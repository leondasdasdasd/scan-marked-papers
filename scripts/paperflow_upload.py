"""Local upload validation and native file binding; authentication stays in-page."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def probe(path, timeout=10, pages_per_paper=None):
    """Bound filesystem reads; a stalled provider must not stall the agent indefinitely."""
    started = time.monotonic()
    worker = r"""
import hashlib, json, sys
from pathlib import Path
try:
    path = Path(sys.argv[1])
    if not path.is_file() or path.stat().st_size > 100*1024*1024:
        raise ValueError('invalid_pdf_file')
    with path.open('rb') as stream:
        data = stream.read(100*1024*1024+1)
    if len(data)>100*1024*1024: raise ValueError('invalid_pdf_file')
    if b'%PDF-' not in data[:1024]: raise ValueError('invalid_pdf_header')
    result = {'sha256':hashlib.sha256(data).hexdigest(), 'size':len(data), 'page_count':None}
    try:
        import pymupdf
    except ImportError:
        result['page_count_available'] = False
    else:
        try:
            with pymupdf.open(stream=data, filetype='pdf') as pdf:
                if pdf.needs_pass:raise ValueError('pdf_password_required')
                if not 1<=len(pdf)<=600:raise ValueError('invalid_pdf_page_count')
                result['page_count'] = len(pdf)
                result['page_count_available'] = True
                geometries = {}
                for page in pdf:
                    width, height = round(page.rect.width, 2), round(page.rect.height, 2)
                    short, long = sorted((width, height))
                    paper_size = next((name for name, size in
                        (('A4', (595.28, 841.89)), ('A3', (841.89, 1190.55)))
                        if abs(short-size[0]) <= 3 and abs(long-size[1]) <= 3), None)
                    orientation = 'landscape' if width > height else 'portrait' if height > width else 'square'
                    key = (width, height, paper_size, orientation)
                    geometries[key] = geometries.get(key, 0) + 1
                result['page_geometry'] = [dict(width_points=k[0], height_points=k[1],
                    paper_size=k[2], orientation=k[3], pages=count) for k, count in geometries.items()]
        except ValueError as exc:
            if str(exc) in ('pdf_password_required','invalid_pdf_page_count'):raise
            raise ValueError('invalid_pdf_file') from None
        except Exception:
            raise ValueError('invalid_pdf_file')
    print(json.dumps({'ok':True, 'result':result}))
except Exception as exc:
    code = str(exc) if isinstance(exc,ValueError) else 'pdf_read_failed'
    print(json.dumps({'ok':False, 'error':{'code':code}}))
"""
    try:
        from paperflow_runtime import python_candidates
        for python in (sys.executable,*python_candidates()):
            remaining=timeout-(time.monotonic()-started)
            if remaining<=0:raise subprocess.TimeoutExpired('pdf_probe',timeout)
            proc = subprocess.run([str(python), '-c', worker, str(path)], capture_output=True,
                                  text=True, timeout=remaining,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
            data = json.loads(proc.stdout)
            if proc.returncode or not isinstance(data, dict) or type(data.get('ok')) is not bool:
                raise ValueError('invalid_pdf_probe_response')
            if not data['ok'] or data['result'].get('page_count_available'):
                break
        if data.get('ok') and not data['result'].get('page_count_available'):
            data['result']['validation_pending']='server_pdf_validation'
            data['next_action']='upload_for_authoritative_pdf_validation'
    except subprocess.TimeoutExpired:
        data = {'ok':False, 'error':{'code':'pdf_read_timeout',
                'next_action':'use_existing_file_tool_or_accessible_copy'}}
    except (OSError, ValueError):
        data = {'ok':False, 'error':{'code':'pdf_read_failed'}}
    if data.get('ok'):
        pages = data['result']['page_count']
        if pages_per_paper is not None and (not 1 <= pages_per_paper <= 12 or
                pages is not None and (pages > 600 or pages < pages_per_paper or pages % pages_per_paper)):
            data = {'ok':False, 'error':{'code':'invalid_pdf_split'}}
        elif pages_per_paper is not None and pages is not None:
            data['result']['paper_count'] = pages // pages_per_paper
    data['wall_seconds'] = round(time.monotonic()-started, 3)
    return data


def prepare(args):
    data = probe(args.file, args.read_timeout, args.pages_per_paper)
    executable = lambda value: bool(shutil.which(str(value)))
    data['capabilities'] = {
        'existing_node': executable('node'),
        'playwright_cli_file_exists': bool(getattr(args,'playwright_cli',None) and args.playwright_cli.is_file()),
        'playwright_wrapper_executable': executable(args.wrapper),
        'agent_browser_executable': executable(args.browser_executable),
        'browser_authentication_verified': False,
        'evaluate_tool_requires_product_verification': True,
    }
    data['executed'] = False
    data['submitted'] = False
    return data


def plan(args):
    if not 1<=args.pages_per_paper<=12:raise ValueError('invalid_paper_pages')
    if args.paper_sides=='double' and args.pages_per_paper%2:raise ValueError('invalid_duplex_pages')
    if args.workflow=='scan' and (args.engine!='llm' or args.has_answer_paper):raise ValueError('scan_mode_conflict')
    if args.workflow=='grading' and args.engine=='llm' and not args.has_answer_paper:raise ValueError('answer_paper_required')
    checked = probe(args.file, getattr(args, 'read_timeout', 10), args.pages_per_paper)
    if not checked['ok']:raise ValueError(checked['error']['code'])
    file = checked['result']
    if args.has_answer_paper and file['page_count'] is not None and file['page_count']<2*args.pages_per_paper:
        raise ValueError('invalid_pdf_split')

    fields={'workflow_mode':args.workflow,'grading_engine':args.engine,'llm_model':args.model,
        'has_answer_paper':args.has_answer_paper,'pages_per_paper':args.pages_per_paper,
        'paper_size':args.paper_size,'orientation':args.orientation,'paper_sides':args.paper_sides}
    if args.workflow=='scan':fields['scan_fast']=not args.full_scan
    if args.workflow=='grading' and args.engine!='llm':fields['analysis_fast']=args.analysis_fast
    scope=json.loads(args.scope_plan.read_text()) if args.scope_plan else None
    if scope and (scope.get('evidence_confirmed') is not True or not str(scope.get('evidence_note','')).strip()):raise ValueError('scope_evidence_required')
    return {'key':args.key,'sha256':file['sha256'],'size':file['size'],
        'fields':fields,'scope':scope,'file_input_selector':args.file_input_selector}


def native_code(script_source,payload,path):
    return '''async(page)=>{
      const input='''+json.dumps(payload,ensure_ascii=False)+''';
      if(await page.evaluate(()=>location.origin)!==input.origin)return {ok:false,error:{code:'origin_mismatch'}};
      let created=false;
      if(input.plan.file_input_selector==='#paperflow-upload'){
        created=await page.evaluate(()=>{if(document.getElementById('paperflow-upload'))return false;
          const el=document.createElement('input');el.type='file';el.id='paperflow-upload';el.hidden=true;document.body.appendChild(el);return true;});
      }
      try{
        await page.locator(input.plan.file_input_selector).setInputFiles('''+json.dumps(str(path.resolve()))+''');
        return await page.evaluate(('''+script_source+'''),input);
      }finally{if(created)await page.evaluate(()=>document.getElementById('paperflow-upload')?.remove());}
    }'''
