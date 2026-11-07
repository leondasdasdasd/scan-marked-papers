#!/usr/bin/env python3
"""Browser-session transport; isolated authentication is transferred in memory."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

JS = r"""async (input) => {
  if (location.origin !== input.origin) throw Error('origin_mismatch');
  const calls = [];
  async function api(method, path, body) {
    if(input.api)return input.api(method,path,body);
    const started = performance.now();
    const response = await fetch(path, {method, credentials:'same-origin', redirect:'error',
      headers: body === undefined ? {} : {'Content-Type':'application/json'},
      ...(body === undefined ? {} : {body:JSON.stringify(body)}), signal:AbortSignal.timeout(45000)});
    calls.push({method,path,status:response.status,ms:Math.round(performance.now()-started)});
    if (!response.ok) {const error=new Error('api_error'); error.status=response.status; throw error;}
    return await response.json();
  }
  const B = '/api/batches/' + input.batch;
  let batchPaperIds=[],batchLeafIds=[];
  const cleanCheck = d => ({ready:d.ready===true,status:d.status,counts:d.counts,
    ...Object.fromEntries(['selected_paper_ids','skipped_paper_ids','eligible_paper_ids'].filter(k=>Array.isArray(d[k])).map(k=>[k,d[k]])),
    ...(Array.isArray(d.excluded_papers)?{excluded_papers:d.excluded_papers.map(p=>({paper_id:p.paper_id,index:p.index,code:p.code}))}:{}),
    issues:(d.issues||[]).map(x=>({code:x.code,severity:x.severity,
      ...(x.paper_id?{paper_id:x.paper_id}:{}),...(x.question_id?{question_id:x.question_id}:{}),
      ...(x.question_label?{question_label:x.question_label}:{}),...(x.id?{id:x.id}:{}),
      ...(x.message?{message:String(x.message).slice(0,500)}:{}),...(x.action?{action:x.action}:{})})),source_version:d.source_version});
  const compact = d => ({id:d.id,status:d.status,stage:d.stage,scan_phase:d.scan_phase,
    revision:d.revision,
    frame_revision:d.frame_revision,catalog_revision:d.catalog_revision,
    reference_student_id:d.reference_student_id,
    total_pages:d.total_pages,pages_per_paper:d.pages_per_paper,
    students:(d.students||[]).map(s=>({id:s.id,index:s.index,start:s.start,status:s.status})),
    question_count:(d.questions||[]).length,
    frame_count:(d.frames||[]).length,
    stale:!!d.stale,has_error:!!(d.error||d.catalog_error)});
  async function inspect() {
    const [batch,a,roster] = await Promise.all([input.snapshot?.batch||api('GET',B),
      input.snapshot?.analysis||api('GET',B+'/analysis?view=summary'),api('GET',B+'/roster')]);
    const questions=a.questions||[];
    const parents=new Set(questions.map(q=>q.parent_id).filter(Boolean));
    const leaves=questions.filter(q=>!parents.has(q.id));
    const expected=new Set(batch.students.map(s=>s.id));
    batchPaperIds=[...expected];
    const seen=new Set(),duplicates=[],counts={};
    let answers=0,duplicate_answers=0,unexpected_answers=0;
    const expectedPairs=new Set();
    const ids=new Set(leaves.map(q=>q.id));
    batchLeafIds=[...ids];
    for(const s of a.students||[]) {
      if(seen.has(s.id)) duplicates.push(s.id);
      seen.add(s.id);
      const qids=new Set();
      for(const answer of s.answers||[]) {
        const id=answer.question_id||answer.id;
        if(!ids.has(id)) {unexpected_answers++;continue;}
        if(qids.has(id)) duplicate_answers++;
        qids.add(id);answers++;
        if(expected.has(s.id))expectedPairs.add(JSON.stringify([s.id,id]));
        const verdict=answer.verdict||'unknown';counts[verdict]=(counts[verdict]||0)+1;
      }
    }
    const expectedAnswers=leaves.length?expected.size*leaves.length:null;
    const missing=expectedAnswers===null?null:expectedAnswers-expectedPairs.size;
    const studentStateCounts={},failedAnalysisPapers=[];
    for(const paperId of expected){
      const state=a.scan_student_states?.[paperId]||'unknown';studentStateCounts[state]=(studentStateCounts[state]||0)+1;
      if(state==='failed')failedAnalysisPapers.push(paperId);
    }
    const unlinked=(roster.papers||[]).filter(p=>!p.student_id).map(p=>({paper_id:p.id,index:p.index,
      pdf_pages:[Number(p.start)+1,Number(p.start)+Number(batch.pages_per_paper)],status:p.status}));
    const rosterIds=(roster.papers||[]).map(p=>p.id);
    const rosterCoverage=rosterIds.length===expected.size&&new Set(rosterIds).size===expected.size&&rosterIds.every(id=>expected.has(id));
    const missing_papers=[...expected].filter(id=>!seen.has(id));
    const unexpected_papers=[...seen].filter(id=>!expected.has(id));
    const complete=a.status==='completed'&&!a.stale&&new Set(questions.map(q=>q.id)).size===questions.length&&
      expected.size>0&&rosterCoverage&&leaves.length>0&&!missing_papers.length&&
      !unexpected_papers.length&&!duplicates.length&&!missing&&!duplicate_answers&&!unexpected_answers;
    return {batch_id:batch.id,workflow_mode:batch.workflow_mode,analysis_status:a.status,stale:!!a.stale,
      papers:expected.size,covered_papers:[...expected].filter(id=>seen.has(id)).length,leaf_questions:leaves.length,
      expected_answers:expectedAnswers,answers,verdicts:counts,student_state_counts:studentStateCounts,
      failed_analysis_papers:failedAnalysisPapers,
      missing_answers:missing,duplicate_answers,unexpected_answers,missing_papers,unexpected_papers,
      duplicate_papers:duplicates,unlinked,roster_coverage_complete:rosterCoverage,structure_complete:complete,
      visual_review_performed:false,full_accuracy_verified:false,
      link:input.origin+'/exams/'+input.batch+'/analysis'};
  }
  try {
    let result;
    if(input.action==='inspect') result=await inspect();
    else if(input.action==='check'||input.action==='diagnose') {
      const summary=await inspect();
      const cfg=await api('GET',B+'/lesson-practice/config');
      if(!cfg.config||!Number.isInteger(cfg.config.revision)) throw Error('config_revision_missing');
      const allIds=new Set(batchPaperIds);
      const selected=cfg.config.selected_paper_ids;
      const scopeComplete=selected===null||selected===undefined||
        (Array.isArray(selected)&&selected.length===allIds.size&&new Set(selected).size===allIds.size&&selected.every(id=>allIds.has(id)));
      let check=await api('POST',B+'/lesson-practice/preflight',{
        revision:cfg.config.revision,allow_pending_formula_protocol:false});
      const eligibleIds=batchPaperIds.filter(id=>!summary.unlinked.some(p=>p.paper_id===id));
      const exactIds=(value,wanted)=>Array.isArray(value)&&value.length===wanted.length&&
        new Set(value).size===value.length&&value.every(id=>wanted.includes(id));
      const eligibleSelection=d=>input.skip_unlinked===true&&summary.unlinked.length>0&&eligibleIds.length>0&&
        exactIds(d.selected_paper_ids,eligibleIds)&&exactIds(d.skipped_paper_ids,summary.unlinked.map(p=>p.paper_id))&&
        Array.isArray(d.excluded_papers)&&d.excluded_papers.length===summary.unlinked.length&&
        exactIds(d.excluded_papers.map(p=>p.paper_id),summary.unlinked.map(p=>p.paper_id))&&
        d.excluded_papers.every(p=>p.code==='STUDENT_UNLINKED')&&
        d.counts?.students===eligibleIds.length&&d.counts?.skippedPapers===summary.unlinked.length;
      const eligibleCoverage=d=>eligibleSelection(d)&&d.counts?.gradableQuestions===summary.leaf_questions&&d.counts?.questionResults===eligibleIds.length*summary.leaf_questions;
      const mediaCodes=['MEDIA_CHECK_PENDING','MEDIA_PENDING','MEDIA_NOT_READY','QUESTION_ASSET_INVALID'];
      const eligiblePreparation=d=>{
        if(!eligibleSelection(d))return false;
        const pending=(d.issues||[]).filter(i=>i.severity==='pending');
        if(pending.some(i=>!mediaCodes.includes(i.code)))return false;
        if(eligibleCoverage(d))return true;
        const questions=new Set(pending.filter(i=>i.code==='QUESTION_ASSET_INVALID').map(i=>i.question_id));
        const count=d.counts?.gradableQuestions;
        return Number.isInteger(count)&&count>=0&&count<summary.leaf_questions&&
          questions.size===summary.leaf_questions-count&&[...questions].every(id=>batchLeafIds.includes(id))&&
          d.counts?.questionResults===eligibleIds.length*count;
      };
      const started=performance.now();
      const deadline=input.deadline??started+input.timeout*1000;
      let preparationStatus=null;
      const mediaPending=(check.issues||[]).some(i=>['MEDIA_CHECK_PENDING','MEDIA_PENDING','MEDIA_NOT_READY','QUESTION_ASSET_INVALID'].includes(i.code)&&i.severity==='pending');
      const hardFailure=(check.issues||[]).some(i=>['blocker','failure'].includes(i.severity));
      if(input.prepare && check.ready!==true && mediaPending && !hardFailure && scopeComplete && summary.structure_complete &&
        (!summary.unlinked.length||eligiblePreparation(check))) {
        const existing=await api('GET',B+'/lesson-practice/progress');
        if(existing.preparation?.status!=='running')
          await api('POST',B+'/lesson-practice/progress/start',{revision:cfg.config.revision});
        do {
          const p=await api('GET',B+'/lesson-practice/progress');
          const state=p.preparation?.status;preparationStatus=state||null;
          if(state==='awaiting_confirmation') {
            break;
          }
          if(['blocked','failed','paused'].includes(state)||performance.now()>=deadline) break;
          await new Promise(resolve=>setTimeout(resolve,Math.min(input.interval*1000,Math.max(0,deadline-performance.now()))));
        }while(performance.now()<deadline);
        const latest=await api('GET',B+'/lesson-practice/config');
        check=await api('POST',B+'/lesson-practice/preflight',{
          revision:latest.config.revision,allow_pending_formula_protocol:false});
      }
      const coverageMatches=check.counts?.students===summary.papers&&
        check.counts?.questionResults===summary.answers&&check.counts?.gradableQuestions===summary.leaf_questions&&
        check.counts?.skippedPapers===0;
      const ready=check.ready===true&&scopeComplete&&coverageMatches&&
        check.status==='awaiting_confirmation'&&summary.structure_complete&&!summary.unlinked.length&&
        !(check.issues||[]).some(i=>['pending','blocker','failure'].includes(i.severity));
      const eligibleReady=eligibleCoverage(check)&&check.ready===true&&scopeComplete&&summary.structure_complete&&
        check.status==='awaiting_confirmation'&&!(check.issues||[]).some(i=>['pending','blocker','failure'].includes(i.severity));
      const remaining=[];
      if(summary.analysis_status!=='completed'||summary.stale)remaining.push({code:'ANALYSIS_INCOMPLETE',analysis_status:summary.analysis_status});
      if(summary.failed_analysis_papers.length)remaining.push({code:'ANALYSIS_FAILED_PAPERS',count:summary.failed_analysis_papers.length});
      if(summary.unlinked.length)remaining.push({code:'IDENTITY_PENDING',count:summary.unlinked.length});
      if(!summary.structure_complete)remaining.push({code:'STRUCTURE_INCOMPLETE'});
      if(!scopeComplete)remaining.push({code:'SCOPE_INCOMPLETE'});
      if(!coverageMatches)remaining.push({code:'CHECK_COVERAGE_MISMATCH'});
      const pendingMedia=(check.issues||[]).some(i=>['MEDIA_CHECK_PENDING','MEDIA_PENDING','MEDIA_NOT_READY','QUESTION_ASSET_INVALID'].includes(i.code)&&i.severity==='pending');
      const blockedMedia=(check.issues||[]).some(i=>['blocker','failure'].includes(i.severity)&&
        (i.action==='prepare_media'||['MEDIA_CHECK_PENDING','MEDIA_PENDING','MEDIA_NOT_READY','QUESTION_ASSET_INVALID'].includes(i.code)));
      for(const issue of check.issues||[]){
        if(!['blocker','failure','pending'].includes(issue.severity))continue;
        const prior=remaining.find(i=>i.code===issue.code&&i.severity===issue.severity);
        if(prior)prior.count++;else remaining.push({code:issue.code,severity:issue.severity,count:1});
      }
      result={...summary,scope_complete:scopeComplete,check_coverage_matches:coverageMatches,
        ...(input.skip_unlinked===true?{eligible_check:{ready:ready||eligibleReady,
          coverage_verified:summary.structure_complete&&(coverageMatches||eligibleCoverage(check)),papers:eligibleIds.length,
          expected_answers:summary.leaf_questions?eligibleIds.length*summary.leaf_questions:null,
          skipped:summary.unlinked.map(p=>({...p,reason:'identity_unconfirmed'})),
          full_batch_ready:ready,scope_persisted:false}}:{}),
        completion:{analysis_completed:summary.analysis_status==='completed'&&!summary.stale,
          structure_verified:summary.structure_complete,identity_complete:summary.unlinked.length===0&&summary.roster_coverage_complete,
          media_pending:pendingMedia,media_blocked:blockedMedia,preflight_passed:ready},remaining,
        preparation_status:preparationStatus,waiting_for_media:preparationStatus==='running'&&pendingMedia&&
          scopeComplete&&(coverageMatches||eligiblePreparation(check))&&summary.structure_complete&&
          (!summary.unlinked.length||eligiblePreparation(check))&&
          !(check.issues||[]).some(i=>['blocker','failure'].includes(i.severity)),
        check:cleanCheck(check),ready,
        outcome:ready?'ready':eligibleReady?'ready_with_skips':!scopeComplete?'coverage_gap':summary.unlinked.length?'identity_pending':!coverageMatches?'coverage_gap':
          (check.issues||[]).some(i=>['blocker','failure'].includes(i.severity))?'blocked':'pending',
        stopped_at:'preflight',submitted:false};
    } else if(input.action==='watch') {
      const started=performance.now();let state;
      do {
        state=await api('GET',B+'/analysis/status');
        if(['completed','partial','failed','awaiting_frames','awaiting_confirmation'].includes(state.status))break;
        if(performance.now()-started>=input.timeout*1000)break;
        await new Promise(resolve=>setTimeout(resolve,input.interval*1000));
      }while(true);
      result=compact(state);
      result.timed_out=!['completed','partial','failed','awaiting_frames','awaiting_confirmation'].includes(state.status);
    } else if(input.action==='request') {
      result=compact(await api(input.method,input.path,input.body));
    } else if(input.action==='session') {
      const d=await api('GET','/api/session?refresh_profile=false');
      result={authenticated:!!d.user,teacher:['employee','teacher'].includes(d.user?.identity),
        models:Object.fromEntries(Object.entries(d.models||{}).map(([k,v])=>[k,{configured:v.configured,workflows:v.workflows}]))};
    }
    return {ok:true,result,calls};
  } catch(error) {return {ok:false,error:{code:error.code||(['origin_mismatch','config_revision_missing'].includes(error.message)?error.message:'request_failed'),status:error.status||null,...(error.details||{})},calls};}
}"""


DEFAULT_ORIGIN = 'https://piyue.yungu.org'


def browser_options(parser):
    parser.add_argument('--playwright-cli',type=Path)
    parser.add_argument('--browser-backend', choices=('playwright','agent-browser','isolated'), default='playwright')
    parser.add_argument('--browser-executable', default='agent-browser')


def browser(args, code, expression=None):
    started = time.perf_counter()
    import paperflow_session
    if getattr(args, 'browser_backend', 'playwright') == 'isolated' or paperflow_session.available(args):
        if expression is None:
            return {'ok':False,'error':{'code':'isolated_expression_required'}}
        return paperflow_session.invoke(args, 'execute', expression)
    if getattr(args, 'browser_backend', 'playwright') == 'agent-browser':
        if expression is None:
            return {'ok':False,'error':{'code':'upload_requires_native_browser_file_tool'}}
        proc = subprocess.run([args.browser_executable, '--session', args.browser_session,
                               '--json', 'eval', '--stdin'], input=expression,
                              capture_output=True, text=True, timeout=args.timeout+65)
        try:
            envelope=json.loads(proc.stdout)
            if not isinstance(envelope,dict):
                raise ValueError('invalid envelope')
            if proc.returncode or envelope.get('success') is not True:
                return {'ok':False,'error':{'code':'browser_command_failed'}}
            data=envelope['data']['result']
            if not isinstance(data,dict) or type(data.get('ok')) is not bool:
                raise ValueError('invalid result')
        except (ValueError,KeyError,TypeError):
            return {'ok':False,'error':{'code':'invalid_browser_response'}}
        data['wall_seconds']=round(time.perf_counter()-started,3)
        return data
    cli = getattr(args, 'playwright_cli', None)
    if cli:
        node = shutil.which('node')
        if not node or not cli.is_file():
            return {'ok':False,'error':{'code':'existing_playwright_cli_unavailable'}}
        command = [node, str(cli), '-s='+args.browser_session, 'run-code']
    else:
        command = [args.wrapper, '-s='+args.browser_session, 'run-code']
    if len(code.encode('utf-8')) > 96 * 1024:
        # The Docker wrapper mounts the current workspace, not the host /tmp.
        # Avoid Linux's per-argument limit without exposing student data in argv.
        with tempfile.TemporaryDirectory(prefix='.paperflow-browser-', dir=Path.cwd()) as directory:
            code_file = Path(directory) / 'operation.js'
            code_file.write_text(code, encoding='utf-8')
            code_file.chmod(0o600)
            proc = subprocess.run(command+['--filename', str(code_file)],
                                  capture_output=True, text=True, timeout=args.timeout+65)
    else:
        proc = subprocess.run(command+[code], capture_output=True, text=True, timeout=args.timeout+65)
    match = re.search(r'### Result\s*\n(.*?)(?=\n### |\Z)', proc.stdout, re.S)
    if not match:
        return {'ok':False,'error':{'code':'browser_command_failed'},'wall_seconds':round(time.perf_counter()-started,3)}
    try:
        data = json.loads(match[1])
    except ValueError:
        return {'ok':False,'error':{'code':'invalid_browser_response'}}
    data['wall_seconds']=round(time.perf_counter()-started,3)
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',default=DEFAULT_ORIGIN)
    p.add_argument('--batch-id',default='')
    p.add_argument('--browser-session',required=True)
    p.add_argument('--wrapper',default=str(Path.home()/'.codex/skills/playwright/scripts/playwright_cli.sh'))
    browser_options(p)
    p.add_argument('--timeout',type=int,default=45)
    p.add_argument('--interval',type=int,default=5)
    sub=p.add_subparsers(dest='action',required=True)
    for name in ('session','inspect','watch'): sub.add_parser(name)
    c=sub.add_parser('check');c.add_argument('--prepare',action='store_true')
    r=sub.add_parser('request');r.add_argument('--method',choices=['GET','POST','PUT','PATCH'],default='GET');r.add_argument('--path',required=True);r.add_argument('--body-file',type=Path)
    u=sub.add_parser('upload');u.add_argument('--file',type=Path,required=True);u.add_argument('--pages-per-paper',type=int,required=True);u.add_argument('--key',required=True);u.add_argument('--model',default='qwen3.8-max')
    args=p.parse_args()
    url=urlsplit(args.base_url)
    if url.scheme not in ('http','https') or not url.netloc or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
        p.error('base-url must be an origin')
    if not 1<=args.timeout<=180 or not 2<=args.interval<=30:p.error('timeout 1..180, interval 2..30')
    if args.action not in ('session','upload') and not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',args.batch_id):p.error('invalid batch-id')
    payload={'action':args.action,'origin':args.base_url.rstrip('/'),'batch':args.batch_id,
             'timeout':args.timeout,'interval':args.interval,'prepare':getattr(args,'prepare',False)}
    if args.action=='request':
        b='/api/batches/'+args.batch_id
        allowed_get={b,b+'/analysis?view=summary',b+'/analysis?view=catalog',b+'/analysis/status',b+'/roster',b+'/lesson-practice/config',b+'/lesson-practice/progress'}
        allowed={'GET':allowed_get,'POST':{b+'/analysis',b+'/analysis/frames/confirm'},
                 'PATCH':{b+'/analysis/frames'},'PUT':{b+'/roster',b+'/lesson-practice/config'}}
        if args.path not in allowed[args.method]:p.error('method/path is not in the experiment allowlist')
        payload.update(method=args.method,path=args.path)
        if args.body_file:payload['body']=json.loads(args.body_file.read_text())
    if args.action=='upload':
        if not args.file.is_file() or not 1<=args.pages_per_paper<=12:p.error('invalid PDF or split')
        # The browser opens only this explicitly selected local file. No auth export.
        setup=json.dumps({'origin':payload['origin'],'key':args.key,'pages':args.pages_per_paper,'model':args.model})
        code='''async(page)=>{
          const input='''+setup+''';
          if(await page.evaluate(()=>location.origin)!==input.origin)return {ok:false,error:{code:'origin_mismatch'}};
          await page.evaluate(()=>{const old=document.getElementById('paperflow-input');if(old)old.remove();const e=document.createElement('input');e.type='file';e.id='paperflow-input';e.hidden=true;document.body.appendChild(e);});
          try {
            await page.locator('#paperflow-input').setInputFiles('''+json.dumps(str(args.file.resolve()))+''');
            return await page.evaluate(async input=>{
              const f=document.getElementById('paperflow-input').files[0];const data=new FormData();data.append('file',f);
              data.append('pages_per_paper',input.pages);data.append('workflow_mode','scan');data.append('llm_model',input.model);
              const response=await fetch('/api/batches',{method:'POST',body:data,credentials:'same-origin',redirect:'error',headers:{'Idempotency-Key':input.key},signal:AbortSignal.timeout(45000)});
              if(!response.ok)return {ok:false,error:{code:'upload_failed',status:response.status}};
              const b=await response.json();return {ok:true,result:{batch_id:b.id,total_pages:b.total_pages,pages_per_paper:b.pages_per_paper,students:b.students.map(s=>({id:s.id,index:s.index,start:s.start})),workflow_mode:b.workflow_mode}};
            },input);
          }finally{await page.evaluate(()=>document.getElementById('paperflow-input')?.remove());}
        }'''
    else:
        code='async(page)=>await page.evaluate(('+JS+'),'+json.dumps(payload,ensure_ascii=False)+')'
    expression=None if args.action=='upload' else '('+JS+')('+json.dumps(payload,ensure_ascii=False)+')'
    try:data=browser(args,code,expression)
    except (OSError,subprocess.TimeoutExpired):data={'ok':False,'error':{'code':'transport_timeout_read_state_before_retry'}}
    print(json.dumps(data,ensure_ascii=False))
    return 0 if data.get('ok') else 1


if __name__=='__main__':sys.exit(main())
