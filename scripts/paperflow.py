#!/usr/bin/env python3
"""Batch frame edits and advance a scan to its next review or preflight boundary."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
import sys
from urllib.parse import urlsplit

import paperflow_base as base

ROOT=Path(__file__).resolve().parent


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    os.chmod(tmp,0o600);os.replace(tmp,path)


def source():return (ROOT/'paperflow.js').read_text().replace('__LEGACY__','('+base.JS+')')


def execute(args,action,plan=None,checkpoint=None):
    if checkpoint is None:checkpoint=json.loads(args.checkpoint.read_text()) if args.checkpoint and args.checkpoint.exists() else {}
    if checkpoint and (checkpoint.get('origin')!=args.base_url or checkpoint.get('batch_id')!=args.batch_id):
        raise ValueError('checkpoint_origin_or_batch_mismatch')
    payload={'action':action,'origin':args.base_url,'batch':args.batch_id,'timeout':args.timeout,
             'interval':args.interval,'checkpoint':checkpoint,'plan':plan,'confirm':getattr(args,'confirm',False)}
    result=base.browser(args,'async(page)=>await page.evaluate(('+source()+'),'+json.dumps(payload,ensure_ascii=False)+')')
    if args.checkpoint and result.get('checkpoint'):atomic_json(args.checkpoint,result['checkpoint'])
    return result


def compact(data):
    """Keep decision data, not recovery signatures or repeated rich-text payloads."""
    result={k:v for k,v in data.items() if k not in ('checkpoint','calls')}
    calls=data.get('calls',[])
    result['http']={'count':len(calls),'failed':sum(c.get('status',0)>=400 for c in calls),
                    'request_ms_sum':sum(c.get('ms',0) for c in calls)}
    r=dict(result.get('result') or {})
    if isinstance(r.get('review'),dict):
        review=r['review'];r['review']={k:v for k,v in review.items() if k not in ('frames','questions')}
        r['review'].update(frame_count=len(review.get('frames',[])),question_count=len(review.get('questions',[])))
    if 'frames' in r:r['frame_count']=len(r.pop('frames'))
    # Explicit snapshot/evidence commands are saved with --output for selective reads.
    if 'questions' in r:r['question_count']=len(r.pop('questions'))
    if r.get('check'):
        check=dict(r['check']);counts={}
        for issue in check.get('issues',[]):
            key=(issue.get('code'),issue.get('severity'));counts[key]=counts.get(key,0)+1
        check['issues']=[{'code':c,'severity':s,'count':n} for (c,s),n in counts.items()];r['check']=check
    result['result']=r
    return result


def render_bundle(metadata,pdf_path,out):
    import pymupdf
    from PIL import Image,ImageDraw
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest()!=metadata.get('source_pdf_sha256'):
        raise ValueError('source_pdf_hash_mismatch')
    out.mkdir(parents=True,exist_ok=True);os.chmod(out,0o700)
    frames=metadata['frames'];start=metadata['reference_start'];count=metadata['pages_per_paper']
    images=[];files=[]
    with pymupdf.open(pdf_path) as doc:
        if start+count>len(doc):raise ValueError('reference_page_out_of_range')
        # Each original page is decoded exactly once; every crop uses that image.
        for relative in range(count):
            pix=doc[start+relative].get_pixmap(matrix=pymupdf.Matrix(2,2))
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            marked=image.copy();draw=ImageDraw.Draw(marked)
            for f in frames:
                for region in f['regions']:
                    if region['page']!=relative:continue
                    b=region['bbox'];box=(round(b[0]*image.width),round(b[1]*image.height),round(b[2]*image.width),round(b[3]*image.height))
                    draw.rectangle(box,outline='#e00000',width=3)
                    draw.text((box[0]+3,box[1]+3),f['label'],fill='#d00000',stroke_width=1,stroke_fill='white')
                    crop=image.crop(box);crop.thumbnail((600,230));images.append((f['label'],crop))
            path=out/f'reference-page-{relative+1}.png';marked.save(path);files.append(path.name)
    if images:
        sheet=Image.new('RGB',(1240,270*((len(images)+1)//2)),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for i,(label,image) in enumerate(images):
            x=(i%2)*620;y=(i//2)*270;draw.text((x+10,y+5),label,fill='black');sheet.paste(image,(x+10,y+25))
        sheet.save(out/'contact-sheet.png');files.append('contact-sheet.png')
    manifest={**metadata,'reviewed':False,'image_files':files,'decoded_pages':count,'crop_count':len(images)}
    atomic_json(out/'review.json',manifest)
    return {'manifest':str(out/'review.json'),'images':files,'decoded_pages':count,'crops':len(images),'reviewed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True);parser.add_argument('--batch-id',required=True)
    parser.add_argument('--browser-session',required=True)
    parser.add_argument('--wrapper',default=str(Path.home()/'.codex/skills/playwright/scripts/playwright_cli.sh'))
    parser.add_argument('--timeout',type=int,default=45);parser.add_argument('--interval',type=int,default=5)
    parser.add_argument('--checkpoint',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verbose',action='store_true')
    sub=parser.add_subparsers(dest='action',required=True)
    for name in ('inspect','check','diagnose','usage'):sub.add_parser(name)
    p=sub.add_parser('run');p.add_argument('--plan',type=Path)
    p.add_argument('--review-pdf',type=Path);p.add_argument('--review-out',type=Path)
    p.add_argument('--follow',action='store_true');p.add_argument('--max-seconds',type=int,default=600)
    p=sub.add_parser('snapshot');p.add_argument('--output',type=Path,dest='snapshot_output')
    p=sub.add_parser('frames');p.add_argument('--edits',type=Path,required=True);p.add_argument('--confirm',action='store_true')
    p=sub.add_parser('associate');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('review');p.add_argument('--pdf',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('retry-precut');p.add_argument('--page',type=int,required=True);p.add_argument('--frame-revision',required=True)
    p=sub.add_parser('evidence');p.add_argument('--paper-id',required=True);p.add_argument('--question-id',action='append')
    p=sub.add_parser('responses');p.add_argument('--plan',type=Path,required=True)
    args=parser.parse_args();args.base_url=args.base_url.rstrip('/')
    url=urlsplit(args.base_url)
    if url.scheme not in ('http','https') or not url.netloc or url.path or url.username or url.password or url.query or url.fragment:
        parser.error('base-url must be an origin')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',args.batch_id):parser.error('invalid batch id')
    if not 1<=args.timeout<=180 or not 2<=args.interval<=30:parser.error('invalid timeout/interval')
    if args.action=='run' and bool(args.review_pdf)!=bool(args.review_out):parser.error('review-pdf and review-out must be provided together')
    if args.action=='run' and not 1<=args.max_seconds<=3600:parser.error('max-seconds 1..3600')
    try:
        plan_path=getattr(args,'plan',None) or getattr(args,'edits',None)
        plan=json.loads(plan_path.read_text()) if plan_path else None
        if args.action=='retry-precut':plan={'page':args.page,'frame_revision':args.frame_revision}
        if args.action=='evidence':plan={'paper_id':args.paper_id,'question_ids':args.question_id}
        started=time.monotonic()
        data=execute(args,'snapshot' if args.action=='review' else args.action,plan)
        if args.action=='run' and args.follow:
            calls=list(data.get('calls',[]));transitions=list(data.get('transitions',[]))
            while data.get('ok') and data.get('result',{}).get('outcome')=='waiting' and time.monotonic()-started<args.max_seconds:
                print(json.dumps({'outcome':'waiting','analysis_status':data['result'].get('analysis_status'),
                                  'elapsed_seconds':round(time.monotonic()-started,1)},ensure_ascii=False),file=sys.stderr,flush=True)
                data=execute(args,'run',plan,data.get('checkpoint'))
                calls.extend(data.get('calls',[]));transitions.extend(data.get('transitions',[]))
            data['calls']=calls;data['transitions']=transitions
            data['follow_seconds']=round(time.monotonic()-started,3)
            data['wall_seconds']=round(time.monotonic()-started,3)
        if args.action=='run' and args.review_pdf and data.get('ok') and data['result'].get('review'):
            data['result']['review_bundle']=render_bundle(data['result']['review'],args.review_pdf,args.review_out)
        if args.action=='review' and data.get('ok'):data['result']=render_bundle(data['result'],args.pdf,args.out)
        if args.action=='snapshot' and args.snapshot_output and data.get('ok'):
            atomic_json(args.snapshot_output,data['result']);data['snapshot_file']=str(args.snapshot_output)
    except Exception as exc:
        data={'ok':False,'error':{'code':str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalnum() else 'local_execution_failed'}}
    if args.output:
        atomic_json(args.output,data)
    shown=data if args.verbose else compact(data)
    if args.output:shown={**shown,'output_file':str(args.output)}
    print(json.dumps(shown,ensure_ascii=False))
    return 0 if data.get('ok') else 1


if __name__=='__main__':sys.exit(main())
