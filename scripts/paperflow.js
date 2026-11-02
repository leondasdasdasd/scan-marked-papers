async (input) => {
  const legacy = __LEGACY__;
  const B='/api/batches/'+input.batch;
  const calls=[], transitions=[];
  let receipt=input.checkpoint?.frame_receipt||null;
  let associations=input.checkpoint?.association_receipt||null;
  const clone=x=>JSON.parse(JSON.stringify(x));
  const fail=(code,details={})=>{throw Object.assign(new Error(code),{code,details});};
  if(location.origin!==input.origin)return {ok:false,error:{code:'origin_mismatch'}};
  if(input.checkpoint?.batch_id&&(input.checkpoint.origin!==input.origin||input.checkpoint.batch_id!==input.batch))
    return {ok:false,error:{code:'checkpoint_origin_or_batch_mismatch'}};
  async function api(method,path,body) {
    const t=performance.now();
    const response=await fetch(path,{method,credentials:'same-origin',redirect:'error',
      headers:body===undefined?{}:{'Content-Type':'application/json'},
      ...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(45000)});
    calls.push({method,path,status:response.status,ms:Math.round(performance.now()-t)});
    if(!response.ok)fail(response.status===409?'version_conflict':response.status===401?'login_required':'api_failed',{status:response.status,path});
    return response.json();
  }
  const full=()=>api('GET',B+'/analysis?view=catalog');
  const signature=frames=>JSON.stringify(frames.map(f=>({id:f.id,label:f.label,parent_id:f.parent_id||null,regions:f.regions})));
  function composite(q,a){
    const types=a.business_question_catalog?.types||a.question_type_templates||[];
    return (q.composite!==undefined&&q.composite!==null&&q.composite!==false)||q.virtual_parent===true||q.is_composite===true||q.isComposite===true||
      q.business_question?.isComposite===true||(Array.isArray(q.content?.children)&&q.content.children.length>0)||
      (Array.isArray(types)&&types.some(t=>String(t.businessQuestionTypeId)===String(q.businessQuestionTypeId)&&t.isComposite===true));
  }
  function snapshot(batch,a) {
    return {batch_id:batch.id,workflow_mode:batch.workflow_mode,pages_per_paper:batch.pages_per_paper,
      total_pages:batch.total_pages,analysis_status:a.status,frame_revision:a.frame_revision,
      source_pdf_sha256:a.source_pdf_sha256,reference_student_id:a.reference_student_id,
      reference_start:a.reference_start,frames:(a.frames||[]).map(f=>({id:f.id,label:f.label,parent_id:f.parent_id||null,regions:f.regions,source:f.source})),
      questions:(a.questions||[]).map(q=>({id:q.id,label:q.label,parent_id:q.parent_id||null,conversion_status:q.conversion_status,issue_count:(q.issues||[]).length})),
      reviewed:false};
  }
  function validate(frames,pages) {
    if(frames.length>600)fail('invalid_frame_count');
    const ids=new Set();
    for(const f of frames){
      if(typeof f.id!=='string'||!/^[A-Za-z0-9_-]{1,100}$/.test(f.id)||ids.has(f.id))fail('invalid_or_duplicate_frame');
      ids.add(f.id);
      if(typeof f.label!=='string'||!f.label.trim()||f.label.length>100)fail('invalid_frame_label');
      if(!Array.isArray(f.regions)||!f.regions.length||f.regions.length>30)fail('missing_regions');
      for(const r of f.regions){
        const b=r.bbox;
        if(!Number.isInteger(r.page)||r.page<0||r.page>=pages||!Array.isArray(b)||b.length!==4||
          b.some(v=>typeof v!=='number'||!Number.isFinite(v)||v<0||v>1)||b[0]>=b[2]||b[1]>=b[3])fail('invalid_region');
      }
    }
    const byId=Object.fromEntries(frames.map(f=>[f.id,f]));
    for(const f of frames){
      const seen=new Set([f.id]);let parent=f.parent_id;
      while(parent){if(!byId[parent]||seen.has(parent))fail('invalid_frame_hierarchy');seen.add(parent);parent=byId[parent].parent_id;}
    }
    return frames;
  }
  function editFrames(frames,operations,pages){
    let result=clone(frames);
    if(!Array.isArray(operations)||!operations.length)fail('empty_edit_plan');
    for(const op of operations){
      if(op.type==='set'){
        const f=result.find(f=>f.id===op.id);if(!f)fail('frame_not_found');
        if(op.regions)f.regions=clone(op.regions);
        if(op.label!==undefined)f.label=String(op.label);
        f.source='manual';
      }else if(op.type==='shift'){
        if(!Array.isArray(op.ids)||!op.ids.length||![op.dx,op.dy].every(Number.isFinite))fail('invalid_shift');
        for(const id of op.ids){const f=result.find(f=>f.id===id);if(!f)fail('frame_not_found');
          f.regions=f.regions.map(r=>({...r,bbox:r.bbox.map((v,i)=>Number((v+(i%2?op.dy:op.dx)).toFixed(10)))}));f.source='manual';}
      }else if(op.type==='split'){
        const index=result.findIndex(f=>f.id===op.id);
        if(index<0||!Array.isArray(op.children)||op.children.length<2||result.some(f=>f.parent_id===op.id))fail('invalid_independent_split');
        const children=op.children.map(f=>({...clone(f),parent_id:null,source:'manual'}));
        result.splice(index,1,...children);
      }else fail('unsupported_edit');
    }
    return validate(result,pages);
  }
  function reviewGuard(plan,a,batch){
    if(plan.source_pdf_sha256!==a.source_pdf_sha256||plan.reference_student_id!==a.reference_student_id)fail('source_changed');
    const pages=plan.reviewed_pages;
    if(!Array.isArray(pages)||new Set(pages).size!==batch.pages_per_paper||
      pages.some(p=>!Number.isInteger(p)||p<0||p>=batch.pages_per_paper))fail('reference_review_required');
    if(plan.reference_reviewed!==true||plan.scope_reviewed!==true)fail('reference_review_required');
  }
  async function apply(batch,a,plan,confirm){
    if(!plan||typeof plan.operation_id!=='string'||!plan.operation_id)fail('edit_plan_required');
    reviewGuard(plan,a,batch);
    let next,already=false;
    if(receipt?.operation_id===plan.operation_id){
      if(receipt.edit_signature!==JSON.stringify(plan.operations))fail('operation_changed');
      if(receipt.source_pdf_sha256!==a.source_pdf_sha256||receipt.reference_student_id!==a.reference_student_id||
        receipt.after_revision!==a.frame_revision||receipt.frames_signature!==signature(a.frames||[]))fail('checkpoint_changed');
      already=true;next=a;
    }else{
      if(plan.frame_revision!==a.frame_revision)fail('version_conflict');
      if(a.status!=='awaiting_frames')fail('frames_frozen');
      const frames=editFrames(a.frames||[],plan.operations,batch.pages_per_paper);
      next=signature(frames)===signature(a.frames||[])?a:await api('PATCH',B+'/analysis/frames',{
        frame_revision:a.frame_revision,frames,checked_pages:plan.reviewed_pages,current_page:0});
      receipt={operation_id:plan.operation_id,source_pdf_sha256:a.source_pdf_sha256,
        reference_student_id:a.reference_student_id,after_revision:next.frame_revision,frames_signature:signature(next.frames),
        edit_signature:JSON.stringify(plan.operations),
        expected_leaf_labels:plan.expected_leaf_labels,
        independent_labels:plan.operations.filter(op=>op.type==='split').flatMap(op=>op.children.map(f=>f.label))};
      transitions.push({action:'frames_saved',edited_operations:plan.operations.length,frames:next.frames.length});
    }
    if(confirm&&next.status==='awaiting_frames'){
      await api('POST',B+'/analysis/frames/confirm',{frame_revision:next.frame_revision});
      transitions.push({action:'frames_confirmed'});
    }
    return {already_applied:already,frame_revision:next.frame_revision,frame_count:next.frames.length};
  }
  async function inspectOrCheck(action){
    const d=await legacy({...input,action,prepare:action==='check'});
    calls.push(...(d.calls||[]));if(!d.ok)fail(d.error.code,d.error);
    return d.result;
  }
  async function control(){
    const [imports,tasks]=await Promise.all([api('GET',B+'/lesson-practice/imports?check_source=false'),api('GET',B+'/task-control')]);
    if((imports.items||[]).length)return {outcome:'existing_import_readonly',submitted:false};
    for(const task of Object.values(tasks||{})){
      if(task&&['stopping','stopped','paused'].includes(task.state||task.status))return {outcome:'stopped_readonly',submitted:false};
    }
    return null;
  }
  async function associate(plan){
    if(!plan)return;
    let roster=await api('GET',B+'/roster');
    if(!Array.isArray(plan.assignments)||plan.assignments.length>50)fail('invalid_associations');
    const target=JSON.stringify(plan.assignments.map(op=>[op.paper_id,op.student_id]));
    if(roster.revision!==plan.revision&&!(associations?.target===target&&associations.after_revision===roster.revision))fail('roster_version_conflict');
    const pids=new Set(),sids=new Set();
    for(const op of plan.assignments){
      const paper=(roster.papers||[]).find(p=>p.id===op.paper_id);
      if(!paper||!roster.students.some(s=>s.id===op.student_id)||pids.has(op.paper_id)||sids.has(op.student_id)||
        op.evidence_confirmed!==true||typeof op.evidence_note!=='string'||!op.evidence_note.trim())fail('identity_evidence_required');
      if((roster.papers||[]).some(p=>p.id!==op.paper_id&&p.student_id===op.student_id))fail('association_already_occupied');
      pids.add(op.paper_id);sids.add(op.student_id);
    }
    const saved=[];
    for(const op of plan.assignments){
      if((roster.papers||[]).find(p=>p.id===op.paper_id)?.student_id===op.student_id)continue;
      roster=await api('PATCH',B+'/roster/'+op.paper_id,{revision:roster.revision,student_id:op.student_id});saved.push(op.paper_id);
      associations={target,after_revision:roster.revision};
      transitions.push({action:'paper_associated',paper_id:op.paper_id});
    }
    const read=await api('GET',B+'/roster');
    if(plan.assignments.some(op=>!read.papers.some(p=>p.id===op.paper_id&&p.student_id===op.student_id)))fail('association_not_persisted');
    return {saved,revision:read.revision};
  }
  async function selectScope(plan){
    if(!plan)return;
    if(plan.evidence_confirmed!==true||typeof plan.evidence_note!=='string'||!plan.evidence_note.trim())fail('scope_evidence_required');
    const current=await api('GET',B+'/roster');
    const ids=(current.classes||[]).map(c=>c.id).sort();
    const same=current.semester_id===plan.semester_id&&JSON.stringify(ids)===JSON.stringify([...(plan.class_ids||[])].sort())&&
      Object.entries(plan.scope||{}).every(([k,v])=>current.scope?.[k]===v);
    if(same)return;
    if(current.revision!==plan.revision)fail('roster_version_conflict');
    await api('PUT',B+'/roster',{revision:plan.revision,semester_id:plan.semester_id,class_ids:plan.class_ids,scope:plan.scope});
    transitions.push({action:'scope_selected'});
  }
  async function run(){
    const readonly=await control();if(readonly)return readonly;
    const batch=await api('GET',B);
    if(batch.workflow_mode!=='scan')return {outcome:'unsupported_workflow',submitted:false};
    await selectScope(input.plan?.scope);
    let a=await full();
    if(a.stale)return {outcome:'source_stale',submitted:false};
    if(!a.status||a.status==='not_generated'){
      const reference=input.plan?.reference_student_id;
      if(!batch.students.some(s=>s.id===reference))return {outcome:'needs_reference',candidates:batch.students.slice(0,5).map(s=>({id:s.id,index:s.index})),submitted:false};
      await api('POST',B+'/analysis',{reference_student_id:reference});transitions.push({action:'analysis_started'});
      a=await full();
    }
    const deadline=performance.now()+input.timeout*1000;
    const visited=new Set();
    for(let n=0;n<25;n++){
      if(a.status==='awaiting_frames'){
        if(!input.plan?.frames)return {outcome:'needs_frame_review',review:snapshot(batch,a),submitted:false};
        await apply(batch,a,input.plan.frames,true);a=await full();
      }else if(['generating','catalog_confirmed','frames_confirmed','processing'].includes(a.status)){
        let state;
        do{
          state=await api('GET',B+'/analysis/status');
          if(!['generating','catalog_confirmed','frames_confirmed','processing'].includes(state.status))break;
          if(performance.now()>=deadline)return {outcome:'waiting',analysis_status:state.status,submitted:false};
          await new Promise(resolve=>setTimeout(resolve,input.interval*1000));
        }while(true);
        a=await full();
      }else if(a.status==='awaiting_confirmation'){
        return {outcome:'needs_catalog_review',review:snapshot(batch,a),submitted:false};
      }else if(a.status==='completed'){
        if(receipt&&(receipt.after_revision!==a.frame_revision||receipt.source_pdf_sha256!==a.source_pdf_sha256||
          receipt.reference_student_id!==a.reference_student_id||receipt.frames_signature!==signature(a.frames||[])))fail('checkpoint_changed');
        const expected=input.plan?.frames?.expected_leaf_labels||input.plan?.expected_leaf_labels||receipt?.expected_leaf_labels;
        const parents=new Set((a.questions||[]).map(q=>q.parent_id).filter(Boolean));
        const leaves=(a.questions||[]).filter(q=>!parents.has(q.id));
        if(expected&&(!Array.isArray(expected)||expected.length!==leaves.length||
          new Set(expected).size!==expected.length||expected.some(label=>!leaves.some(q=>q.label===label))))fail('business_split_mismatch');
        const independent=receipt?.independent_labels||[];
        if(independent.some(label=>!leaves.some(q=>q.label===label&&!q.parent_id&&!composite(q,a))))fail('business_split_mismatch');
        const unconverted=(a.questions||[]).some(q=>q.conversion_status!=='converted');
        if(unconverted)return {outcome:'needs_catalog_review',review:snapshot(batch,a),submitted:false};
        if(input.plan?.associations)await associate(input.plan.associations);
        const check=await inspectOrCheck('check');
        return {...check,visual_review_performed:!!receipt||input.plan?.reference_reviewed===true,
          expected_granularity_verified:!!expected,submitted:false};
      }else return {outcome:['partial','failed'].includes(a.status)?'needs_targeted_recovery':'unknown_stage',analysis_status:a.status,submitted:false};
      const key=JSON.stringify([a.status,a.frame_revision,a.catalog_revision]);
      if(visited.has(key))return {outcome:'no_progress',analysis_status:a.status,submitted:false};
      visited.add(key);
      if(performance.now()>=deadline)return {outcome:'waiting',submitted:false};
    }
    return {outcome:'iteration_limit',submitted:false};
  }
  try{
    let result;
    if(input.action==='snapshot'){
      const [b,a]=await Promise.all([api('GET',B),full()]);result=snapshot(b,a);
    }else if(input.action==='frames'){
      const stop=await control();if(stop)result=stop;
      else{const [b,a]=await Promise.all([api('GET',B),full()]);result=await apply(b,a,input.plan,input.confirm);}
    }else if(input.action==='associate'){
      const stop=await control();result=stop||await associate(input.plan);
    }
    else if(input.action==='run')result=await run();
    else if(input.action==='check'){
      const stop=await control();result=stop||await inspectOrCheck(input.action);
    }else result=await inspectOrCheck(input.action);
    return {ok:true,result,transitions,calls,checkpoint:{origin:input.origin,batch_id:input.batch,frame_receipt:receipt,association_receipt:associations}};
  }catch(error){return {ok:false,error:{code:error.code||'transport_failed',...(error.details||{})},transitions,calls,
    checkpoint:{origin:input.origin,batch_id:input.batch,frame_receipt:receipt,association_receipt:associations}};}
}
