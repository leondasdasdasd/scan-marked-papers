"""State-machine contract tests using synthetic responses; no model or network."""
import importlib.util
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'scripts'))
import paperflow

TESTS=r'''
const assert=require('node:assert/strict');
const main=eval('('+SOURCE+')');
global.location={origin:'https://example.test'};
const B='/api/batches/test';
const clone=x=>JSON.parse(JSON.stringify(x));
const frame=(id,label,bbox=[.1,.1,.3,.2])=>({id,label,parent_id:null,source:'manual',regions:[{page:0,bbox}]});
function world(){
 const batch={id:'test',workflow_mode:'scan',pages_per_paper:1,total_pages:2,students:[{id:'p1',index:1,start:0},{id:'p2',index:2,start:1}]};
 const a={status:'awaiting_frames',frame_revision:'r1',source_pdf_sha256:'a'.repeat(64),reference_student_id:'p1',reference_start:0,
   frames:[frame('first','1'),frame('group','2',[.1,.3,.9,.9])],questions:[],students:[]};
 const roster={revision:1,semester_id:'1',scope:{source:'teaching'},classes:[{id:'2'}],students:[{id:'11'},{id:'12'}],
  papers:[{id:'p1',index:1,start:0,student_id:'11'},{id:'p2',index:2,start:1,student_id:'12'}]};
 const w={batch,a,roster,cfg:{config:{revision:1,selected_paper_ids:null}},imports:[],tasks:{},trace:[],patches:0,starts:0,media:0,
   failAssociation:null,associationAttempts:[],badComposite:false,checks:0,checkPolicy:null,progressQueue:[]};
 function finish(){
  a.status='completed';a.questions=a.frames.map(f=>({...clone(f),conversion_status:'converted'}));
  if(w.badComposite)a.questions[1].content={children:[{id:'hidden-child'}]};
  a.students=batch.students.map(s=>({id:s.id,answers:a.questions.map(q=>({question_id:q.id,verdict:'correct'}))}));
 }
 w.finish=finish;
 global.fetch=async(path,options)=>{
  const method=options.method;const body=options.body?JSON.parse(options.body):null;
  w.trace.push([method,path]);let value,status=200;
  if(path===B+'/lesson-practice/imports?check_source=false')value={items:w.imports};
  else if(path===B+'/task-control')value=w.tasks;
  else if(path===B&&method==='GET')value=batch;
  else if(path.startsWith(B+'/analysis?')||path===B+'/analysis/status')value=a;
  else if(path===B+'/analysis'&&method==='POST'){w.starts++;a.status='awaiting_frames';value=a;}
  else if(path===B+'/analysis/frames'&&method==='PATCH'){
   assert.equal(body.frame_revision,a.frame_revision);a.frames=clone(body.frames);a.frame_revision='r'+(++w.patches+1);value=a;
  }else if(path===B+'/analysis/frames/confirm'&&method==='POST'){finish();value={status:a.status};}
  else if(path===B+'/roster'&&method==='GET')value=roster;
  else if(path===B+'/roster'&&method==='PUT'){
   assert.equal(body.revision,roster.revision);Object.assign(roster,{...body,classes:body.class_ids.map(id=>({id})),revision:roster.revision+1});value=roster;
  }else if(path.startsWith(B+'/roster/')&&method==='PATCH'){
   const pid=path.split('/').pop();w.associationAttempts.push(pid);
   if(w.failAssociation===pid){status=409;value={};}
   else{assert.equal(body.revision,roster.revision);roster.papers.find(p=>p.id===pid).student_id=body.student_id;roster.revision++;value=roster;}
  }else if(path===B+'/lesson-practice/config')value=w.cfg;
  else if(path===B+'/lesson-practice/preflight'){
   const linked=roster.papers.filter(p=>p.student_id).length;
   value={ready:true,status:'awaiting_confirmation',issues:[],counts:{students:linked,skippedPapers:2-linked,
    gradableQuestions:a.questions.length,questionResults:linked*a.questions.length}};
   w.checks++;if(w.checkPolicy)Object.assign(value,w.checkPolicy(w.checks));
  }else if(path===B+'/lesson-practice/progress/start'){w.media++;value={};}
  else if(path===B+'/lesson-practice/progress')value={preparation:{status:w.progressQueue.shift()||'awaiting_confirmation'}};
  else throw Error('Unexpected request '+method+' '+path);
  const captured=clone(value);return {ok:status<400,status,json:async()=>captured};
 };
 return w;
}
function plan(w){
 return {operation_id:'review-1',frame_revision:w.a.frame_revision,source_pdf_sha256:w.a.source_pdf_sha256,
 reference_student_id:'p1',reference_reviewed:true,scope_reviewed:true,reviewed_pages:[0],
 expected_leaf_labels:['1',...Array.from({length:6},(_,i)=>'2('+(i+1)+')')],
 operations:[{type:'shift',ids:['first'],dx:.01,dy:0},{type:'split',id:'group',children:
 Array.from({length:6},(_,i)=>frame('c'+i,'2('+(i+1)+')',[.1,.3+i*.08,.8,.37+i*.08]))}]};
}
const input=(action,extra={})=>({origin:location.origin,batch:'test',action,timeout:1,interval:2,...extra});
const tests=[];
function test(name,fn){tests.push([name,fn]);}
test('9 edits are validated before one write and six independent business questions are checked',async()=>{
 const w=world(),p=plan(w);const d=await main(input('run',{plan:{frames:p}}));
 assert(d.ok);assert(d.result.ready);assert.equal(w.patches,1);assert.equal(w.a.questions.length,7);
 assert.equal(w.a.questions.filter(q=>q.label.startsWith('2(')&&q.parent_id===null).length,6);
 const before=w.trace.length;const retry=await main(input('run',{checkpoint:d.checkpoint}));
 assert(retry.ok&&retry.result.ready&&retry.result.expected_granularity_verified);assert.equal(w.patches,1);assert.equal(w.starts,0);
 assert(w.trace.slice(before).every(([m])=>m==='GET'||m==='POST'));
});
test('expired frame revision gives zero writes',async()=>{
 const w=world(),p=plan(w);p.frame_revision='expired';const d=await main(input('frames',{plan:p}));
 assert.equal(d.error.code,'version_conflict');assert.equal(w.patches,0);
});
test('invalid box after valid operations rejects the complete batch',async()=>{
 const w=world(),p=plan(w);p.operations.push({type:'set',id:'first',regions:[{page:0,bbox:[-.1,.1,.4,.3]}]});
 const d=await main(input('frames',{plan:p}));assert.equal(d.error.code,'invalid_region');assert.equal(w.patches,0);
});
test('wrong source PDF rejects without a write',async()=>{
 const w=world(),p=plan(w);p.source_pdf_sha256='b'.repeat(64);
 const d=await main(input('frames',{plan:p}));assert.equal(d.error.code,'source_changed');assert.equal(w.patches,0);
});
test('generated images never count as reference review',async()=>{
 const w=world(),p=plan(w);p.reference_reviewed=false;
 const d=await main(input('frames',{plan:p}));assert.equal(d.error.code,'reference_review_required');assert.equal(w.patches,0);
});
test('same operation resumes without a second shift; changed server state stops',async()=>{
 const w=world(),p=plan(w);const d=await main(input('frames',{plan:p}));
 const retry=await main(input('frames',{plan:p,checkpoint:d.checkpoint}));assert(retry.ok&&retry.result.already_applied);assert.equal(w.patches,1);
 w.a.frame_revision='someone-else';const changed=await main(input('frames',{plan:p,checkpoint:d.checkpoint}));
 assert.equal(changed.error.code,'checkpoint_changed');assert.equal(w.patches,1);
});
test('changed content with the same operation ID is rejected',async()=>{
 const w=world(),p=plan(w);const d=await main(input('frames',{plan:p}));p.operations[0].dx=.02;
 const retry=await main(input('frames',{plan:p,checkpoint:d.checkpoint}));assert.equal(retry.error.code,'operation_changed');assert.equal(w.patches,1);
});
test('a calculation group cannot silently remain a composite business question',async()=>{
 const w=world();w.badComposite=true;const d=await main(input('run',{plan:{frames:plan(w)}}));assert.equal(d.error.code,'business_split_mismatch');
});
for(const state of ['stopping','stopped','paused'])test('explicit '+state+' is read only',async()=>{
 const w=world();w.tasks={analysis:{status:state}};const d=await main(input('run',{plan:{frames:plan(w)}}));
 assert(d.ok&&d.result.outcome==='stopped_readonly');assert(w.trace.every(([m])=>m==='GET'));
});
test('an existing import is read only for frame edits and associations',async()=>{
 const w=world();w.imports=[{state:'SUCCEEDED'}];
 for(const action of ['run','frames','associate','check']){const d=await main(input(action,{plan:plan(w)}));assert.equal(d.result.outcome,'existing_import_readonly');}
 assert(w.trace.every(([m])=>m==='GET'));
});
test('unknown identity keeps the entire batch not ready even if platform subset says ready',async()=>{
 const w=world();w.finish();w.roster.papers[1].student_id=null;const d=await main(input('check'));
 assert(d.ok&&!d.result.ready);assert.equal(d.result.papers,2);assert.equal(d.result.unlinked.length,1);
 assert.equal(d.result.check.counts.students,1);assert.equal(w.media,0);
});
test('unrelated workflows remain read only',async()=>{
 const w=world();w.batch.workflow_mode='essay';const d=await main(input('run'));
 assert.equal(d.result.outcome,'unsupported_workflow');assert(w.trace.every(([m])=>m==='GET'));
});
test('split with duplicate IDs rejects without a write',async()=>{
 const w=world(),p=plan(w);p.operations[1].children[1].id=p.operations[1].children[0].id;
 const d=await main(input('frames',{plan:p}));assert.equal(d.error.code,'invalid_or_duplicate_frame');assert.equal(w.patches,0);
});
test('partial association failure preserves a receipt and resumes only remaining papers',async()=>{
 const w=world();w.roster.papers.forEach(p=>p.student_id=null);w.failAssociation='p2';
 const p={revision:1,assignments:[['p1','11'],['p2','12']].map(([paper_id,student_id])=>({paper_id,student_id,evidence_confirmed:true,evidence_note:'Known test evidence'}))};
 const d=await main(input('associate',{plan:p}));assert(!d.ok&&d.checkpoint.association_receipt);assert.equal(w.roster.papers[0].student_id,'11');
 w.failAssociation=null;const resume=await main(input('associate',{plan:p,checkpoint:d.checkpoint}));assert(resume.ok);
 assert.deepEqual(w.associationAttempts,['p1','p2','p2']);
});
test('a stale checkpoint from another batch is rejected in the browser executor too',async()=>{
 const w=world();const d=await main(input('run',{checkpoint:{origin:location.origin,batch_id:'other'}}));
 assert.equal(d.error.code,'checkpoint_origin_or_batch_mismatch');assert.equal(w.trace.length,0);
});
test('a genuinely changed scope uses the live revision and authoritative endpoint',async()=>{
 const w=world();w.a.status='not_generated';
 const d=await main(input('run',{plan:{reference_student_id:'p1',scope:{revision:1,semester_id:'1',class_ids:['3'],scope:{source:'teaching'},evidence_confirmed:true,evidence_note:'User selected class'}}}));
 assert(d.ok&&d.result.outcome==='needs_frame_review');assert.equal(w.trace.filter(([m,p])=>m==='PUT'&&p.endsWith('/roster')).length,1);
});
test('a blocker is reported without starting useless media preparation',async()=>{
 const w=world();w.finish();w.checkPolicy=()=>({ready:false,status:'blocked',issues:[{code:'CONFIG_INVALID',severity:'blocker'}]});
 const d=await main(input('check'));assert(d.ok&&!d.result.ready);assert.equal(w.media,0);assert.equal(w.checks,1);
});
test('an active media preparation is observed and never started twice',async()=>{
 const w=world();w.finish();w.progressQueue=['running','awaiting_confirmation'];
 w.checkPolicy=n=>n===1?{ready:false,status:'preparing',issues:[{code:'MEDIA_CHECK_PENDING',severity:'pending'}]}:{};
 const d=await main(input('check'));assert(d.ok&&d.result.ready);assert.equal(w.media,0);assert.equal(w.checks,2);
});
test('preflight preparing without an active worker starts the missing preparation',async()=>{
 const w=world();w.finish();w.progressQueue=['preparing','awaiting_confirmation'];
 w.checkPolicy=n=>n===1?{ready:false,status:'preparing',issues:[{code:'MEDIA_CHECK_PENDING',severity:'pending'}]}:{};
 const d=await main(input('check'));assert(d.ok&&d.result.ready);assert.equal(w.media,1);assert.equal(w.checks,2);
});
test('an object composite membership prevents claiming an independent calculation question',async()=>{
 const w=world();const f=w.finish;w.finish=()=>{};
 // Pre-existing completed records can carry a composite object instead of a boolean.
 f();w.a.questions[0].composite={id:'business-parent'};
 const receipt={after_revision:w.a.frame_revision,source_pdf_sha256:w.a.source_pdf_sha256,
  reference_student_id:'p1',frames_signature:JSON.stringify(w.a.frames.map(f=>({id:f.id,label:f.label,parent_id:null,regions:f.regions}))),
  independent_labels:['1'],expected_leaf_labels:['1','2']};
 const d=await main(input('run',{checkpoint:{origin:location.origin,batch_id:'test',frame_receipt:receipt}}));
 assert.equal(d.error.code,'business_split_mismatch');
});
test('a completed batch with a changed frame revision cannot reuse its old review receipt',async()=>{
 const w=world();const d=await main(input('run',{plan:{frames:plan(w)}}));assert(d.ok);w.a.frame_revision='changed';
 const retry=await main(input('run',{checkpoint:d.checkpoint}));assert.equal(retry.error.code,'checkpoint_changed');
});
test('duplicate answers prevent full-batch readiness',async()=>{
 const w=world();w.finish();w.a.students[0].answers.push(clone(w.a.students[0].answers[0]));
 const d=await main(input('check'));assert(d.ok&&!d.result.ready);assert.equal(d.result.duplicate_answers,1);
});
for(const state of ['partial','failed'])test(state+' results require targeted recovery without a full rerun',async()=>{
 const w=world();w.a.status=state;const d=await main(input('run'));
 assert(d.ok&&d.result.outcome==='needs_targeted_recovery');assert.equal(w.starts,0);assert(w.trace.every(([m])=>m==='GET'));
});
(async()=>{let failed=0;for(const[name,fn]of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.log('FAIL '+name+' '+e.message);}}console.log(JSON.stringify({tests:tests.length,passed:tests.length-failed,failed}));process.exitCode=failed?1:0;})();
'''

if __name__=='__main__':
    import json
    source='const SOURCE='+json.dumps(paperflow.source())+';\n'+TESTS
    result=subprocess.run(['node','-'],input=source,text=True,capture_output=True)
    print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
    sys.exit(result.returncode)
