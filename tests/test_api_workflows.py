"""Additional full-workflow boundaries; isolated synthetic API responses only."""
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_workflow as baseline
import paperflow

EXTRA=r'''
const reply=(value,status=200)=>({ok:status<400,status,json:async()=>clone(value)});
const ev={evidence_confirmed:true,evidence_note:'Observed synthetic evidence'};
function hook(w,routes){const old=global.fetch;global.fetch=async(path,o)=>{
 const matched=await routes(path,o);return matched===undefined?old(path,o):reply(matched);
};}
function gradingWorld(engine='xueersi'){
 const w=world();w.batch.workflow_mode='grading';w.batch.grading_engine=engine;w.batch.has_answer_paper=engine==='llm';
 w.batch.status='uploaded';w.batch.students.forEach(s=>s.status='pending');w.gradingStarts=0;w.retries=[];
 w.progress={status:'uploaded'};w.tasks={};
 hook(w,async(path,o)=>{
  if(path===B+'/live-state')return {progress:w.progress,task_control:w.tasks,analysis_status:w.a};
  if(path===B+'/start'){assert.equal(o.body,undefined);w.gradingStarts++;w.progress.status='grading';w.tasks.grading={status:'running'};return {ok:true};}
  if(path.endsWith('/retry')&&path.startsWith(B+'/students/')){assert.equal(o.body,undefined);w.retries.push(path.split('/')[5]);w.tasks.grading={status:'running'};return {ok:true};}
 });return w;
}
test('class discovery works before upload without touching DOM',async()=>{
 const w=world();let gets=0;
 hook(w,async(path,o)=>{if(path==='/api/classroom/classes'){gets++;assert.equal(o.method,'GET');return {semester_id:'7',classes:[{id:'47071',name:'G7 C1'}]};}});
 const d=await main(input('classes',{batch:''}));assert(d.ok);assert.equal(d.result.classes[0].id,'47071');assert.equal(gets,1);assert.equal(w.trace.length,0);
});
test('general directory and roster preview send exact permitted scope parameters',async()=>{
 world();let seen=[];global.fetch=async(path,o)=>{seen.push(path);assert.equal(o.method,'GET');return reply({classes:[],students:[]});};
 let d=await main(input('classes',{batch:'',plan:{source:'general',grade:'7',subject_id:'50',course_id:'99'}}));assert(d.ok);
 d=await main(input('class-students',{batch:'',plan:{class_id:'47071',source:'general',grade:'7',subject_id:'50',course_id:'99'}}));assert(d.ok);
 assert.equal(seen[0],'/api/classroom/general-options?grade=7&subject_id=50&course_id=99');
 assert.equal(seen[1],'/api/classroom/classes/47071/students?source=general&grade=7&subject_id=50&course_id=99');
});
test('scope binding is one versioned save with authoritative readback',async()=>{
 const w=world();const d=await main(input('scope',{plan:{...ev,revision:1,semester_id:'1',class_ids:['3'],scope:{source:'teaching'}}}));
 assert(d.ok);assert.equal(d.result.roster.revision,2);assert.deepEqual(d.result.roster.classes,[{id:'3'}]);assert.equal(w.trace.filter(([m])=>m==='PUT').length,1);
});
test('named operations reject unknown routes and query injection before network',async()=>{
 const w=world();let d=await main(input('api-call',{plan:{operation:'not-real'}}));assert.equal(d.error.code,'unknown_operation');
 d=await main(input('api-call',{plan:{operation:'classes',query:{redirect:'https://elsewhere.test'}}}));assert.equal(d.error.code,'invalid_query_field');assert.equal(w.trace.length,0);
 d=await main(input('api-call',{plan:{operation:'student',params:{sid:'../../another'}}}));assert.equal(d.error.code,'invalid_route_parameter');assert.equal(w.trace.length,0);
});
test('generic versioned review takes runtime token and strips it from output',async()=>{
 const w=world();w.finish();w.a.read_version='read-v1';w.a.review_token='version:read-v1';let saves=0;
 hook(w,async(path,o)=>{if(path===B+'/analysis/students/p1/questions/first'){
  assert.equal(o.method,'PATCH');const body=JSON.parse(o.body);assert.equal(body.review_token,'version:read-v1');assert.equal(body.verdict,'incorrect');
  saves++;return {...w.a,review_token:'runtime-private-new'};
 }});
 const d=await main(input('api-call',{plan:{...ev,operation:'question-review',params:{sid:'p1',qid:'first'},expected:{read_version:'read-v1'},body:{verdict:'incorrect',verdict_only:true}}}));
 assert(d.ok);assert.equal(saves,1);assert(!JSON.stringify(d.result).includes('runtime-private-new'));assert(!JSON.stringify(d.result).includes('review_token'));
});
test('stale or user-supplied review tokens never write',async()=>{
 const w=world();w.finish();w.a.read_version='new';w.a.review_token='private';
 const p={...ev,operation:'question-review',params:{sid:'p1',qid:'first'},expected:{read_version:'old'},body:{verdict:'incorrect'}};
 let d=await main(input('api-call',{plan:p}));assert.equal(d.error.code,'review_version_conflict');
 p.body.review_token='injected';d=await main(input('api-call',{plan:p}));assert.equal(d.error.code,'runtime_token_only');assert(w.trace.every(([m])=>m==='GET'));
});
test('catalog confirmation and synchronization require dedicated commands',async()=>{
 const w=world();for(const op of ['import-submit','import-resume','catalog-confirm-and-start']){
 const d=await main(input('api-call',{plan:{...ev,operation:op}}));assert.equal(d.error.code,'dedicated_command_required');}assert.equal(w.trace.length,0);
});
test('quick grading starts once with no body and waits for the original job',async()=>{
 const w=gradingWorld();let d=await main(input('run'));assert(d.ok);assert.equal(d.result.waiting_for,'grading');assert.equal(w.gradingStarts,1);
 d=await main(input('run',{checkpoint:d.checkpoint}));assert(d.ok);assert.equal(d.result.outcome,'waiting');assert.equal(w.gradingStarts,1);
});
test('quick grading reuses frame review and independently split calculations to preflight',async()=>{
 const w=gradingWorld();w.batch.students.forEach(s=>s.status='done');w.progress.status='completed';
 const d=await main(input('run',{plan:{frames:plan(w)}}));assert(d.ok&&d.result.ready);assert.equal(w.gradingStarts,0);assert.equal(w.patches,1);assert.equal(w.a.questions.length,7);assert.equal(d.result.submitted,false);
});
test('quick reference ranking reuses existing reliable verdicts',async()=>{
 const w=gradingWorld();w.batch.students.forEach(s=>s.status='done');w.progress.status='completed';w.a.status='not_generated';
 w.batch.students[0].results=[{verdict:'correct'},{verdict:'incorrect'}];w.batch.students[1].results=[{verdict:'correct'},{verdict:'correct'}];
 const d=await main(input('run'));assert(d.ok);assert.equal(d.result.reference_ranking,'existing_grading_verdicts');assert.equal(d.result.candidates[0].id,'p2');assert.equal(d.result.candidates[0].correct_rate,1);assert.equal(w.starts,0);
});
for(const engine of ['xueersi','doubao','llm'])test(engine+' grading-only starts and resumes to grading without organizing',async()=>{
 const w=gradingWorld(engine);let reads=[];const old=global.fetch;
 global.fetch=async(path,o)=>{reads.push([o.method,path]);return old(path,o);};
 let d=await main(input('run',{stop_after:'grading'}));assert(d.ok);assert.equal(d.result.outcome,'waiting');assert.equal(d.checkpoint.stop_after,'grading');
 w.progress.status='completed';w.tasks.grading={status:'finished'};
 w.batch.students.forEach((s,i)=>{s.status='done';s.results=[{verdict:i?'incorrect':'correct'}];});
 d=await main(input('run',{checkpoint:d.checkpoint}));assert(d.ok);assert.equal(d.result.outcome,'grading_completed');
 assert.equal(d.result.graded_papers,2);assert.equal(d.result.observations,2);assert.deepEqual(d.result.verdicts,{correct:1,incorrect:1});
 assert.equal(d.result.submitted,false);assert.equal(w.gradingStarts,1);assert.equal(d.checkpoint.stop_after,'grading');
 assert(!reads.some(([method,path])=>path.includes('/analysis')||method!=='GET'&&path.includes('/lesson-practice')));
});
test('grading-only reports missing result evidence without retrying done papers',async()=>{
 const w=gradingWorld();w.batch.students.forEach(s=>s.status='done');w.progress.status='completed';
 const d=await main(input('run',{stop_after:'grading'}));assert(d.ok);assert.equal(d.result.outcome,'grading_incomplete');
 assert.deepEqual(d.result.missing_result_papers,['p1','p2']);assert.equal(d.result.grading_complete,false);assert.equal(w.gradingStarts,0);assert.equal(w.starts,0);assert.equal(w.checks,0);
});
test('grading-only preserves uncertain judgments rather than declaring them correct',async()=>{
 const w=gradingWorld('llm');w.batch.students.forEach(s=>{s.status='done';s.judgments=[{verdict:'uncertain'},{}];});w.progress.status='completed';
 const d=await main(input('run',{stop_after:'grading'}));assert(d.ok);assert.equal(d.result.outcome,'grading_completed');
 assert.deepEqual(d.result.verdicts,{uncertain:2,unknown:2});assert.equal(d.result.full_accuracy_verified,false);assert.equal(w.checks,0);
});
test('scan cannot use the grading endpoint or write a scope under a conflicting goal',async()=>{
 const w=world();const d=await main(input('run',{stop_after:'grading',plan:{scope:{...ev,revision:1,semester_id:'1',class_ids:['3'],scope:{source:'teaching'}}}}));
 assert.equal(d.error.code,'grading_endpoint_requires_grading');assert(w.trace.every(([method])=>method==='GET'));assert.equal(w.starts,0);
});
test('an explicit new check endpoint overrides the prior grading-only goal',async()=>{
 const w=gradingWorld();w.batch.students.forEach(s=>s.status='done');w.progress.status='completed';w.a.status='not_generated';
 const d=await main(input('run',{stop_after:'check',checkpoint:{origin:location.origin,batch_id:'test',stop_after:'grading'}}));
 assert(d.ok);assert.equal(d.result.outcome,'needs_reference');assert.equal(d.checkpoint.stop_after,'check');assert.equal(w.checks,0);
});
test('unknown endpoints fail before reading or mutating the batch',async()=>{
 const w=world();const d=await main(input('run',{stop_after:'sync'}));assert.equal(d.error.code,'invalid_stop_after');assert.equal(w.trace.length,0);
});
test('LLM grading uses prepare-analysis without asking for a reference',async()=>{
 const w=gradingWorld('llm');w.batch.students.forEach(s=>s.status='done');w.progress.status='completed';w.a.status='not_generated';let prepares=0;
 hook(w,async(path,o)=>{if(path===B+'/lesson-practice/prepare-analysis'){assert.equal(o.body,undefined);prepares++;w.finish();return w.a;}});
 const d=await main(input('run'));assert(d.ok&&d.result.ready);assert.equal(prepares,1);assert.equal(w.starts,0);assert.equal(w.gradingStarts,0);
});
test('failed grading returns a precise recovery boundary and keeps completed papers',async()=>{
 const w=gradingWorld();w.batch.students[0].status='done';w.batch.students[1].status='failed';w.batch.students[1].error='provider timeout';
 const d=await main(input('run'));assert(d.ok);assert.equal(d.result.outcome,'needs_grading_recovery');assert.equal(d.result.failed[0].paper_id,'p2');assert.equal(w.gradingStarts,0);
});
test('retry plan resumes only remaining failed papers and never regrades done papers',async()=>{
 const w=gradingWorld();w.batch.students[0].status='done';w.batch.students[1].status='failed';
 const d=await main(input('run',{plan:{grading_retry:{...ev,paper_ids:['p1','p2']}}}));assert(d.ok);assert.deepEqual(w.retries,['p2']);assert.equal(w.gradingStarts,0);
});
test('an explicit resume waits for stopping and restarts only after the stop finishes',async()=>{
 const w=gradingWorld();w.tasks.grading={status:'stopping'};
 let d=await main(input('run',{plan:{resume_authorized:true}}));assert(d.ok);assert.equal(d.result.outcome,'waiting');assert.equal(w.gradingStarts,0);
 w.tasks.grading={status:'stopped'};d=await main(input('run',{plan:{resume_authorized:true}}));assert(d.ok);assert.equal(w.gradingStarts,1);
});
test('sync is impossible without current explicit authorization',async()=>{
 const w=world();const d=await main(input('sync',{plan:ev}));assert.equal(d.error.code,'sync_authorization_required');assert.equal(w.trace.length,0);
});
test('explicit synchronization confirms current full-batch version and exact warnings in memory',async()=>{
 const w=world();w.finish();let imports=0;
 w.checkPolicy=()=>({source_version:'sv1',check_token:'runtime-private-check',issues:[{id:'warn-1',code:'JUDGMENT_BINARY_MAPPING',severity:'warning'}]});
 hook(w,async(path,o)=>{if(path===B+'/lesson-practice/imports'&&o.method==='POST'){
 const b=JSON.parse(o.body);assert.equal(b.confirmed_check_token,'runtime-private-check');assert.deepEqual(b.accepted_warning_ids,['warn-1']);imports++;return {id:'attempt1',state:'PENDING'};
 }});
 const p={...ev,reference_reviewed:true,scope_reviewed:true,catalog_reviewed:true,revision:1,source_version:'sv1',accepted_warning_ids:['warn-1']};
 const d=await main(input('sync',{authorize_sync:true,plan:p}));assert(d.ok);assert.equal(d.result.submitted,true);assert.equal(imports,1);assert(!JSON.stringify(d).includes('runtime-private-check'));
});
test('warning changes or uncovered identity stop sync before imports',async()=>{
 const w=world();w.finish();w.checkPolicy=()=>({source_version:'sv1',check_token:'runtime-private-check',issues:[{id:'new-warning',severity:'warning'}]});
 const p={...ev,reference_reviewed:true,scope_reviewed:true,catalog_reviewed:true,revision:1,source_version:'sv1',accepted_warning_ids:[]};
 let d=await main(input('sync',{authorize_sync:true,plan:p}));assert.equal(d.error.code,'check_confirmation_required');
 w.roster.papers[1].student_id=null;d=await main(input('sync',{authorize_sync:true,plan:p}));assert(d.ok&&!d.result.submitted&&!d.result.ready);
 assert(!w.trace.some(([m,path])=>m==='POST'&&path.endsWith('/imports')));
});
function uploadWorld(){
 const w=world();const bytes=Buffer.from('%PDF-1.7 synthetic');const f=new Blob([bytes],{type:'application/pdf'});
 global.crypto=require('node:crypto').webcrypto;global.document={querySelector:()=>({files:[f]})};
 w.uploads=0;w.uploadStatus={status:'not_found'};
 w.uploadPlan={key:'stable-upload-1',sha256:require('node:crypto').createHash('sha256').update(bytes).digest('hex'),size:bytes.length,
  fields:{workflow_mode:'scan',grading_engine:'llm',has_answer_paper:false,pages_per_paper:1,paper_size:'A4',orientation:'portrait',paper_sides:'single'},scope:null};
 hook(w,async(path,o)=>{
  if(path==='/api/uploads/stable-upload-1')return w.uploadStatus;
  if(path==='/api/batches'&&o.method==='POST'){
   assert(o.body instanceof FormData);assert.equal(o.headers['Content-Type'],undefined);assert.equal(o.headers['Idempotency-Key'],'stable-upload-1');
   assert.equal(o.body.get('workflow_mode'),'scan');assert.equal(o.body.get('has_answer_paper'),'false');w.uploads++;w.uploadStatus={status:'completed',batch_id:'test'};return w.batch;
  }
 });return w;
}
test('upload sends FormData and resumes the same batch without uploading twice',async()=>{
 const w=uploadWorld();let d=await main(input('upload',{batch:'',plan:w.uploadPlan}));assert(d.ok);assert.equal(w.uploads,1);assert.equal(d.checkpoint.batch_id,'test');
 d=await main(input('upload',{batch:'',plan:w.uploadPlan,checkpoint:d.checkpoint}));assert(d.ok);assert.equal(d.result.batch_id,'test');assert.equal(w.uploads,1);
});
test('upload rejects a different file and a changed plan before sending bytes',async()=>{
 const w=uploadWorld();w.uploadPlan.sha256='0'.repeat(64);const d=await main(input('upload',{batch:'',plan:w.uploadPlan}));assert.equal(d.error.code,'upload_file_mismatch');assert.equal(w.uploads,0);
});
test('lost upload receipt reads status and never blindly resends unresolved bytes',async()=>{
 const w=uploadWorld(),p=w.uploadPlan;const cp={origin:location.origin,batch_id:'',upload_receipt:{state:'dispatching',signature:JSON.stringify([p.key,p.sha256,p.fields,null])}};
 const d=await main(input('upload',{batch:'',plan:p,checkpoint:cp}));assert(d.ok);assert.equal(d.result.outcome,'upload_uncertain');assert.equal(w.uploads,0);
});
'''

if __name__=='__main__':
    setup=baseline.TESTS.split("test('9 edits")[0]
    runner=baseline.TESTS[baseline.TESTS.index('(async()=>{let failed=0;'):]
    code='const SOURCE='+json.dumps(paperflow.source())+';\n'+setup+EXTRA+runner
    result=subprocess.run(['node','-'],input=code,text=True,capture_output=True)
    print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
    sys.exit(result.returncode)
