"""Local upload validation and native file binding; authentication stays in-page."""
import hashlib
import json
from pathlib import Path


def plan(args):
    path=args.file.resolve()
    if not path.is_file() or path.stat().st_size>100*1024*1024:
        raise ValueError('invalid_pdf_file')
    with path.open('rb') as f:
        if b'%PDF-' not in f.read(1024):raise ValueError('invalid_pdf_header')
    if not 1<=args.pages_per_paper<=12:raise ValueError('invalid_paper_pages')
    if args.paper_sides=='double' and args.pages_per_paper%2:raise ValueError('invalid_duplex_pages')
    if args.workflow=='scan' and (args.engine!='llm' or args.has_answer_paper):raise ValueError('scan_mode_conflict')
    if args.workflow=='grading' and args.engine=='llm' and not args.has_answer_paper:raise ValueError('answer_paper_required')
    try:
        import pymupdf
    except ImportError:pymupdf=None
    if pymupdf:
        with pymupdf.open(path) as pdf:
            pages=len(pdf)
            if pages>600 or pages%args.pages_per_paper or pages<args.pages_per_paper*(2 if args.has_answer_paper else 1):raise ValueError('invalid_pdf_split')
    fields={'workflow_mode':args.workflow,'grading_engine':args.engine,'llm_model':args.model,
        'has_answer_paper':args.has_answer_paper,'pages_per_paper':args.pages_per_paper,
        'paper_size':args.paper_size,'orientation':args.orientation,'paper_sides':args.paper_sides}
    if args.workflow=='scan':fields['scan_fast']=not args.full_scan
    if args.workflow=='grading' and args.engine!='llm':fields['analysis_fast']=args.analysis_fast
    scope=json.loads(args.scope_plan.read_text()) if args.scope_plan else None
    if scope and (scope.get('evidence_confirmed') is not True or not str(scope.get('evidence_note','')).strip()):raise ValueError('scope_evidence_required')
    return {'key':args.key,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':path.stat().st_size,
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
