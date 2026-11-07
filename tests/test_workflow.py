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
test('accepted analysis start waits through initialization without a second dispatch or reference selection',async()=>{
 const w=world();w.a.status='not_generated';w.batch.scan_reference_student_id='p1';
 const old=global.fetch;
 global.fetch=async(path,o)=>{
  if(path===B+'/analysis'&&o.method==='POST'){
   w.starts++;w.trace.push([o.method,path]);
   return {ok:true,status:200,json:async()=>({status:'not_generated'})};
  }
  return old(path,o);
 };
 let d=await main(input('run',{stop_after:'frames'}));
 assert(d.ok);assert.equal(d.result.outcome,'waiting');assert.equal(d.result.waiting_for,'analysis_start');
 assert.equal(w.starts,1);assert.equal(d.transitions[0].response_status,'not_generated');
 d=await main(input('run',{stop_after:'frames',checkpoint:d.checkpoint,observe_analysis:true}));
 assert.equal(d.result.waiting_for,'analysis_start');assert.equal(w.starts,1);
 w.a.status='awaiting_frames';
 d=await main(input('run',{stop_after:'frames',checkpoint:d.checkpoint,observe_analysis:true}));
 assert.equal(d.result.outcome,'needs_frame_review');assert.equal(w.starts,1);
});
test('paused organizer exposes bounded server recovery hints without extra reads or automatic retry',async()=>{
 const w=world();Object.assign(w.a,{status:'failed',scan_student_states:{p1:'done',p2:'queued'},
  error:'学校 AI 需要当前教师登录；服务重启后请进入该任务并继续',error_code:'GATEWAY_BINDING_REQUIRED',
  recovery_action:'resume_with_session',resume_authorized:true,retryable:false,artifact_token:'private-fixture'});
 const d=await main(input('run'));
 assert.equal(d.result.outcome,'needs_targeted_recovery');assert.equal(d.result.failed_papers.length,0);
 assert.equal(d.result.recovery.error_code,'GATEWAY_BINDING_REQUIRED');
 assert.equal(d.result.recovery.recovery_action,'resume_with_session');
 assert.equal(d.result.recovery.server_resume_authorized,true);assert.equal(d.result.retry_authorized,false);
 assert.equal(d.result.resume_context.reference_student_id,'p1');assert.equal(d.result.resume_context.source_pdf_sha256,w.a.source_pdf_sha256);
 assert.equal(d.result.resume_context.frame_revision,'r1');assert.equal(d.result.resume_context.catalog_revision,null);
 assert.equal(d.result.next_action,'verify_current_session_and_authorized_resume');
 assert(w.trace.every(([m])=>m==='GET'));assert.equal(w.trace.filter(([,p])=>p.includes('/analysis?')).length,1);
 assert(!JSON.stringify(d.result).includes('private-fixture'));
});
test('frames endpoint saves geometric splits without confirming or organizing',async()=>{
 const w=world(),p=plan(w);
 const d=await main(input('run',{stop_after:'frames',plan:{frames:p}}));
 assert(d.ok);assert.equal(d.result.outcome,'precut_prepared');
 assert.equal(d.result.organization_started,false);assert.equal(d.result.business_questions_verified,false);
 assert.equal(d.checkpoint.stop_after,'frames');assert.equal(w.patches,1);
 assert.equal(w.a.status,'awaiting_frames');assert.equal(w.a.questions.length,0);
 assert.equal(d.result.review.frames.length,7);assert.equal(d.result.review.frame_revision,w.a.frame_revision);
 assert(!w.trace.some(([m,path])=>m==='POST'||path.includes('/preflight')||path.includes('/progress')));
 const before=w.trace.length;
 const blocked=await main(input('frames',{checkpoint:d.checkpoint,plan:p,confirm:true}));
 assert.equal(blocked.error.code,'precut_endpoint_confirmation_blocked');
 assert(w.trace.slice(before).every(([m])=>m==='GET'));
 const resumed=await main(input('run',{stop_after:'check',checkpoint:d.checkpoint,plan:{frames:p}}));
 assert(resumed.ok&&resumed.result.ready);assert.equal(w.patches,1);
 assert.equal(resumed.checkpoint.stop_after,'check');
});
test('frames endpoint reports review boundary and refuses unsupported or passed stages without writes',async()=>{
 let w=world();
 let d=await main(input('run',{stop_after:'frames'}));
 assert.equal(d.result.outcome,'needs_frame_review');assert.equal(d.result.organization_started,false);
 assert(w.trace.every(([m])=>m==='GET'));
 w=world();w.finish();d=await main(input('run',{stop_after:'frames',plan:{scope:{revision:1,
  evidence_confirmed:true,evidence_note:'fixture verified change',semester_id:'1',class_ids:['3'],scope:{source:'teaching'}}}}));
 assert.equal(d.result.outcome,'precut_stage_passed');assert.equal(d.result.stage_reverted,false);
 assert(w.trace.every(([m])=>m==='GET'));assert.equal(w.roster.revision,1);
 w=world();w.batch.workflow_mode='grading';w.batch.grading_engine='llm';
 d=await main(input('run',{stop_after:'frames'}));
 assert.equal(d.result.outcome,'precut_endpoint_unsupported');assert.equal(w.starts,0);
 assert(w.trace.every(([m])=>m==='GET'));
});
test('frames endpoint does not silently accept catalog or association writes',async()=>{
 const w=world();const d=await main(input('run',{stop_after:'frames',plan:{catalog:{},associations:{}}}));
 assert.equal(d.error.code,'precut_endpoint_plan_conflict');assert.equal(w.trace.length,0);
});
test('catalog snapshot retains authoritative answers and independent response structure without students',async()=>{
 const w=world();w.finish();
 Object.assign(w.a,{read_version:'catalog-source-version',reference_preparation:{status:'ready',remaining:0,artifact_token:'not-in-snapshot'},
  business_question_catalog:{types:[{businessQuestionTypeId:'type-1',isComposite:true,name:'fixture'}]}});
 Object.assign(w.a.questions[0],{stem:'$1+2$ with shared context',standard_answer:'3',standard_answer_source:'teacher_reference',
  explanation:'fixture explanation',group:'shared instruction',subquestion_stem:'child',composite:{id:'parent'},
  businessQuestionTypeId:'type-1',response_definitions:[{id:'response-1',type:'textResponse',blank_ids:['b1']}],
  business_question:{isComposite:true}});
 const d=await main(input('snapshot'));assert(d.ok);const q=d.result.questions[0],source=w.a.questions[0];
 for(const key of ['stem','standard_answer','standard_answer_source','explanation','group','subquestion_stem','composite','response_definitions'])
  assert.deepEqual(q[key],source[key]);
 assert.equal(q.business_question_is_composite,true);
 assert.equal(d.result.business_question_types[0].isComposite,true);
 assert.equal(d.result.read_version,w.a.read_version);
 assert.equal(d.result.reference_preparation.status,'ready');
 assert(!JSON.stringify(d.result).includes('not-in-snapshot'));
 assert(!('students' in d.result));assert.equal(w.trace.length,2);
});
test('catalog snapshot preserves platform figures and explicitly empty image evidence without extra reads',async()=>{
 const w=world();w.finish();const path=B+'/analysis/question-images/figure1';
 const figure={url:path,page:0,context:false,bbox:[.1,.2,.3,.4],reference_start:0,
  source_pdf_sha256:'a'.repeat(64),crop_version:'rgb-v3',pixels:[600,400],sha256:'b'.repeat(64),confirmed_frame_revision:'r1'};
 Object.assign(w.a.questions[0],{images:[path],crop_images:[figure],figure_images:[figure],
  figure_regions:[{page:0,bbox:figure.bbox}],reference_regions:[{page:0,bbox:figure.bbox}]});
 Object.assign(w.a.questions[1],{images:[],crop_images:[],figure_images:[]});
 const d=await main(input('snapshot'));assert(d.ok);const [q,empty]=d.result.questions;
 assert.deepEqual(q.images,[location.origin+path]);
 assert.deepEqual(q.figure_images,[{...figure,url:location.origin+path}]);
 assert.deepEqual(q.crop_images,q.figure_images);assert.deepEqual(q.figure_regions,w.a.questions[0].figure_regions);
 assert.deepEqual(q.reference_regions,w.a.questions[0].reference_regions);
 assert.deepEqual(empty.figure_images,[]);assert(!('image_locations_omitted' in q));
 assert.equal(w.trace.length,2);assert(!('students' in d.result));
});
test('catalog image projection omits external or credential-bearing locations and reports omission',async()=>{
 const w=world();w.finish();Object.assign(w.a.questions[0],{images:[
  B+'/analysis/question-images/local',
  'https://outside.test/image.png',B+'/analysis/question-images/secret?token=private-fixture',
  'https://user:password@example.test'+B+'/analysis/question-images/secret',B+'/original']});
 const d=await main(input('snapshot'));assert(d.ok);const q=d.result.questions[0];
 assert.equal(q.image_locations_omitted,4);assert.deepEqual(q.images,[location.origin+B+'/analysis/question-images/local']);
 assert(!JSON.stringify(d.result).includes('private-fixture'));assert(!JSON.stringify(d.result).includes('password'));
 assert.equal(w.trace.length,2);
});
test('completed run returns its existing versioned catalog for actual review without a separate snapshot read',async()=>{
 const w=world();w.finish();w.a.read_version='review-version';
 Object.assign(w.a.questions[0],{stem:'printed question',standard_answer:'3',figure_images:[],crop_images:[]});
 const d=await main(input('run'));assert(d.ok);const review=d.result.review;
 assert.equal(review.read_version,'review-version');assert.equal(review.reviewed,false);
 assert.equal(review.questions[0].stem,'printed question');assert.deepEqual(review.questions[0].figure_images,[]);
 assert.equal(w.trace.filter(([m,p])=>p===B+'/analysis?view=catalog').length,1);
 assert(!('students' in review));assert.equal(d.result.full_accuracy_verified,false);
});
test('interrupted analysis exposes unfinished reading papers instead of suggesting nonexistent failures',async()=>{
 const w=world();w.finish();w.a.status='failed';w.a.resume_authorized=true;w.a.retryable=true;
 w.a.scan_student_states={p1:'done',p2:'reading'};w.a.error='Interrupted; completed results retained';
 const d=await main(input('run'));assert(d.ok);assert.equal(d.result.outcome,'needs_targeted_recovery');
 assert.deepEqual(d.result.failed_papers,[]);
 assert.deepEqual(d.result.incomplete_papers,[{paper_id:'p2',index:2,pdf_pages:[2,2],state:'reading'}]);
 assert.equal(d.result.next_action,'verify_current_session_and_authorized_resume');
 assert.equal(d.result.retry_authorized,false);assert.equal(d.result.recovery.server_resume_authorized,true);
 assert(w.trace.every(([m])=>m==='GET'));assert(!w.trace.some(([m,p])=>p.endsWith('view=summary')));
});
test('association collision returns the current occupied paper locations without clearing or another roster read',async()=>{
 const w=world();const d=await main(input('associate',{plan:{revision:1,assignments:[
  {paper_id:'p1',student_id:'12',evidence_confirmed:true,evidence_note:'Visible name matched current roster'}]}}));
 assert.equal(d.ok,false);assert.equal(d.error.code,'association_already_occupied');
 assert.deepEqual(d.error.occupied_by,[{paper_id:'p2',index:2}]);assert.equal(d.error.roster_revision,1);
 assert.equal(d.error.next_action,'verify_conflicting_paper_evidence_or_keep_unlinked');
 assert.equal(w.trace.filter(([m,p])=>p===B+'/roster').length,1);assert(w.trace.every(([m])=>m==='GET'));
 assert.equal(w.roster.papers[0].student_id,'11');assert.equal(w.roster.papers[1].student_id,'12');
});
test('completed reference-answer session recovery points to its existing operation without authorizing or executing it',async()=>{
 const w=world();w.finish();w.a.reference_preparation={status:'waiting',remaining:4,
  error_code:'GATEWAY_BINDING_REQUIRED',recovery_action:'resume_with_session',retryable:false,artifact_token:'private-reference-token'};
 let d=await main(input('snapshot'));assert(d.ok);
 assert.equal(d.result.reference_preparation.resume_operation,'reference-answers-resume');
 assert.equal(d.result.reference_preparation.remaining,4);assert(!JSON.stringify(d.result).includes('private-reference-token'));
 assert(w.trace.every(([m])=>m==='GET'));assert.equal(w.trace.length,2);
 w.a.status='awaiting_frames';w.trace.length=0;d=await main(input('snapshot'));
 assert(!('resume_operation' in d.result.reference_preparation));assert.equal(w.trace.length,2);
});
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
test('natural repeated question labels retain distinct leaf IDs and pass with exact multiplicities',async()=>{
 const w=world();w.a.frames.forEach(f=>f.label='①');w.finish();
 const d=await main(input('run',{plan:{expected_leaf_labels:['①','①']}}));
 assert(d.ok&&d.result.ready);assert.equal(d.result.expected_granularity_verified,true);
 assert.equal(d.result.leaf_questions,2);assert.equal(new Set(w.a.questions.map(q=>q.id)).size,2);
 assert.equal(w.patches,0);assert.equal(w.starts,0);
 assert(w.trace.every(([method,path])=>method==='GET'||path===B+'/lesson-practice/preflight'));
});
test('repeated labels cannot conceal missing or extra leaf occurrences',async()=>{
 const w=world();w.a.frames[0].label='①';w.a.frames[1].label='②';w.finish();
 const d=await main(input('run',{plan:{expected_leaf_labels:['①','①']}}));
 assert.equal(d.error.code,'business_split_mismatch');assert.equal(d.error.reason,'label_counts_mismatch');
 assert.deepEqual(d.error.missing_labels,[{label:'①',count:1}]);assert.deepEqual(d.error.unexpected_labels,[{label:'②',count:1}]);
 assert.equal(d.error.expected_leaf_count,2);assert.equal(d.error.actual_leaf_count,2);
 assert.equal(d.error.retryable,false);assert.equal(w.checks,0);assert(w.trace.every(([method])=>method==='GET'));
});
test('matching labels never permit duplicate business leaf IDs',async()=>{
 const w=world();w.finish();w.a.questions[1].id=w.a.questions[0].id;
 const d=await main(input('run',{plan:{expected_leaf_labels:['1','2']}}));
 assert.equal(d.error.code,'business_split_mismatch');assert.equal(d.error.reason,'duplicate_or_missing_leaf_ids');
 assert.equal(w.checks,0);assert(w.trace.every(([method])=>method==='GET'));
});
test('leaf mismatch diagnostics stay bounded and omit answer content',async()=>{
 const w=world();w.a.frames=Array.from({length:25},(_,i)=>frame('q'+i,'actual'+i));w.finish();
 const d=await main(input('run',{plan:{expected_leaf_labels:Array.from({length:25},(_,i)=>'expected'+i)}}));
 assert.equal(d.error.reason,'label_counts_mismatch');assert.equal(d.error.missing_labels.length,12);
 assert.equal(d.error.unexpected_labels.length,12);assert.equal(d.error.details_truncated,true);
 assert(!JSON.stringify(d.error).includes('answers'));assert.equal(w.checks,0);
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
test('authorized identity skipping verifies exact server IDs and preserves full-batch failure',async()=>{
 const w=world();w.finish();w.roster.papers[1].student_id=null;
 w.checkPolicy=()=>({selected_paper_ids:['p1'],skipped_paper_ids:['p2'],eligible_paper_ids:['p1'],
   excluded_papers:[{paper_id:'p2',index:2,code:'STUDENT_UNLINKED',student_name:'not-needed'}]});
 const d=await main(input('check',{skip_unlinked:true}));
 assert(d.ok);assert.equal(d.result.ready,false);assert.equal(d.result.outcome,'ready_with_skips');
 assert.equal(d.result.eligible_check.ready,true);assert.equal(d.result.eligible_check.papers,1);
 assert.equal(d.result.eligible_check.full_batch_ready,false);assert.equal(d.result.papers,2);
 assert.equal(d.result.eligible_check.scope_persisted,false);assert.equal(d.result.eligible_check.skipped[0].paper_id,'p2');
 assert.equal(d.result.check.excluded_papers[0].student_name,undefined);assert.equal(w.media,0);
 assert(!w.trace.some(([m,p])=>m!=='GET'&&p!==B+'/lesson-practice/preflight'));
});
test('identity skip does not hide another excluded reason, incomplete structure, or a selected-scope gap',async()=>{
 for(const defect of ['wrong_ids','other_reason','missing_ids','duplicate_ids','missing_answer','narrowed_scope']){
  const w=world();w.finish();w.roster.papers[1].student_id=null;
  w.checkPolicy=()=>({selected_paper_ids:defect==='wrong_ids'?['p2']:defect==='duplicate_ids'?['p1','p1']:['p1'],
    ...(defect==='missing_ids'?{}:{skipped_paper_ids:['p2']}),
    excluded_papers:[{paper_id:'p2',code:defect==='other_reason'?'ANSWER_SET_INVALID':'STUDENT_UNLINKED'}]});
  if(defect==='missing_answer')w.a.students[0].answers.pop();
  if(defect==='narrowed_scope')w.cfg.config.selected_paper_ids=['p1'];
  const d=await main(input('check',{skip_unlinked:true}));
  assert(d.ok);assert.equal(d.result.eligible_check.ready,false,defect);assert.equal(d.result.ready,false);assert.equal(w.media,0);
 }
});
test('explicit identity skip prepares only after server coverage proves precisely the skipped identities',async()=>{
 const w=world();w.finish();w.roster.papers[1].student_id=null;
 w.checkPolicy=n=>({selected_paper_ids:['p1'],skipped_paper_ids:['p2'],excluded_papers:[{paper_id:'p2',code:'STUDENT_UNLINKED'}],
   ...(n===1?{ready:false,status:'preparing',issues:[{code:'MEDIA_CHECK_PENDING',severity:'pending'}]}:{})});
 const d=await main(input('run',{skip_unlinked:true}));
 assert(d.ok);assert.equal(d.result.eligible_check.ready,true);assert.equal(d.result.ready,false);
 assert.equal(w.media,1);assert.equal(w.checks,2);
});
test('identity-skip media preparation can restore a precisely identified pending question without certifying missing coverage',async()=>{
 const w=world();w.finish();w.roster.papers[1].student_id=null;
 w.checkPolicy=n=>({selected_paper_ids:['p1'],skipped_paper_ids:['p2'],excluded_papers:[{paper_id:'p2',code:'STUDENT_UNLINKED'}],
   ...(n===1?{ready:false,status:'preparing',counts:{students:1,skippedPapers:1,gradableQuestions:1,questionResults:1},
     issues:[{code:'QUESTION_ASSET_INVALID',severity:'pending',question_id:'group'},
       {code:'MEDIA_CHECK_PENDING',severity:'pending'}]}:{})});
 const d=await main(input('run',{skip_unlinked:true}));
 assert(d.ok);assert.equal(w.media,1);assert.equal(w.checks,2);
 assert.equal(d.result.eligible_check.ready,true);assert.equal(d.result.eligible_check.coverage_verified,true);
 assert.equal(d.result.ready,false);assert.equal(d.result.eligible_check.full_batch_ready,false);
 assert(!w.trace.some(([m,p])=>m==='PUT'||(m!=='GET'&&p.includes('/imports'))));
});
test('pending question media never licenses other exclusions, unknown questions, or unexplained count gaps',async()=>{
 for(const defect of ['other_reason','wrong_ids','unknown_question','unexplained_count','nonmedia_pending','bad_results','blocker']){
  const w=world();w.finish();w.roster.papers[1].student_id=null;
  w.checkPolicy=()=>({ready:false,status:'preparing',selected_paper_ids:defect==='wrong_ids'?['p2']:['p1'],skipped_paper_ids:['p2'],
    excluded_papers:[{paper_id:'p2',code:defect==='other_reason'?'ANSWER_SET_INVALID':'STUDENT_UNLINKED'}],
    counts:{students:1,skippedPapers:1,gradableQuestions:defect==='unexplained_count'?0:1,questionResults:defect==='bad_results'?0:1},
    issues:[{code:'QUESTION_ASSET_INVALID',severity:'pending',question_id:defect==='unknown_question'?'missing':'group'},
     ...(defect==='nonmedia_pending'?[{code:'ANSWER_PENDING',severity:'pending'}]:[]),
     ...(defect==='blocker'?[{code:'QUESTION_ASSET_INVALID',severity:'blocker'}]:[])]});
  const d=await main(input('check',{skip_unlinked:true}));assert(d.ok);
  assert.equal(w.media,0,defect);assert.equal(d.result.ready,false);assert.equal(d.result.eligible_check.ready,false);
  assert.equal(d.result.eligible_check.coverage_verified,false);
 }
});
test('still-pending skipped-scope question media remains waiting with strict coverage false',async()=>{
 const w=world();w.finish();w.roster.papers[1].student_id=null;w.progressQueue=['running','running'];
 w.checkPolicy=()=>({ready:false,status:'preparing',selected_paper_ids:['p1'],skipped_paper_ids:['p2'],
  excluded_papers:[{paper_id:'p2',code:'STUDENT_UNLINKED'}],
  counts:{students:1,skippedPapers:1,gradableQuestions:1,questionResults:1},
  issues:[{code:'QUESTION_ASSET_INVALID',severity:'pending',question_id:'group'}]});
 const d=await main(input('run',{skip_unlinked:true,timeout:0}));assert(d.ok);
 assert.equal(w.media,0);assert.equal(d.result.outcome,'waiting');assert.equal(d.result.waiting_for,'media');
 assert.equal(d.result.eligible_check.ready,false);assert.equal(d.result.eligible_check.coverage_verified,false);
 assert.equal(d.result.ready,false);
});
test('missing standard answers distinguish an already-running answer subtask without retrying or claiming readiness',async()=>{
 for(const status of ['running','ready','failed']){
  const w=world();w.finish();w.a.reference_preparation={status};
  w.checkPolicy=()=>({ready:false,issues:[{code:'STANDARD_ANSWER_MISSING',severity:'blocker'}]});
  const d=await main(input('run'));assert(d.ok);assert.equal(d.result.ready,false);
  assert.equal(d.result.reference_answers_pending,status==='running'?true:undefined);
  assert.equal(d.result.next_action,status==='running'?'observe_reference_answers_before_catalog_edits':undefined);
  assert.equal(d.result.review.reference_preparation.status,status);
  assert.equal(w.starts,0);assert.equal(w.patches,0);assert.equal(w.media,0);assert.equal(w.checks,1);
  assert(w.trace.every(([m,p])=>m==='GET'||p===B+'/lesson-practice/preflight'));
 }
});
test('missing organizer scope stops before analysis and reuses a same-run saved roster',async()=>{
 const w=world();w.a.status='not_generated';w.batch.scan_reference_student_id='p1';w.roster.classes=[];
 let d=await main(input('run'));assert(d.ok);assert.equal(d.result.outcome,'needs_scope');assert.equal(w.starts,0);
 const before=w.trace.length;
 d=await main(input('run',{plan:{scope:{evidence_confirmed:true,evidence_note:'Selected class',revision:1,
   semester_id:'1',class_ids:['2'],scope:{source:'teaching'}}}}));
 assert(d.ok);assert.equal(w.starts,1);
 assert.equal(w.trace.slice(before).filter(([m,p])=>m==='GET'&&p===B+'/roster').length,2);
});
test('incomplete general scope does not dispatch analysis or guess a missing directory value',async()=>{
 const w=world();w.a.status='not_generated';w.batch.scan_reference_student_id='p1';
 w.roster.scope={source:'general',grade:'7',subject_id:'14'};
 const d=await main(input('run'));assert(d.ok);assert.equal(d.result.outcome,'needs_scope');assert.equal(w.starts,0);
 assert(w.trace.every(([m])=>m==='GET'));
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
test('empty failed precut is a recovery boundary, never a visual approval',async()=>{
 const w=world();w.a.frames=[];w.a.localization_failed_pages=[0];w.a.localization_issues=['Page 1 failed'];
 const d=await main(input('run'));assert.equal(d.result.outcome,'needs_precut_recovery');assert.deepEqual(d.result.diagnosis.retryable_pages,[0]);assert.equal(w.starts,0);assert.equal(w.patches,0);
 assert.equal(d.result.review.source_pdf_sha256,w.a.source_pdf_sha256);
 assert.equal(d.result.review.reference_student_id,'p1');assert.equal(d.result.review.reviewed,false);
 assert.deepEqual(d.result.diagnosis.manual_recovery,{operation:'replace_page',pages:[0],review_required:true,auto_confirm:false});
 assert.deepEqual(d.result.review.precut_diagnosis,d.result.diagnosis);
 assert.equal(w.trace.length,4);
});
test('snapshot retains failed page diagnosis and valid-page frames without another run',async()=>{
 const w=world();w.batch.pages_per_paper=2;w.a.localization_failed_pages=[0];w.a.localization_issues=['Page 1 transport failed'];
 w.a.frames=w.a.frames.map(f=>({...f,regions:f.regions.map(r=>({...r,page:1}))}));
 const d=await main(input('snapshot'));assert(d.ok);assert.deepEqual(d.result.precut_diagnosis.failed_pages,[0]);
 assert.equal(d.result.precut_diagnosis.frame_revision,'r1');assert.equal(d.result.frames.length,2);
 assert.equal(d.result.precut_diagnosis.manual_recovery,undefined);
 assert(d.result.frames.every(f=>f.regions[0].page===1));assert.equal(w.trace.length,2);
 w.finish();const completed=await main(input('snapshot'));assert.equal(completed.result.precut_diagnosis,null);
});
test('empty teaching directory gives a bounded next action without choosing a different source',async()=>{
 const w=world(),old=global.fetch;
 global.fetch=async(path,o)=>path==='/api/classroom/classes'?{ok:true,status:200,json:async()=>({semester_id:'1',classes:[],courses:[]})}:old(path,o);
 const d=await main(input('classes',{plan:{source:'teaching'}}));assert(d.ok);
 assert.equal(d.result.next_action,'query_general_directory');assert.equal(d.result.source,'teaching');
 assert.deepEqual(d.result.classes,[]);assert.equal(w.trace.length,0);
});
test('empty precut with no failed-page list uses the known paper page count',async()=>{
 const w=world();w.a.frames=[];w.batch.pages_per_paper=2;
 const d=await main(input('run'));assert.equal(d.result.outcome,'needs_precut_recovery');
 assert.deepEqual(d.result.diagnosis.retryable_pages,[0,1]);assert.equal(w.starts,0);assert.equal(w.patches,0);
});
test('retry-precut sends one revision-guarded request for only the failed page',async()=>{
 const w=world();w.a.frames=[];w.a.localization_failed_pages=[0];const old=global.fetch;let retries=0;
 global.fetch=async(path,o)=>{if(path===B+'/analysis/frames/retry-precut'){retries++;assert.deepEqual(JSON.parse(o.body),{page:0,frame_revision:'r1'});return {ok:true,status:200,json:async()=>({status:'generating'})};}return old(path,o);};
 const d=await main(input('retry-precut',{plan:{page:0,frame_revision:'r1'}}));assert(d.ok);assert.equal(retries,1);
});
test('retry-precut preserves manual frames on the failed page',async()=>{
 const w=world();w.a.localization_failed_pages=[0];const d=await main(input('retry-precut',{plan:{page:0,frame_revision:'r1'}}));
 assert.equal(d.error.code,'manual_frames_present');assert(w.trace.every(([m])=>m==='GET'));
});
function promotion(w){
 w.a.frames.push(...Array.from({length:6},(_,i)=>({...frame('old'+i,'('+i+')',[.1,.3+i*.08,.8,.37+i*.08]),parent_id:'group'})));
 const p=plan(w);p.operations=[{type:'promote_children',id:'group',children:w.a.frames.slice(2).map((f,i)=>({...clone(f),label:'2('+(i+1)+')'}))}];return p;
}
test('existing six children become six independent questions in one PATCH, retaining IDs',async()=>{
 const w=world(),p=promotion(w);const d=await main(input('run',{plan:{frames:p}}));
 assert(d.ok&&d.result.ready);assert.equal(w.patches,1);assert.equal(w.a.frames.length,7);assert(!w.a.frames.some(f=>f.id==='group'));assert(w.a.frames.every(f=>!f.parent_id));
 assert.deepEqual(d.checkpoint.frame_receipt.independent_labels,['2(1)','2(2)','2(3)','2(4)','2(5)','2(6)']);
});
test('promotion cannot drop an existing child or include a grandchild',async()=>{
 let w=world(),p=promotion(w);p.operations[0].children.pop();let d=await main(input('frames',{plan:p}));assert.equal(d.error.code,'invalid_independent_promotion');assert.equal(w.patches,0);
 w=world();p=promotion(w);w.a.frames.push({...frame('grandchild','nested'),parent_id:'old0'});d=await main(input('frames',{plan:p}));assert.equal(d.error.code,'invalid_independent_promotion');assert.equal(w.patches,0);
});
test('diagnose groups related failures and does not prepare media',async()=>{
 const w=world();w.finish();w.a.questions[0].content={questionTypeKey:1,elements:[{type:'richText',content:{text:'Stem',html:'BIG_HTML',json:['BIG_JSON']}},{type:'choice',options:[{id:'stable-c',cells:[{text:'Actual option'}]}]}]};
 w.checkPolicy=()=>({ready:false,status:'blocked',issues:[{code:'ANSWER_ELEMENT_INVALID',severity:'blocker',paper_id:'p2',question_id:'first',message:'Select actual option'}]});
 const d=await main(input('diagnose'));assert(d.ok);assert.equal(d.result.review_tasks.issue_count,1);assert.equal(d.result.review_tasks.papers[0].index,2);assert.equal(d.result.review_tasks.questions[0].elements[1].options[0].id,'stable-c');assert(!JSON.stringify(d.result).includes('BIG_HTML'));assert.equal(w.media,0);
});
test('usage missing from provider remains unknown',async()=>{
 world();const old=global.fetch;global.fetch=async(path,o)=>path===B+'/model-usage'?{ok:true,status:200,json:async()=>({summary:{http_attempts:60,total_tokens:null,total_tokens_missing_attempts:60},usage_source:'provider'})}:old(path,o);
 const d=await main(input('usage'));assert(d.ok);assert.equal(d.result.tokens_complete,false);assert.equal(d.result.summary.total_tokens,null);
});
function responseWorld(){
 const w=world();w.finish();w.a.catalog_revision='catalog1';w.a.review_token='ephemeral1';w.responseWrites=[];
 w.a.questions[0].blanks=[];w.a.questions[0].content={elements:[{type:'richText',content:{text:'Stem'}},{type:'choice',config:{selectionType:'single'},options:[{id:'stable-A'},{id:'stable-B'},{id:'stable-C'}]}]};
 const old=global.fetch;
 global.fetch=async(path,o)=>{
  if(path===B+'/analysis'&&o.method==='GET')return {ok:true,status:200,json:async()=>clone(w.a)};
  if(path===B+'/analysis/students/p2')return {ok:true,status:200,json:async()=>({student:clone(w.a.students[1])})};
  if(path.includes('/questions/')&&o.method==='PATCH'){
   const body=JSON.parse(o.body);assert.equal(body.review_token,w.a.review_token);assert.equal(body.response_only,true);assert(!('verdict' in body));w.responseWrites.push(body);w.a.review_token+='next';
   return {ok:true,status:200,json:async()=>clone(w.a)};
  }
  return old(path,o);
 };
 w.responsePlan={source_pdf_sha256:w.a.source_pdf_sha256,frame_revision:w.a.frame_revision,catalog_revision:w.a.catalog_revision,
 assignments:[{paper_id:'p2',question_id:'first',selected_option_positions:[3],evidence_confirmed:true,evidence_note:'Observed third option on original PDF'}]};return w;
}
test('observed option position maps to actual stable ID, preserving teacher verdict',async()=>{
 const w=responseWorld();const d=await main(input('responses',{plan:w.responsePlan}));assert(d.ok);assert.equal(w.responseWrites.length,1);assert.equal(w.responseWrites[0].response.answer_text,'stable-C');assert.equal(d.result.changed_teacher_verdicts,false);
});
test('response plan validates every item before the first write',async()=>{
 const w=responseWorld();w.responsePlan.assignments.push({...w.responsePlan.assignments[0],question_id:'group',evidence_confirmed:false});
 const d=await main(input('responses',{plan:w.responsePlan}));assert(!d.ok);assert.equal(w.responseWrites.length,0);
});
test('response edits stop on stale source and existing imports',async()=>{
 let w=responseWorld();w.responsePlan.frame_revision='stale';let d=await main(input('responses',{plan:w.responsePlan}));assert.equal(d.error.code,'response_source_changed');assert.equal(w.responseWrites.length,0);
 w=responseWorld();w.imports=[{state:'SUCCEEDED'}];d=await main(input('responses',{plan:w.responsePlan}));assert.equal(d.result.outcome,'existing_import_readonly');assert.equal(w.responseWrites.length,0);
});
test('evidence is limited to requested paper and question and excludes review token',async()=>{
 const w=responseWorld();const d=await main(input('evidence',{plan:{paper_id:'p2',question_ids:['first']}}));
 assert(d.ok);assert.equal(d.result.paper_id,'p2');assert.equal(d.result.questions.length,1);assert.equal(d.result.observations.length,1);assert.equal(d.result.reviewed,false);assert(!JSON.stringify(d.result).includes('ephemeral1'));assert.equal(w.responseWrites.length,0);
});
test('sequential response edits propagate returned token without another full read',async()=>{
 const w=responseWorld();w.a.questions[1].blanks=[];w.a.questions[1].content={elements:[{type:'textResponse'}]};
 w.responsePlan.assignments.push({paper_id:'p2',question_id:'group',answer_text:'Observed work',evidence_confirmed:true,evidence_note:'Read original'});
 const d=await main(input('responses',{plan:w.responsePlan}));assert(d.ok);assert.equal(w.responseWrites.length,2);assert.notEqual(w.responseWrites[0].review_token,w.responseWrites[1].review_token);
});

function reply(value,status=200){return {ok:status<400,status,headers:{get:()=>null},json:async()=>clone(value)};}
test('initial reference candidates use uploaded papers even when analysis students are empty',async()=>{
 const w=world();w.a.status='not_generated';w.a.students=[];
 const d=await main(input('run'));assert.equal(d.result.outcome,'needs_reference');assert.equal(d.result.papers,2);
 assert.equal(d.result.candidates[0].pages[0],location.origin+B+'/pages/0?original=true&student_id=p1');assert.equal(w.starts,0);
});
test('reference selection sends exactly one JSON object with correct content type',async()=>{
 const w=world();w.a.status='not_generated';const old=global.fetch;let attempts=0;
 global.fetch=async(path,o)=>{if(path===B+'/analysis'&&o.method==='POST'){
  attempts++;assert.equal(o.headers['Content-Type'],'application/json');assert.equal(typeof o.body,'string');
  assert.deepEqual(JSON.parse(o.body),{reference_student_id:'p1'});
 }return old(path,o);};
 const d=await main(input('run',{plan:{reference_student_id:'p1'}}));assert(d.ok);assert.equal(attempts,1);assert.equal(d.result.outcome,'needs_frame_review');
});
test('malformed JSON detail is not misreported as invalid reference or retried with other fields',async()=>{
 const w=world();w.a.status='not_generated';const old=global.fetch;let attempts=0;
 global.fetch=async(path,o)=>path===B+'/analysis'&&o.method==='POST'?(attempts++,reply({detail:'标准卷选择格式无效'},422)):old(path,o);
 const d=await main(input('run',{plan:{reference_student_id:'p1'}}));assert(!d.ok);assert.equal(d.error.code,'invalid_json_body');
 assert.equal(d.error.next_action,'verify_json_transport');assert.equal(d.error.retryable,false);assert.equal(attempts,1);
});
test('actual invalid paper error remains distinct from malformed JSON',async()=>{
 const w=world();w.a.status='not_generated';const old=global.fetch;
 global.fetch=async(path,o)=>path===B+'/analysis'&&o.method==='POST'?reply({detail:'请选择本次上传的一份学生卷'},422):old(path,o);
 const d=await main(input('run',{plan:{reference_student_id:'p1'}}));assert.equal(d.error.code,'validation_failed');assert.equal(d.error.message,'请选择本次上传的一份学生卷');
});
test('reviewed unchanged frames confirm with zero PATCH operations',async()=>{
 const w=world(),p=plan(w);p.operations=[];p.expected_leaf_labels=['1','2'];
 const d=await main(input('run',{plan:{frames:p}}));assert(d.ok&&d.result.ready);assert.equal(w.patches,0);
 assert.equal(w.trace.filter(([m,p])=>m==='POST'&&p.endsWith('/frames/confirm')).length,1);
});
function catalogWorld(){
 const w=world();w.finish();w.a.status='awaiting_confirmation';w.a.catalog_revision='c1';w.batch.analysis_confirmation_version=2;
 w.batch.name='Test';w.batch.name_revision=3;
 w.a.questions[0].content={elements:[{type:'richText',content:{text:'actual',html:'preserve_html',json:{stable:'payload'}}}]};
 const old=global.fetch;w.catalogCalls=[];
 global.fetch=async(path,o)=>{
  if(path===B+'/merge-preflight'){
   const b=JSON.parse(o.body);assert.deepEqual(b.source_ids,[]);w.catalogCalls.push([path,b]);
   return reply({operation_id:'server-op',preflight_token:'transient-business-token',versions:{test:{version:1}},duplicates:w.duplicates||[]});
  }
  if(path===B+'/analysis/confirm-and-start'||path===B+'/analysis/confirm'){
   const b=JSON.parse(o.body);w.catalogCalls.push([path,b]);
   if(w.confirmTimeout)throw Error('connection lost');
   w.a.status='completed';return reply({status:'accepted',operation_id:'server-op'});
  }
  return old(path,o);
 };
 w.catalogPlan={operation_id:'catalog-review-1',source_pdf_sha256:w.a.source_pdf_sha256,reference_student_id:'p1',
  frame_revision:w.a.frame_revision,catalog_revision:'c1',reference_reviewed:true,scope_reviewed:true,catalog_reviewed:true,
  reviewed_pages:[0],expected_leaf_labels:['1','2']};
 return w;
}
test('a no-edit review cannot approve failed or empty precut output',async()=>{
 const w=world(),p=plan(w);p.operations=[];w.a.localization_failed_pages=[0];
 let d=await main(input('frames',{plan:p,confirm:true}));assert.equal(d.error.code,'precut_recovery_required');
 w.a.localization_failed_pages=[];w.a.frames=[];
 d=await main(input('frames',{plan:p,confirm:true}));assert.equal(d.error.code,'precut_recovery_required');
 assert(w.trace.every(([m])=>m==='GET'));
});
test('v2 reviewed catalog advances to ready without copying rich questions through the agent plan',async()=>{
 const w=catalogWorld();const d=await main(input('run',{plan:{catalog:w.catalogPlan}}));assert(d.ok&&d.result.ready);
 assert.equal(w.catalogCalls.length,2);const sent=w.catalogCalls[1][1];
 assert.deepEqual(sent.questions,w.a.questions);assert.equal(sent.questions[0].content.elements[0].content.html,'preserve_html');
 assert.equal(sent.name_revision,3);assert.deepEqual(sent.source_versions,{test:{version:1}});assert.equal(d.result.submitted,false);
 assert(!w.trace.some(([m,p])=>m==='POST'&&p.endsWith('/imports')));assert.equal(d.result.visual_review_performed,true);
 assert.equal(w.trace.filter(([m,p])=>m==='GET'&&p===B).length,1);
 assert(!JSON.stringify(d.checkpoint).includes('transient-business-token'));
});
test('unreviewed or changed catalog version cannot be confirmed',async()=>{
 const w=catalogWorld();w.catalogPlan.catalog_revision='old';let d=await main(input('catalog',{plan:w.catalogPlan}));
 assert.equal(d.error.code,'catalog_review_required');assert.equal(w.catalogCalls.length,0);
 w.catalogPlan.catalog_revision='c1';w.catalogPlan.catalog_reviewed=false;d=await main(input('catalog',{plan:w.catalogPlan}));
 assert.equal(d.error.code,'catalog_review_required');assert.equal(w.catalogCalls.length,0);
});
test('duplicate students stop scope confirmation without selecting a paper or submitting',async()=>{
 const w=catalogWorld();w.duplicates=[{student_id:'11',papers:[{key:'p1'},{key:'p2'}]}];
 const d=await main(input('run',{plan:{catalog:w.catalogPlan}}));assert.equal(d.result.outcome,'needs_duplicate_review');
 assert.equal(w.catalogCalls.length,1);assert.equal(d.result.submitted,false);
});
test('catalog confirmation timeout preserves recovery operation and cannot create another preflight',async()=>{
 const w=catalogWorld();w.confirmTimeout=true;const d=await main(input('catalog',{plan:w.catalogPlan}));assert(!d.ok);
 assert.equal(d.error.code,'transport_uncertain');assert.equal(d.checkpoint.catalog_receipt.server_operation_id,'server-op');
 const before=w.catalogCalls.length;const retry=await main(input('catalog',{plan:w.catalogPlan,checkpoint:d.checkpoint}));
 assert(retry.ok);assert.equal(retry.result.outcome,'needs_confirmation_recovery');assert.equal(w.catalogCalls.length,before);
});
test('old confirmation is used only when the deployed version permits it',async()=>{
 const w=catalogWorld();delete w.batch.analysis_confirmation_version;const d=await main(input('catalog',{plan:w.catalogPlan}));
 assert(d.ok);assert.equal(w.catalogCalls.length,1);assert.equal(w.catalogCalls[0][0],B+'/analysis/confirm');
});
test('catalog granularity mismatch is detected before a preflight or confirmation write',async()=>{
 const w=catalogWorld();w.catalogPlan.expected_leaf_labels=['1'];const d=await main(input('catalog',{plan:w.catalogPlan}));
 assert.equal(d.error.code,'business_split_mismatch');assert.equal(w.catalogCalls.length,0);
});
test('catalog replay with changed source cannot claim current review',async()=>{
 const w=catalogWorld();const d=await main(input('catalog',{plan:w.catalogPlan}));w.a.source_pdf_sha256='new-source';
 const retry=await main(input('catalog',{plan:w.catalogPlan,checkpoint:d.checkpoint}));assert.equal(retry.error.code,'source_changed');assert.equal(w.catalogCalls.length,2);
});

function authWorld(){
 const w=world(),old=global.fetch;
 w.sessionUser={id:'teacher-1',school_id:'school-1',identity:'teacher'};
 w.loginCheck={'云谷会话':'有效且账号一致','课堂会话':'有效'};
 w.loginCalls=0;
 global.fetch=async(path,o)=>{
  if(path==='/api/session?refresh_profile=false&include_models=false')return reply({user:w.sessionUser});
  if(path==='/api/classroom/login-check')return reply(w.loginCheck);
  if(path.startsWith('/api/login?force=true')){
   w.loginCalls++;return reply({ok:false,login_url:'https://sso.example.test/login?private_state=secret_runtime_value'});
  }
  return old(path,o);
 };return w;
}
test('access checks both authentication boundaries without requesting model configuration',async()=>{
 const w=authWorld();const d=await main(input('access'));assert(d.ok&&d.result.classroom_valid);
 assert.equal(d.result.outcome,'access_verified');assert.equal(d.checkpoint.auth_receipt.principal.user_id,'teacher-1');
 assert.equal(w.starts,0);assert.equal(w.loginCalls,0);assert.equal(d.calls.length,2);
 assert(d.calls.every(c=>c.method==='GET'&&!c.path.includes('include_models=true')));
});
test('HTTP 200 login diagnostic containing an embedded 428 cannot pass access',async()=>{
 const w=authWorld();w.loginCheck={'云谷会话':'未验证','课堂会话':'未验证','状态码':428,'错误类型':'classroom_login_required','检查结果':'批阅台已登录，但云谷课堂会话已失效'};
 const d=await main(input('access'));assert(d.ok&&!d.result.classroom_valid);assert.equal(d.result.outcome,'classroom_login_required');
 assert.equal(d.result.next_action,'relogin');assert.equal(w.loginCalls,0);
});
test('unknown upstream diagnostic remains unverified rather than triggering login or pretending success',async()=>{
 const w=authWorld();w.loginCheck={'状态码':503,'错误类型':'upstream_unavailable','课堂会话':'未验证'};
 const d=await main(input('access'));assert.equal(d.result.outcome,'authentication_unverified');assert.equal(d.result.classroom_valid,false);assert.equal(w.loginCalls,0);
});
test('exact classroom expiry 428 has a deterministic recovery action while unrelated 428 does not',async()=>{
 const w=world();w.a.status='not_generated';const old=global.fetch;
 let message='批阅台已登录，但云谷课堂会话已失效';
 global.fetch=async(path,o)=>path===B+'/analysis'&&o.method==='POST'?reply({detail:message},428):old(path,o);
 let d=await main(input('run',{plan:{reference_student_id:'p1'}}));assert.equal(d.error.code,'classroom_login_required');assert.equal(d.error.next_action,'check_access_then_relogin');
 message='请先完成模型能力配置';d=await main(input('run',{plan:{reference_student_id:'p1'}}));assert.equal(d.error.code,'api_failed');
});
test('relogin navigates once using a runtime URL, returns no authorization URL and rechecks the same identity',async()=>{
 const w=authWorld();const a=await main(input('access'));
 const originalTimeout=global.setTimeout,originalAssign=location.assign;let navigation;
 global.setTimeout=fn=>{fn();return 1};location.assign=url=>{navigation=url};
 try{
  const d=await main(input('relogin',{checkpoint:a.checkpoint}));assert.equal(d.result.outcome,'authentication_navigation_started');
  assert(navigation.startsWith('https://sso.example.test/'));assert(!JSON.stringify(d).includes('private_state'));
  assert(!JSON.stringify(d).includes('secret_runtime_value'));assert.equal(w.loginCalls,1);
  const again=await main(input('relogin',{checkpoint:d.checkpoint}));assert.equal(again.result.outcome,'authentication_recovery_pending');assert.equal(w.loginCalls,1);
  const verified=await main(input('access',{checkpoint:d.checkpoint}));assert.equal(verified.result.outcome,'access_verified');assert.equal(verified.checkpoint.auth_receipt.recovery_started,false);
 }finally{global.setTimeout=originalTimeout;location.assign=originalAssign;}
});
test('authentication recovery preserves focused edits and does not revoke an active login',async()=>{
 const w=authWorld();const original=global.document;global.document={querySelector:()=>({})};
 try{const d=await main(input('relogin'));assert.equal(d.result.outcome,'authentication_navigation_deferred');assert.equal(w.loginCalls,0);}
 finally{if(original===undefined)delete global.document;else global.document=original;}
});
test('a changed teacher or school blocks all pending business writes after recovery',async()=>{
 const w=authWorld(),d=await main(input('access'));d.checkpoint.auth_receipt.recovery_started=true;
 w.sessionUser.school_id='different-school';
 for(const action of ['run','frames','catalog','associate','responses','retry-precut','check']){
  const result=await main(input(action,{checkpoint:d.checkpoint}));assert.equal(result.error.code,'identity_changed');
 }
 assert(w.trace.every(([method])=>method==='GET'));assert.equal(w.loginCalls,0);
});
test('one roster reconciliation returns only unmatched paper evidence and exact name candidates',async()=>{
 const w=world();w.roster.papers[1].student_id=null;w.roster.papers[1].name='Verified Name';w.roster.papers[1].name_confirmed=false;
 w.roster.students=[{id:'11',name:'Other private name'},{id:'12',name:'Verified Name'},{id:'13',name:'Remaining guessed name'}];
 const d=await main(input('roster'));assert(d.ok);assert.equal(d.result.revision,1);assert.equal(d.result.linked,1);assert.equal(d.result.papers,2);
 assert.equal(d.result.unlinked[0].index,2);assert.deepEqual(d.result.unlinked[0].pdf_pages,[2,2]);assert.equal(d.result.unlinked[0].evidence_confirmed,false);
 assert.deepEqual(d.result.unlinked[0].exact_name_candidates,[{id:'12',name:'Verified Name'}]);
 assert(!JSON.stringify(d.result).includes('Remaining guessed name'));assert.equal(d.calls.length,2);assert(w.trace.every(([m])=>m==='GET'));
});
test('identity and media blockers remain separate even when the platform subset says ready',async()=>{
 const w=world();w.finish();w.roster.papers[1].student_id=null;
 w.checkPolicy=()=>({ready:true,status:'awaiting_confirmation',issues:[{code:'MEDIA_CHECK_PENDING',severity:'pending'}]});
 const d=await main(input('run'));assert(d.ok&&!d.result.ready);assert.equal(d.result.outcome,'identity_pending');
 assert.equal(d.result.completion.analysis_completed,true);assert.equal(d.result.completion.identity_complete,false);
 assert.equal(d.result.completion.media_pending,true);assert.equal(d.result.completion.preflight_passed,false);
 assert(d.result.remaining.some(i=>i.code==='IDENTITY_PENDING'));assert(d.result.remaining.some(i=>i.code==='MEDIA_CHECK_PENDING'));
 assert.equal(w.media,0);assert.equal(d.result.submitted,false);
});
test('invalid asset versions remain explicit media blockers alongside unknown identity without preparation',async()=>{
 const w=world();w.finish();w.roster.papers[1].student_id=null;
 w.checkPolicy=()=>({ready:false,status:'blocked',issues:[
  {code:'QUESTION_ASSET_INVALID',severity:'blocker',action:'prepare_media',question_id:'first'},
  {code:'NO_SYNC_STUDENTS',severity:'blocker',action:'roster'}]});
 const d=await main(input('check'));assert(d.ok&&!d.result.ready);
 assert.equal(d.result.completion.media_pending,false);assert.equal(d.result.completion.media_blocked,true);
 assert.equal(d.result.completion.identity_complete,false);assert.equal(d.result.completion.preflight_passed,false);
 assert(d.result.remaining.some(x=>x.code==='QUESTION_ASSET_INVALID'));assert.equal(w.media,0);assert.equal(w.checks,1);
 assert(!w.trace.some(([m,p])=>p===B+'/lesson-practice/progress'));
});
test('contradictory platform ready with pending media cannot report full completion',async()=>{
 const w=world();w.finish();w.checkPolicy=()=>({ready:true,status:'awaiting_confirmation',issues:[{code:'MEDIA_CHECK_PENDING',severity:'pending'}]});
 const d=await main(input('run'));assert(d.ok&&!d.result.ready);assert.equal(d.result.completion.preflight_passed,false);assert.equal(d.result.completion.media_pending,true);
 assert.equal(d.result.outcome,'pending');assert.equal(w.media,0);
});
test('roster gaps cannot report all identities linked',async()=>{
 const w=world();w.roster.papers.pop();const d=await main(input('roster'));
 assert.equal(d.result.outcome,'roster_coverage_gap');assert.equal(d.result.roster_coverage_complete,false);
});
test('run returns media waiting for CLI follow without restarting an existing preparation',async()=>{
 const w=world();w.finish();w.checkPolicy=()=>({ready:false,status:'preparing',issues:[{code:'MEDIA_CHECK_PENDING',severity:'pending'}]});
 const oldFetch=global.fetch,oldPerformance=global.performance;let now=0,reads=0;
 global.performance={now:()=>now};
 global.fetch=async(path,o)=>{
  if(path===B+'/lesson-practice/progress'){reads++;if(reads>1)now=1001;return reply({preparation:{status:'running'}});}
  return oldFetch(path,o);
 };
 try{
  const d=await main(input('run'));assert(d.ok);assert.equal(d.result.outcome,'waiting');assert.equal(d.result.waiting_for,'media');assert.equal(w.media,0);assert.equal(d.result.ready,false);
 }finally{global.performance=oldPerformance;}
});

test('deleted batch is distinct from unknown routes and missing scope does not cause a retry or selection',async()=>{
 for(const [message,expected] of [['考试不存在或已删除','batch_not_found'],['route unavailable','contract_mismatch']]){
  const w=world(),original=global.fetch;
  global.fetch=async(path,o)=>path===B+'/roster'?reply({detail:message},404):original(path,o);
  const d=await main(input('api-call',{plan:{operation:'roster'}}));
  assert(!d.ok);assert.equal(d.error.code,expected);assert.equal(d.calls.length,1);assert.equal(d.calls[0].method,'GET');
 }
 const w=world();w.batch.workflow_mode='grading';w.batch.grading_engine='xueersi';
 const original=global.fetch;let starts=0;
 global.fetch=async(path,o)=>{if(path===B+'/start'){starts++;return reply({detail:'请先选择年级、学科、课程和班级'},422);}return original(path,o);};
 const d=await main(input('api-call',{plan:{operation:'grading-start',evidence_confirmed:true,evidence_note:'authorized original batch'}}));
 assert(!d.ok);assert.equal(d.error.code,'classroom_scope_required');assert.equal(d.error.next_action,'select_verified_classroom_scope');
 assert.equal(starts,1);assert(w.trace.every(([method])=>method==='GET'));
 const fresh=world();fresh.batch.workflow_mode='grading';fresh.batch.grading_engine='xueersi';const liveFetch=global.fetch;let conflictingStarts=0;
 global.fetch=async(path,o)=>{if(path===B+'/start'){conflictingStarts++;return reply({detail:'关联结果已更新，请刷新后重试'},409);}return liveFetch(path,o);};
 const changed=await main(input('api-call',{plan:{operation:'grading-start',evidence_confirmed:true,evidence_note:'same authorized batch'}}));
 assert.equal(changed.error.code,'grading_roster_changed');assert.equal(conflictingStarts,1);
 assert.equal(changed.error.next_action,'read_live_state_and_roster_before_resuming');
});
test('exact-name lookup batches explicit permitted classes with bounded reads and never guesses an association',async()=>{
 world();let active=0,maxActive=0;const calls=[];
 global.fetch=async(path,o)=>{
  calls.push([o.method,path]);active++;maxActive=Math.max(maxActive,active);
  await new Promise(r=>setTimeout(r,2));active--;
  const cid=path.match(/classes\/(\d+)\/students/)[1];
  return reply({classroom:{id:cid},total:2,students:[{id:'private',name:'Unrelated private name'},
    {id:cid,name:cid==='937'?'Clear Name':'Clear Name Variant'}]});
 };
 const plan={source:'general',grade:'6',subject_id:'14',course_id:'658',
   class_ids:['934','935','936','937','938','939','940','941'],name_exact:['Clear Name','Absent Name']};
 const d=await main(input('class-students',{plan}));assert(d.ok);assert.equal(d.result.lookup_complete,true);
 assert.equal(maxActive,3);assert.equal(calls.length,8);assert(calls.every(([m])=>m==='GET'));
 assert.deepEqual(d.result.matches,[{id:'937',name:'Clear Name',class_id:'937'}]);
 assert.deepEqual(d.result.unmatched_names,['Absent Name']);assert.equal(d.result.association_performed,false);
 assert(!JSON.stringify(d.result).includes('Unrelated private name'));assert(!JSON.stringify(d.result).includes('Name Variant'));
 global.fetch=async(path,o)=>reply({detail:'forbidden'},403);
 const partial=await main(input('class-students',{plan:{...plan,class_ids:['934']}}));
 assert(partial.ok);assert.equal(partial.result.lookup_complete,false);assert.equal(partial.result.unmatched_names,null);
 assert.equal(partial.result.classes[0].error.code,'permission_denied');
 global.fetch=async()=>reply({total:2,students:[{id:'1',name:'Other'}]});
 const truncated=await main(input('class-students',{plan:{...plan,class_ids:['934']}}));
 assert.equal(truncated.result.lookup_complete,false);assert.equal(truncated.result.unmatched_names,null);
 assert.equal(truncated.result.classes[0].error.code,'class_students_incomplete');
 let unexpected=0;global.fetch=async()=>{unexpected++;return reply({},500);};
 const invalid=await main(input('class-students',{plan:{...plan,class_ids:['934','934']}}));
 assert.equal(invalid.error.code,'invalid_class_id');assert.equal(unexpected,0);
});
test('explicit unlink uses the association command with evidence, revision checks and persisted readback',async()=>{
 const w=world();
 const p={revision:1,assignments:['p1','p2'].map(paper_id=>({paper_id,student_id:null,evidence_confirmed:true,evidence_note:'Original image cannot support automatic link'}))};
 const saved=await main(input('associate',{plan:p}));assert(saved.ok);
 assert.deepEqual(w.roster.papers.map(p=>p.student_id),[null,null]);
 assert.equal(w.associationAttempts.length,2);assert.equal(saved.result.revision,3);
 assert.equal(saved.transitions.filter(t=>t.action==='paper_unassociated').length,2);
 const noEvidence=world();const invalid=await main(input('associate',{plan:{...p,assignments:[{...p.assignments[0],evidence_confirmed:false}]}}));
 assert.equal(invalid.error.code,'identity_evidence_required');assert.equal(noEvidence.associationAttempts.length,0);
 const concurrent=world();concurrent.roster.revision=2;
 const conflict=await main(input('associate',{plan:p}));assert.equal(conflict.error.code,'roster_version_conflict');
 assert.equal(conflict.error.current_revision,2);assert.equal(conflict.error.expected_revision,1);
 assert.deepEqual(conflict.error.current_assignments,[{paper_id:'p1',student_id:'11'},{paper_id:'p2',student_id:'12'}]);
 assert.equal(concurrent.associationAttempts.length,0);
 const changed=world(),originalFetch=global.fetch;
 global.fetch=async(path,options)=>{if(options.method==='PATCH'){changed.associationAttempts.push(path);return reply({...changed.roster,revision:2});}return originalFetch(path,options);};
 const unpersisted=await main(input('associate',{plan:{...p,assignments:[p.assignments[0]]}}));
 assert.equal(unpersisted.error.code,'association_not_persisted');
});
test('partial analysis returns source failure locations without answers or retrying',async()=>{
 const w=world();w.a.status='partial';w.a.scan_student_states={p1:'done',p2:'failed'};
 w.a.students=[{id:'p2',issues:['第 1 页识别失败，可重试：相同模型请求已达到三次传输尝试，不能在恢复时重置重试次数'],incomplete_pages:1,
  answers:[{answer_text:'private answer'}]}];
 const d=await main(input('run'));assert(d.ok);assert.equal(d.result.outcome,'needs_targeted_recovery');
 assert.deepEqual(d.result.student_state_counts,{done:1,failed:1});assert.equal(d.result.failed_papers[0].paper_id,'p2');
 assert.deepEqual(d.result.failed_papers[0].pdf_pages,[2,2]);assert(d.result.failed_papers[0].issues[0].includes('三次传输尝试'));
 assert.equal(d.result.retry_authorized,false);assert(!JSON.stringify(d.result).includes('private answer'));
 assert(w.trace.every(([method])=>method==='GET'));
});
test('missing failure details use one version-matched summary read and reject changed-source details',async()=>{
 for(const matched of [true,false]){
  const w=world();w.a.status='partial';w.a.read_version='v1';w.a.scan_student_states={p1:'done',p2:'failed'};
  const originalFetch=global.fetch;let summaries=0;
  global.fetch=async(path,o)=>{
   if(path===B+'/analysis?view=summary'){summaries++;w.trace.push([o.method,path]);return reply({read_version:matched?'v1':'v2',
    students:[{id:'p2',issues:['source failure cause'],incomplete_pages:1}]});}
   return originalFetch(path,o);
  };
  const d=await main(input('run'));assert(d.ok);assert.equal(summaries,1);
  assert.equal(d.result.failure_details_status,matched?'available':'source_changed_or_unversioned');
  assert.deepEqual(d.result.failed_papers[0].issues,matched?['source failure cause']:[]);
  assert.equal(d.result.retry_authorized,false);assert(w.trace.every(([method])=>method==='GET'));
 }
 const exhausted=world();exhausted.a.status='partial';exhausted.a.scan_student_states={p2:'failed'};
 const budget=await main(input('run',{timeout:0}));assert.equal(budget.result.failure_details_status,'budget_exhausted');
 assert(!exhausted.trace.some(([,path])=>path===B+'/analysis?view=summary'));
 const unavailable=world();unavailable.a.status='partial';unavailable.a.scan_student_states={p2:'failed'};
 const previousFetch=global.fetch;
 global.fetch=async(path,o)=>path===B+'/analysis?view=summary'?reply({detail:'unavailable'},503):previousFetch(path,o);
 const missing=await main(input('run'));assert(missing.ok);assert.equal(missing.result.outcome,'needs_targeted_recovery');
 assert.equal(missing.result.failure_details_status,'unavailable');assert.equal(missing.result.failed_papers[0].paper_id,'p2');
 assert.equal(missing.result.retry_authorized,false);
});
test('whole-batch missing counts include absent papers and stay unknown before a catalog exists',async()=>{
 const w=world();w.finish();w.a.students=w.a.students.slice(0,1);
 const absent=await main(input('inspect'));assert(absent.ok);assert.equal(absent.result.expected_answers,4);
 assert.equal(absent.result.answers,2);assert.equal(absent.result.missing_answers,2);
 w.a.students.push(clone(w.a.students[0]));
 const duplicate=await main(input('inspect'));assert.equal(duplicate.result.missing_answers,2);assert.equal(duplicate.result.duplicate_papers.length,1);
 w.a.students[1].id='outside';
 const outside=await main(input('inspect'));assert.equal(outside.result.covered_papers,1);assert.equal(outside.result.missing_answers,2);
 const pending=world();pending.a.status='generating';
 const unknown=await main(input('inspect'));assert.equal(unknown.result.expected_answers,null);assert.equal(unknown.result.missing_answers,null);
 const check=await main(input('check',{skip_unlinked:true}));assert(check.ok);
 assert.equal(check.result.eligible_check.expected_answers,null);assert.equal(check.result.eligible_check.ready,false);
 assert.equal(check.result.eligible_check.coverage_verified,false);
});
test('check keeps analysis failures visible alongside identity and coverage blockers',async()=>{
 const w=world();w.finish();w.a.status='partial';w.a.scan_student_states={p1:'done',p2:'failed'};w.roster.papers[0].student_id=null;
 const d=await main(input('check'));assert(d.ok);assert.equal(d.result.ready,false);
 const codes=d.result.remaining.map(x=>x.code);
 assert(codes.includes('ANALYSIS_INCOMPLETE'));assert(codes.includes('ANALYSIS_FAILED_PAPERS'));assert(codes.includes('IDENTITY_PENDING'));
 assert.deepEqual(d.result.student_state_counts,{done:1,failed:1});assert.deepEqual(d.result.failed_analysis_papers,['p2']);
});

(async()=>{let failed=0;for(const[name,fn]of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.log('FAIL '+name+' '+e.message);}}console.log(JSON.stringify({tests:tests.length,passed:tests.length-failed,failed}));process.exitCode=failed?1:0;})();
'''

if __name__=='__main__':
    import json
    source='const SOURCE='+json.dumps(paperflow.source())+';\n'+TESTS
    result=subprocess.run(['node','-'],input=source,text=True,capture_output=True)
    print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
    sys.exit(result.returncode)
