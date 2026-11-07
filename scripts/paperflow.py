#!/usr/bin/env python3
"""Batch frame edits and advance a scan to its next review or preflight boundary."""
import argparse
import copy
import hashlib
import json
import math
import re
import os
import secrets
import subprocess
import time
from pathlib import Path
import sys
from urllib.parse import urlsplit

import paperflow_base as base
import paperflow_upload as upload
import skill_update
import paperflow_session

ROOT=Path(__file__).resolve().parent


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    os.chmod(tmp,0o600);os.replace(tmp,path)



def validate_file_paths(args,generated_outputs=(),protected_inputs=()):
    """Reject aliases before any output, checkpoint or update can overwrite input."""
    inputs=('plan','edits','scope_plan','metadata','pixel_review','result','file','pdf','review_pdf')
    outputs=('output','checkpoint','snapshot_output','emit_script')
    paths=[(name,Path(value),name in outputs) for name in (*inputs,*outputs)
           if (value:=getattr(args,name,None)) is not None]
    paths.extend(('protected_input',Path(value),False) for value in protected_inputs)
    generated=[('generated',Path(value),True) for value in generated_outputs]
    paths.extend(generated)
    # atomic_json also writes a temporary sibling before replacing its target.
    paths.extend((name+'_temporary',path.with_name(path.name+'.tmp'),True)
                 for name,path,_ in list(paths) if name in ('output','checkpoint','snapshot_output') or
                 name=='generated' and path.suffix=='.json')
    for index,(name,path,writes) in enumerate(paths):
        for other_name,other,other_writes in paths[:index]:
            if not (writes or other_writes):continue
            same=path.resolve()==other.resolve()
            if not same and path.exists() and other.exists():same=path.samefile(other)
            if same:raise ValueError('file_path_conflict')


def validate_frame_plan(action,plan):
    """Check local edit syntax; server state and review guards remain authoritative."""
    if action=='run':
        plan=plan.get('frames') if isinstance(plan,dict) else None
        if plan is None:return
    elif action!='frames':return
    if not isinstance(plan,dict):raise ValueError('edit_plan_required')
    if plan.get('coordinate_space') is not None:raise ValueError('pixel_review_required')
    operations=plan.get('operations')
    if not isinstance(operations,list):raise ValueError('empty_edit_plan')
    def frame_id(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value):
            raise ValueError('invalid_frame_id')
    def number(value):return type(value) in (int,float) and math.isfinite(value)
    def page(value):
        if type(value) is not int or value<0:raise ValueError('invalid_region')
    def regions(values):
        if not isinstance(values,list) or not 1<=len(values)<=30:raise ValueError('missing_regions')
        for region in values:
            if not isinstance(region,dict):raise ValueError('invalid_region')
            page(region.get('page'));box=region.get('bbox')
            if (not isinstance(box,list) or len(box)!=4 or
                not all(number(v) and 0<=v<=1 for v in box) or box[0]>=box[2] or box[1]>=box[3]):
                raise ValueError('invalid_region')
    def frames(values,minimum):
        if not isinstance(values,list) or len(values)<minimum:raise ValueError('invalid_frame_children')
        for frame in values:
            if not isinstance(frame,dict):raise ValueError('invalid_frame_id')
            frame_id(frame.get('id'))
            if frame.get('parent_id'):frame_id(frame['parent_id'])
            label=frame.get('label')
            if not isinstance(label,str) or not label.strip() or len(label)>100:raise ValueError('invalid_frame_label')
            regions(frame.get('regions'))
    for operation in operations:
        if not isinstance(operation,dict):raise ValueError('unsupported_edit')
        kind=operation.get('type')
        if kind in ('set','split','promote_children'):frame_id(operation.get('id'))
        if kind=='set':
            if 'regions' in operation:regions(operation['regions'])
        elif kind in ('split','promote_children'):frames(operation.get('children'),2)
        elif kind=='replace_page':
            page(operation.get('page'));frames(operation.get('frames'),1)
        elif kind=='shift':
            ids=operation.get('ids')
            if not isinstance(ids,list) or not ids or not all(number(operation.get(k)) for k in ('dx','dy')):
                raise ValueError('invalid_shift')
            for ident in ids:frame_id(ident)
        else:raise ValueError('unsupported_edit')


def local_error(exc):
    code=str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalnum() else 'local_execution_failed'
    details={
        'file_path_conflict':{'next_action':'use_distinct_input_output_checkpoint_paths'},
        'invalid_frame_id':{'constraint':'[A-Za-z0-9_-]{1,100}','next_action':'put_display_question_number_in_label'},
        'unsupported_edit':{'required_field':'type','allowed_types':['set','shift','split','promote_children','replace_page'],
            'next_action':'fix_edit_operation_type'},
        'invalid_region':{'constraint':'page is a nonnegative integer; bbox is finite [x1,y1,x2,y2] within 0..1 with x1<x2 and y1<y2'},
    }
    return {'ok':False,'error':{'code':code,**details.get(code,{})}}


def source():
    contracts=json.loads((ROOT/'api_contracts.json').read_text())
    for op in contracts['operations']:op.pop('purpose',None)
    workflow=(ROOT/'paperflow_workflow.js').read_text().replace('__CONTRACTS__',json.dumps(contracts,separators=(',',':')))
    return (ROOT/'paperflow.js').read_text().replace('__LEGACY__','('+base.JS+')').replace('__WORKFLOW__','('+workflow+')')


def request_payload(args,action,plan=None,checkpoint=None):
    if checkpoint is None:checkpoint=json.loads(args.checkpoint.read_text()) if args.checkpoint and args.checkpoint.exists() else {}
    if checkpoint and (checkpoint.get('origin')!=args.base_url or args.batch_id and checkpoint.get('batch_id')!=args.batch_id):
        raise ValueError('checkpoint_origin_or_batch_mismatch')
    payload={'action':action,'origin':args.base_url,'batch':args.batch_id,'timeout':args.timeout,
             'interval':args.interval,'observe_analysis':getattr(args,'observe_analysis',False),'checkpoint':checkpoint,'plan':plan,'confirm':getattr(args,'confirm',False),'authorize_sync':getattr(args,'authorize_sync',False)}
    if getattr(args,'skip_unlinked',False):payload['skip_unlinked']=True
    if action=='run':
        stop_after=getattr(args,'stop_after',None) or checkpoint.get('stop_after','check')
        if stop_after not in ('grading','frames','check'):raise ValueError('invalid_stop_after')
        payload['stop_after']=stop_after
        checkpoint={**checkpoint,'origin':args.base_url,'batch_id':args.batch_id,'stop_after':stop_after}
        payload['checkpoint']=checkpoint
        if args.checkpoint:atomic_json(args.checkpoint,checkpoint)
    if action=='upload':
        signature=json.dumps([plan['key'],plan['sha256'],plan['fields'],plan.get('scope')],ensure_ascii=False,separators=(',',':'))
        prior=checkpoint.get('upload_receipt')
        if prior and prior.get('signature')!=signature:raise ValueError('upload_plan_changed')
        payload['upload_first_dispatch']=not prior or prior.get('state')=='prepared'
        checkpoint={**checkpoint,'origin':args.base_url,'batch_id':checkpoint.get('batch_id') or args.batch_id,
            'upload_receipt':{**(prior or {}),'key':plan['key'],'sha256':plan['sha256'],'signature':signature,
                'state':'dispatching' if payload['upload_first_dispatch'] else prior['state']}}
        payload['checkpoint']=checkpoint
        if args.checkpoint:atomic_json(args.checkpoint,checkpoint)
    return payload


def execute(args,action,plan=None,checkpoint=None):
    validate_frame_plan(action,plan)
    payload=request_payload(args,action,plan,checkpoint)
    script_source=source()
    expression='('+script_source+')('+json.dumps(payload,ensure_ascii=False)+')'
    try:
        code=upload.native_code(script_source,payload,args.file) if action=='upload' else 'async(page)=>await page.evaluate(('+script_source+'),'+json.dumps(payload,ensure_ascii=False)+')'
        result=base.browser(args,code,expression)
    except FileNotFoundError:
        if action=='upload' and payload.get('upload_first_dispatch'):
            payload['checkpoint']['upload_receipt']=None;atomic_json(args.checkpoint,payload['checkpoint'])
        result={'ok':False,'error':{'code':'browser_backend_unavailable','retryable':False,'next_action':'use_emit_script'}}
    except (OSError,subprocess.TimeoutExpired):
        result={'ok':False,'error':{'code':'transport_uncertain','retryable':False,'next_action':'read_state_before_retry'}}
    if (action=='upload' and payload.get('upload_first_dispatch') and
            result.get('error',{}).get('code')=='existing_playwright_cli_unavailable'):
        # This explicit local precheck failed before any browser or HTTP dispatch.
        cp=payload['checkpoint']
        cp['upload_receipt']={**cp['upload_receipt'],'state':'prepared'}
        result['checkpoint']=cp
    if args.checkpoint and result.get('checkpoint'):atomic_json(args.checkpoint,result['checkpoint'])
    return result


def http_metrics(data):
    calls=data.get('calls',[])
    return {'count':len(calls),'failed':sum(c.get('status',0)>=400 for c in calls),
            'request_ms_sum':sum(c.get('ms',0) for c in calls)}


def compact(data):
    """Keep decision data, not recovery signatures or repeated rich-text payloads."""
    result={k:v for k,v in data.items() if k not in ('checkpoint','calls')}
    result['http']=http_metrics(data)
    r=dict(result.get('result') or {})
    if r.get('outcome')=='class_directory' and r.get('source')=='general':
        selected=r.get('scope_query') or {}
        for field,choices in (('grade','grades'),('subject_id','subjects')):
            if selected.get(field) and isinstance(r.get(choices),list):
                values=r.pop(choices);r[choices+'_count']=len(values)
                r['selected_'+field]=next((value for value in values if str(value.get('id'))==str(selected[field])),None)
    if isinstance(r.get('review'),dict):
        review=r['review'];r['review']={k:v for k,v in review.items() if k not in ('frames','questions')}
        r['review'].update(frame_count=len(review.get('frames',[])),question_count=len(review.get('questions',[])))
    if 'frames' in r:r['frame_count']=len(r.pop('frames'))
    # Explicit snapshot/evidence commands are saved with --output for selective reads.
    if 'questions' in r:r['question_count']=len(r.pop('questions'))
    if isinstance(r.get('failed_papers'),list):
        groups={}
        for paper in r['failed_papers']:
            for issue in dict.fromkeys(i for i in paper.get('issues',[]) if isinstance(i,str)):
                groups.setdefault(issue,[]).append(paper.get('paper_id'))
        shared={issue:ids for issue,ids in groups.items() if len(ids)>1}
        if shared:
            r['shared_failure_issues']=[{'issue':issue,'paper_ids':ids} for issue,ids in shared.items()]
            r['failed_papers']=[{**paper,'issues':[i for i in paper.get('issues',[]) if not isinstance(i,str) or i not in shared]}
                for paper in r['failed_papers']]
    if r.get('check'):
        check=dict(r['check']);counts={}
        for issue in check.get('issues',[]):
            key=(issue.get('code'),issue.get('severity'));counts[key]=counts.get(key,0)+1
        check['issues']=[{'code':c,'severity':s,'count':n} for (c,s),n in counts.items()];r['check']=check
    if r.get('operation') and isinstance(r.get('data'),dict):
        def summary(value):
            keep=('id','status','stage','workflow_mode','grading_engine','revision','read_version','frame_revision',
                'catalog_revision','source_pdf_sha256','reference_student_id','total_pages','pages_per_paper',
                'ready','counts','source_version','outcome','error','semester_id','scope','classes','config',
                'progress','task_control','analysis_status','analysis_version','summary','phases','next_cursor')
            data={k:v for k,v in value.items() if k in keep}
            for key in ('students','papers','questions','frames','results','answers','judgments','items'):
                if isinstance(value.get(key),list):
                    data[key+'_count']=len(value[key])
            if isinstance(value.get('items'),list):
                data['items']=[{k:v for k,v in item.items() if k in ('id','name','state','status','stage','counts','local_changed')}
                    for item in value['items'] if isinstance(item,dict)]
            return data
        if r['operation']=='session':
            session=r['data']
            r['data']={k:session[k] for k in ('ok','xueersi_configured','doubao_configured','model_configured','model') if k in session}
            models=session.get('models')
            r['data']['model_capabilities_included']=isinstance(models,dict)
            if isinstance(models,dict):
                r['data']['models_count']=len(models)
                r['data']['models']={name:{'configured':True,
                    'workflows':{k:v for k,v in (details.get('workflows') or {}).items() if type(v) is bool},
                    'capabilities':details.get('capabilities',[])}
                    for name,details in models.items() if isinstance(details,dict) and details.get('configured') is True}
        elif r['operation'] not in ('classes','general-options','class-students','recent-selection','recent-classes','sync-options','sync-courses','import-links','correction-item'):
            r['data']=summary(r['data'])
            if isinstance(r.get('readback'),dict):r['readback']=summary(r['readback'])
    result['result']=r
    return result


def review_output_paths(metadata,out):
    paths=[out/'review.json',out/'frame-index.json']
    has_crops=False
    for relative in range(metadata.get('pages_per_paper',0)):
        paths.extend((out/f'raw-page-{relative+1}.png',out/f'reference-page-{relative+1}.png'))
        crops=sum(region['page']==relative for frame in metadata.get('frames',[]) for region in frame['regions'])
        has_crops=has_crops or crops>0
        paths.extend(out/f'frame-crops-page-{relative+1}-{sheet+1}.png' for sheet in range((crops+5)//6))
    if has_crops:paths.append(out/'contact-sheet.png')
    return paths


def render_bundle(metadata,pdf_path,out,allow_fallback=True):
    validate_file_paths(argparse.Namespace(pdf=pdf_path),review_output_paths(metadata,out))
    try:
        import pymupdf
        from PIL import Image,ImageDraw
    except ImportError:
        if allow_fallback:
            from paperflow_runtime import python_candidates
            worker="""import sys,json
sys.path.insert(0,sys.argv[1])
from paperflow import render_bundle,local_error
from pathlib import Path
d=json.load(sys.stdin)
try:print(json.dumps({'ok':True,'result':render_bundle(d['metadata'],Path(d['pdf']),Path(d['out']),allow_fallback=False)}))
except Exception as exc:print(json.dumps(local_error(exc)))
"""
            for python in python_candidates():
                try:
                    result=subprocess.run([str(python),'-c',worker,str(ROOT)],
                        input=json.dumps({'metadata':metadata,'pdf':str(pdf_path.absolute()),'out':str(out.absolute())}),
                        capture_output=True,text=True,timeout=120,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
                    if result.returncode==0:
                        response=json.loads(result.stdout)
                        if response.get('ok'):
                            data=response['result'];data['renderer_python']=str(python);return data
                        code=response.get('error',{}).get('code')
                        if code=='review_dependency_unavailable':continue
                        raise ValueError(code if code in ('source_pdf_hash_mismatch','reference_page_out_of_range',
                            'invalid_review_bbox','file_path_conflict') else 'review_render_failed')
                    raise ValueError('review_render_failed')
                except subprocess.TimeoutExpired:raise ValueError('review_render_timeout') from None
                except OSError:continue
        raise ValueError('review_dependency_unavailable') from None
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest()!=metadata.get('source_pdf_sha256'):
        raise ValueError('source_pdf_hash_mismatch')
    out.mkdir(parents=True,exist_ok=True);os.chmod(out,0o700)
    frames=metadata['frames'];start=metadata['reference_start'];count=metadata['pages_per_paper']
    binding={k:metadata.get(k) for k in ('batch_id','source_pdf_sha256','frame_revision','reference_student_id','reference_start','pages_per_paper')}
    cache_key=hashlib.sha256(json.dumps({**binding,'frames':frames,'renderer_version':2},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    previous={}
    try:
        previous=json.loads((out/'review.json').read_text())
    except (OSError,ValueError):pass
    def intact(name):
        return (isinstance(name,str) and Path(name).name==name and (out/name).is_file() and
                hashlib.sha256((out/name).read_bytes()).hexdigest()==previous.get('file_sha256',{}).get(name))
    if previous.get('render_key')==cache_key and previous.get('file_sha256') and all(intact(name) for name in previous['file_sha256']):
        manifest={**previous,**metadata,'reviewed':False};atomic_json(out/'review.json',manifest)
        return {'manifest':str(out/'review.json'),'images':manifest['image_files'],'detail_sheets':manifest['detail_sheets'],
            'frame_index':str(out/'frame-index.json'),'decoded_pages':0,'crops':manifest['crop_count'],'reviewed':False,'cache_hit':True}
    raw_reusable=all(previous.get(k)==binding.get(k) for k in ('source_pdf_sha256','reference_student_id','reference_start','pages_per_paper'))
    images=[];files=[];index=[];sheets=[];decoded=0;reused=0
    with pymupdf.open(pdf_path) as doc:
        if start<0 or count<1 or start+count>len(doc):raise ValueError('reference_page_out_of_range')
        # Decode each original page once; supply raw, overview and bounded detail views.
        for relative in range(count):
            raw=out/f'raw-page-{relative+1}.png'
            if raw_reusable and intact(raw.name):
                with Image.open(raw) as existing:image=existing.convert('RGB')
                reused+=1
            else:
                pix=doc[start+relative].get_pixmap(matrix=pymupdf.Matrix(2,2))
                image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                image.save(raw);decoded+=1
            files.append(raw.name)
            marked=image.copy();draw=ImageDraw.Draw(marked);details=[]
            for f in frames:
                for region in f['regions']:
                    if region['page']!=relative:continue
                    b=region['bbox'];box=(round(b[0]*image.width),round(b[1]*image.height),round(b[2]*image.width),round(b[3]*image.height))
                    if not (0<=box[0]<box[2]<=image.width and 0<=box[1]<box[3]<=image.height):
                        raise ValueError('invalid_review_bbox')
                    number=len(index)+1
                    draw.rectangle(box,outline='#e00000',width=3)
                    draw.text((box[0]+3,box[1]+3),str(number),fill='#d00000',stroke_width=1,stroke_fill='white')
                    crop=image.crop(box);crop.thumbnail((600,230));images.append((str(number),crop))
                    # Context outside the box makes truncated stems/options visible.
                    margin=round(min(image.size)*.02)
                    context=(max(0,box[0]-margin),max(0,box[1]-margin),min(image.width,box[2]+margin),min(image.height,box[3]+margin))
                    detail=image.crop(context);dd=ImageDraw.Draw(detail)
                    dd.rectangle((box[0]-context[0],box[1]-context[1],box[2]-context[0]-1,box[3]-context[1]-1),outline='#e00000',width=3)
                    detail.thumbnail((780,430))
                    entry={'number':number,'frame_id':f['id'],'label':f['label'],
                        'parent_id':f.get('parent_id'),'page':relative,'pdf_page':start+relative+1,'bbox':b}
                    index.append(entry);details.append((entry,detail))
            path=out/f'reference-page-{relative+1}.png';marked.save(path);files.append(path.name)
            for offset in range(0,len(details),6):
                chunk=details[offset:offset+6];rows=[]
                for i in range(0,len(chunk),2):rows.append(max(im.height for _,im in chunk[i:i+2])+38)
                sheet=Image.new('RGB',(1600,sum(rows)),'#eeeeee');sd=ImageDraw.Draw(sheet);y=0
                name=f'frame-crops-page-{relative+1}-{offset//6+1}.png'
                for i,(entry,detail) in enumerate(chunk):
                    if i and i%2==0:y+=rows[i//2-1]
                    x=(i%2)*800
                    sd.text((x+10,y+5),f"#{entry['number']} {entry['frame_id']} PDF {entry['pdf_page']}",fill='black')
                    sheet.paste(detail,(x+10,y+30));entry['image_file']=name
                sheet.save(out/name);files.append(name);sheets.append(name)
    if images:
        # Compatibility overview; detail sheets avoid shrinking an entire long sheet.
        sheet=Image.new('RGB',(1240,270*((len(images)+1)//2)),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for i,(label,image) in enumerate(images):
            x=(i%2)*620;y=(i//2)*270;draw.text((x+10,y+5),label,fill='black');sheet.paste(image,(x+10,y+25))
        sheet.save(out/'contact-sheet.png');files.append('contact-sheet.png')
    binding={k:metadata.get(k) for k in ('batch_id','source_pdf_sha256','frame_revision','reference_student_id')}
    atomic_json(out/'frame-index.json',{**binding,'reviewed':False,'frames':index})
    manifest={**metadata,'reviewed':False,'image_files':files,'detail_sheets':sheets,
        'frame_index':'frame-index.json','decoded_pages':decoded,'crop_count':len(images),'render_key':cache_key,
        'file_sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in [*files,'frame-index.json']}}
    atomic_json(out/'review.json',manifest)
    return {'manifest':str(out/'review.json'),'images':files,'detail_sheets':sheets,
        'frame_index':str(out/'frame-index.json'),'decoded_pages':decoded,'raw_pages_reused':reused,'crops':len(images),'reviewed':False,'cache_hit':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url');parser.add_argument('--batch-id')
    parser.add_argument('--batch-url')
    parser.add_argument('--browser-session')
    parser.add_argument('--emit-script',type=Path)
    parser.add_argument('--standalone-script',action='store_true')
    parser.add_argument('--sync-evaluate',action='store_true')
    parser.add_argument('--wrapper',default=str(Path.home()/'.codex/skills/playwright/scripts/playwright_cli.sh'))
    base.browser_options(parser)
    parser.add_argument('--timeout',type=int,default=45);parser.add_argument('--interval',type=int,default=5)
    parser.add_argument('--checkpoint',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verbose',action='store_true')
    sub=parser.add_subparsers(dest='action',required=True)
    for name in ('inspect','check','diagnose','usage','access','relogin','roster'):
        p=sub.add_parser(name)
        if name=='check':p.add_argument('--skip-unlinked',action='store_true')
    p=sub.add_parser('browser-open');p.add_argument('--executable')
    sub.add_parser('browser-close')
    p=sub.add_parser('session-connect')
    p.add_argument('--source-url');p.add_argument('--source-target')
    p.add_argument('--target-url');p.add_argument('--executable')
    sub.add_parser('session-status');sub.add_parser('session-close')
    p=sub.add_parser('api-list');p.add_argument('--operation')
    p=sub.add_parser('api-call');p.add_argument('--operation',required=True);p.add_argument('--plan',type=Path)
    for name in ('scope','sync'):
        p=sub.add_parser(name);p.add_argument('--plan',type=Path,required=True)
        if name=='sync':p.add_argument('--authorize-sync',action='store_true')
    for name in ('classes','class-students'):
        p=sub.add_parser(name);p.add_argument('--source',choices=('teaching','general'),default='teaching')
        p.add_argument('--grade');p.add_argument('--subject-id');p.add_argument('--course-id')
        if name=='class-students':
            p.add_argument('--class-id',required=True,action='append')
            p.add_argument('--name-exact',action='append')
    p=sub.add_parser('prepare');p.add_argument('--file',type=Path,required=True);p.add_argument('--pages-per-paper',type=int)
    p.add_argument('--read-timeout',type=float,default=10)
    p=sub.add_parser('doctor');p.add_argument('--read-timeout',type=float,default=10)
    p=sub.add_parser('upload');p.add_argument('--file',type=Path,required=True);p.add_argument('--pages-per-paper',type=int,required=True)
    p.add_argument('--key',required=True);p.add_argument('--workflow',choices=('scan','grading'),default='scan')
    p.add_argument('--engine',choices=('llm','xueersi','doubao'),default='llm');p.add_argument('--model',default='qwen3.8-max')
    p.add_argument('--has-answer-paper',action='store_true');p.add_argument('--paper-size',choices=('A4','A3'),default='A4')
    p.add_argument('--orientation',choices=('portrait','landscape'),default='portrait');p.add_argument('--paper-sides',choices=('single','double'),default='single')
    p.add_argument('--full-scan',action='store_true');p.add_argument('--analysis-fast',action='store_true')
    p.add_argument('--read-timeout',type=float,default=10)
    p.add_argument('--scope-plan',type=Path);p.add_argument('--file-input-selector',default='#paperflow-upload')
    p=sub.add_parser('run');p.add_argument('--plan',type=Path)
    p.add_argument('--skip-unlinked',action='store_true')
    p.add_argument('--stop-after',choices=('grading','frames','check'))
    p.add_argument('--reference-paper',help='ID of the actually reviewed reference paper; avoids a one-field plan file')
    p.add_argument('--review-pdf',type=Path);p.add_argument('--review-out',type=Path)
    p.add_argument('--follow',action='store_true');p.add_argument('--max-seconds',type=int,default=600)
    p=sub.add_parser('snapshot');p.add_argument('--output',type=Path,dest='snapshot_output')
    p=sub.add_parser('frames');p.add_argument('--edits',type=Path,required=True);p.add_argument('--confirm',action='store_true')
    p.add_argument('--pixel-review',type=Path)
    p=sub.add_parser('associate');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('review');p.add_argument('--pdf',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--metadata',type=Path)
    p=sub.add_parser('retry-precut');p.add_argument('--page',type=int,required=True);p.add_argument('--frame-revision',required=True)
    p=sub.add_parser('evidence');p.add_argument('--paper-id',required=True);p.add_argument('--question-id',action='append')
    p=sub.add_parser('responses');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('catalog');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('collect');p.add_argument('--result',type=Path,required=True)
    args=parser.parse_args()
    try:validate_file_paths(args)
    except (OSError,ValueError) as exc:
        print(json.dumps(local_error(exc),ensure_ascii=False));return 1
    import re
    if args.batch_url:
        link=urlsplit(args.batch_url)
        match=re.fullmatch(r'/exams/([A-Za-z0-9_-]{1,80})(?:/analysis|/papers/[A-Za-z0-9_-]{1,80})?/?',link.path)
        if link.scheme not in ('http','https') or not link.netloc or link.username or link.password or link.fragment or not match:
            parser.error('invalid batch URL')
        origin=link.scheme+'://'+link.netloc
        if (args.base_url and args.base_url.rstrip('/')!=origin) or (args.batch_id and args.batch_id!=match[1]):
            parser.error('batch URL conflicts with origin or batch id')
        args.base_url=origin;args.batch_id=match[1]
    args.base_url=(args.base_url or base.DEFAULT_ORIGIN).rstrip('/')
    if args.action=='doctor':
        if not 0.1<=args.read_timeout<=60:parser.error('read-timeout 0.1..60')
        try:
            from paperflow_doctor import doctor
            result=doctor(args,ROOT.parent)
        except ImportError:
            result={'ok':False,'error':{'code':'installation_incomplete','next_action':'verify_installed_release_files'}}
        if args.output:atomic_json(args.output,result)
        print(json.dumps(result,ensure_ascii=False));return 0 if result.get('ok') else 1
    if args.action=='prepare':
        if not 0.1<=args.read_timeout<=60:parser.error('read-timeout 0.1..60')
        result=upload.prepare(args)
        if args.output:atomic_json(args.output,result)
        print(json.dumps(result,ensure_ascii=False));return 0 if result.get('ok') else 1
    if args.action=='upload' and not 0.1<=args.read_timeout<=60:parser.error('read-timeout 0.1..60')
    if args.action=='api-list':
        contracts=json.loads((ROOT/'api_contracts.json').read_text())
        if args.operation:contracts['operations']=[o for o in contracts['operations'] if o['name']==args.operation]
        print(json.dumps(contracts,ensure_ascii=False));return 0 if contracts['operations'] else 1
    # Upload already records the batch identity; reuse that bound checkpoint.
    if not args.batch_id and args.checkpoint and args.checkpoint.is_file():
        try:
            saved=json.loads(args.checkpoint.read_text())
            if not isinstance(saved,dict):raise ValueError()
        except (OSError,ValueError):parser.error('invalid checkpoint file')
        if saved.get('origin')!=args.base_url:parser.error('checkpoint origin conflicts with base URL')
        args.batch_id=saved.get('batch_id') or ''
        if not isinstance(args.batch_id,str):parser.error('invalid checkpoint batch id')
    batch_optional=args.action in ('upload','classes','class-students','access','relogin','api-call','collect',
                                  'session-connect','session-status','session-close','browser-open','browser-close')
    if not args.batch_id and not batch_optional:parser.error('batch-id or batch-url required')
    args.batch_id=args.batch_id or ''
    if args.action=='upload' and not args.checkpoint:parser.error('upload requires checkpoint')
    if not args.browser_session and not args.emit_script and args.action!='collect' and not (args.action=='review' and args.metadata):parser.error('browser-session required for browser backend')
    if args.emit_script and args.action in ('review','collect'):parser.error('emit-script requires a browser action')
    if args.emit_script and args.action in ('browser-open','browser-close'):parser.error(args.action+' requires a native Playwright backend')
    url=urlsplit(args.base_url)
    if url.scheme not in ('http','https') or not url.netloc or url.path or url.username or url.password or url.query or url.fragment:
        parser.error('base-url must be an origin')
    import re
    if args.batch_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',args.batch_id):parser.error('invalid batch id')
    if not 1<=args.timeout<=180 or not 2<=args.interval<=30:parser.error('invalid timeout/interval')
    if args.action=='run' and bool(args.review_pdf)!=bool(args.review_out):parser.error('review-pdf and review-out must be provided together')
    if args.action=='run' and not 1<=args.max_seconds<=3600:parser.error('max-seconds 1..3600')
    if args.emit_script:
        engine_source=source();engine_id='__paperflow_'+hashlib.sha256(engine_source.encode()).hexdigest()[:20]
        engine_file=None if args.standalone_script else args.emit_script.with_name('paperflow-engine-'+engine_id.removeprefix('__paperflow_')+'.js')
        poll_file=args.emit_script.with_name(args.emit_script.stem+'-poll.js') if args.sync_evaluate else None
        try:validate_file_paths(args,[path for path in (engine_file,poll_file) if path is not None])
        except (OSError,ValueError) as exc:
            print(json.dumps(local_error(exc),ensure_ascii=False));return 1
    if __name__=='__main__' and args.action not in ('api-list','collect','session-status','session-close','browser-close') and not (args.action=='review' and args.metadata):
        try:updated=skill_update.ensure(ROOT.parent)
        except Exception:updated={'outcome':'update_failed','error':'update_check_unavailable','updated':False}
        if updated.get('updated'):
            os.execv(sys.executable,[sys.executable,str(ROOT/'paperflow.py'),*sys.argv[1:]])
        if updated.get('outcome')=='update_in_progress':
            print(json.dumps({'ok':False,'error':{'code':'skill_update_in_progress','retry_after_seconds':2}}));return 1
        if updated.get('outcome') in ('update_failed','local_changes_preserved','baseline_missing'):
            print(json.dumps({'skill_update':updated},ensure_ascii=False),file=sys.stderr)
    if args.action in ('session-connect','session-status','session-close'):
        result=paperflow_session.invoke(args,args.action.removeprefix('session-'))
        if args.output:atomic_json(args.output,result)
        print(json.dumps(result,ensure_ascii=False));return 0 if result.get('ok') else 1
    if args.action in ('browser-open','browser-close'):
        from paperflow_browser import open_browser,close_browser
        result=(open_browser if args.action=='browser-open' else close_browser)(args)
        if args.output:atomic_json(args.output,result)
        print(json.dumps(result,ensure_ascii=False));return 0 if result.get('ok') else 1
    try:
        plan_path=getattr(args,'plan',None) or getattr(args,'edits',None)
        if plan_path and not plan_path.is_file():raise ValueError('plan_file_not_found')
        plan=json.loads(plan_path.read_text()) if plan_path else None
        if args.action=='frames' and args.pixel_review:
            from paperflow_coordinates import normalize_pixel_plan
            plan,images=normalize_pixel_plan(plan,args.pixel_review,args.batch_id)
            validate_file_paths(args,protected_inputs=images)
        if args.action=='run' and args.reference_paper:
            if plan is not None and not isinstance(plan,dict):raise ValueError('invalid_run_plan')
            if plan and plan.get('reference_student_id') not in (None,args.reference_paper):
                raise ValueError('reference_plan_conflict')
            plan={**(plan or {}),'reference_student_id':args.reference_paper}
        if args.action=='api-call':plan={**(plan or {}),'operation':args.operation}
        if args.action in ('classes','class-students'):
            plan={k:getattr(args,k) for k in ('source','grade','subject_id','course_id') if getattr(args,k) is not None}
            if args.action=='class-students':
                if len(args.class_id)==1 and not args.name_exact:plan['class_id']=args.class_id[0]
                else:plan.update(class_ids=args.class_id,name_exact=args.name_exact or [])
        if args.action=='upload':plan=upload.plan(args)
        if args.action=='retry-precut':plan={'page':args.page,'frame_revision':args.frame_revision}
        if args.action=='evidence':plan={'paper_id':args.paper_id,'question_ids':args.question_id}
        validate_frame_plan(args.action,plan)
        if args.emit_script:
            payload=request_payload(args,args.action,plan)
            args.emit_script.parent.mkdir(parents=True,exist_ok=True)
            engine_info={}
            if args.standalone_script:
                script='('+engine_source+')('+json.dumps(payload,ensure_ascii=False)+')'
            else:
                bootstrap='(()=>{if(location.origin!=='+json.dumps(args.base_url)+')return {ok:false,error:{code:"origin_mismatch"}};Object.defineProperty(globalThis,'+json.dumps(engine_id)+',{value:('+engine_source+'),configurable:true});return {ok:true,result:{outcome:"engine_loaded",engine_id:'+json.dumps(engine_id)+'}};})()'
                engine_file.write_text(bootstrap,encoding='utf-8');os.chmod(engine_file,0o600)
                script='(async()=>{const input='+json.dumps(payload,ensure_ascii=False)+';const engine=globalThis['+json.dumps(engine_id)+'];if(typeof engine!=="function"){const checkpoint={origin:input.origin,batch_id:input.batch,...input.checkpoint};if(input.action==="upload"&&input.upload_first_dispatch&&checkpoint.upload_receipt?.state==="dispatching")checkpoint.upload_receipt={...checkpoint.upload_receipt,state:"prepared"};return {ok:false,error:{code:"engine_not_loaded",next_action:"evaluate_bootstrap_file"},calls:[],checkpoint};}return await engine(input);})()'
                engine_info={'engine_file':str(engine_file),'engine_id':engine_id,'engine_load_required_if_missing':True}
            if args.sync_evaluate:
                job_id='__paperflow_job_'+secrets.token_hex(12)
                # Some product evaluate hosts serialize a Promise instead of awaiting it.
                # The retained job makes repeated dispatch of this same file idempotent.
                wrapped='(()=>{const key='+json.dumps(job_id)+';let existing=globalThis[key];if(existing?.state==="completed"&&existing.result?.error?.code==="engine_not_loaded"){delete globalThis[key];existing=null;}if(existing)return existing.state==="completed"?existing.result:{ok:true,result:{outcome:"browser_step_running",job_id:key}};const job={state:"running"};Object.defineProperty(globalThis,key,{value:job,configurable:true});Promise.resolve().then(()=>('+script+')).then(result=>{job.result=result;job.state="completed";},()=>{job.result={ok:false,error:{code:"browser_step_failed",next_action:"read_state_before_retry"}};job.state="completed";});return {ok:true,result:{outcome:"browser_step_started",job_id:key}};})()'
                poll='(()=>{const job=globalThis['+json.dumps(job_id)+'];if(!job)return {ok:false,error:{code:"browser_step_missing",next_action:"read_state_before_retry"}};return job.state==="completed"?job.result:{ok:true,result:{outcome:"browser_step_running",job_id:'+json.dumps(job_id)+'}};})()'
                poll_file.write_text(poll,encoding='utf-8');os.chmod(poll_file,0o600)
                script=wrapped
                engine_info.update(poll_file=str(poll_file),job_id=job_id,evaluate_mode='synchronous_dispatch')
            args.emit_script.write_text(script,encoding='utf-8');os.chmod(args.emit_script,0o600)
            emitted={'ok':True,'result':{'outcome':'browser_script_created',
                'script_file':str(args.emit_script),'origin':args.base_url,'batch_id':args.batch_id,
                **engine_info,'script_bytes':len(script.encode()),'executed':False,'submitted':False}}
            if args.output:atomic_json(args.output,emitted)
            print(json.dumps(emitted,ensure_ascii=False))
            return 0
        started=time.monotonic()
        execution_args=copy.copy(args)
        if args.action=='run' and args.follow:execution_args.timeout=min(args.timeout,args.max_seconds)
        if args.action=='review' and args.metadata:
            metadata=json.loads(args.metadata.read_text())
            if isinstance(metadata,dict) and isinstance(metadata.get('result'),dict):metadata=metadata['result']
            if isinstance(metadata,dict) and isinstance(metadata.get('review'),dict):metadata=metadata['review']
            if not isinstance(metadata,dict) or metadata.get('batch_id')!=args.batch_id:
                raise ValueError('review_batch_mismatch')
            data={'ok':True,'result':metadata}
        elif args.action=='collect':
            data=json.loads(args.result.read_text())
            if not isinstance(data,dict) or type(data.get('ok')) is not bool:
                raise ValueError('invalid_browser_result')
            cp=data.get('checkpoint')
            if not isinstance(cp,dict) or cp.get('origin')!=args.base_url or (args.batch_id and cp.get('batch_id')!=args.batch_id):
                raise ValueError('checkpoint_origin_or_batch_mismatch')
            if args.checkpoint:atomic_json(args.checkpoint,cp)
        else:
            data=execute(execution_args,'snapshot' if args.action=='review' else args.action,plan)
        if args.action=='run' and args.follow:
            calls=list(data.get('calls',[]));transitions=list(data.get('transitions',[]))
            while data.get('ok') and data.get('result',{}).get('outcome')=='waiting' and time.monotonic()-started<args.max_seconds:
                if data['result'].get('waiting_for') in ('grading','grading_stop','task_stop','analysis_start'):
                    time.sleep(min(args.interval,max(0,args.max_seconds-(time.monotonic()-started))))
                if time.monotonic()-started>=args.max_seconds:break
                print(json.dumps({'outcome':'waiting','analysis_status':data['result'].get('analysis_status'),
                                  'elapsed_seconds':round(time.monotonic()-started,1)},ensure_ascii=False),file=sys.stderr,flush=True)
                execution_args=copy.copy(args)
                execution_args.timeout=min(args.timeout,max(.001,args.max_seconds-(time.monotonic()-started)))
                execution_args.observe_analysis=(data['result'].get('waiting_for')=='analysis_start' or
                    data['result'].get('analysis_status') in ('generating','catalog_confirmed','frames_confirmed','processing') and data['result'].get('waiting_for') not in ('grading','grading_stop','task_stop','media'))
                data=execute(execution_args,'run',plan,data.get('checkpoint'))
                calls.extend(data.get('calls',[]));transitions.extend(data.get('transitions',[]))
            data['calls']=calls;data['transitions']=transitions
            data['follow_seconds']=round(time.monotonic()-started,3)
            data['wall_seconds']=round(time.monotonic()-started,3)
        if args.action=='run' and args.review_pdf and data.get('ok') and data['result'].get('review'):
            validate_file_paths(args,review_output_paths(data['result']['review'],args.review_out))
            data['result']['review_bundle']=render_bundle(data['result']['review'],args.review_pdf,args.review_out)
        if args.action=='review' and data.get('ok'):
            validate_file_paths(args,review_output_paths(data['result'],args.out))
            data['result']=render_bundle(data['result'],args.pdf,args.out)
        if args.action=='snapshot' and args.snapshot_output and data.get('ok'):
            atomic_json(args.snapshot_output,data['result']);data['snapshot_file']=str(args.snapshot_output)
    except Exception as exc:
        data=local_error(exc)
        if data.get('error',{}).get('code')=='file_path_conflict':
            print(json.dumps(data,ensure_ascii=False));return 1
    data['http']=http_metrics(data)
    if args.output:
        atomic_json(args.output,data)
    shown=data if args.verbose else compact(data)
    if args.output:shown={**shown,'output_file':str(args.output)}
    print(json.dumps(shown,ensure_ascii=False))
    return 0 if data.get('ok') else 1


if __name__=='__main__':sys.exit(main())
