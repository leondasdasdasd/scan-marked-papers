async (input) => {
  const legacy = __LEGACY__;
  const workflowFactory = __WORKFLOW__;
  let uploadReceipt=input.checkpoint?.upload_receipt||null;
  const B='/api/batches/'+input.batch;
  const calls=[], transitions=[];
  let receipt=input.checkpoint?.frame_receipt||null;
  let associations=input.checkpoint?.association_receipt||null;
  let catalogReceipt=input.checkpoint?.catalog_receipt||null;
  let authReceipt=input.checkpoint?.auth_receipt||null;
  const clone=x=>JSON.parse(JSON.stringify(x));
  const fail=(code,details={})=>{throw Object.assign(new Error(code),{code,details});};
  if(location.origin!==input.origin)return {ok:false,error:{code:'origin_mismatch'}};
  if(input.checkpoint?.origin&&(input.checkpoint.origin!==input.origin||input.batch&&input.checkpoint.batch_id!==input.batch))
    return {ok:false,error:{code:'checkpoint_origin_or_batch_mismatch'}};
  async function api(method,path,body,extraHeaders={}) {
    const t=performance.now();
    let response;
    try{response=await fetch(path,{method,credentials:'same-origin',redirect:'error',
      headers:{...(body===undefined||body instanceof FormData?{}:{'Content-Type':'application/json'}),...extraHeaders},
      ...(body===undefined?{}:{body:body instanceof FormData?body:JSON.stringify(body)}),signal:AbortSignal.timeout(45000)});}
    catch{fail('transport_uncertain',{method,path,retryable:false,next_action:'read_state_before_retry'});}
    calls.push({method,path,status:response.status,ms:Math.round(performance.now()-t)});
    if(!response.ok){
      let value;try{value=await response.json();}catch{}
      const detail=value?.detail;
      const message=typeof detail==='string'?detail:typeof detail?.message==='string'?detail.message:undefined;
      const serverCode=response.headers?.get?.('X-Error-Code')||detail?.code;
      let code=response.status===409?'version_conflict':response.status===401?'login_required':
        response.status===403?'permission_denied':response.status===422?'validation_failed':
        [404,405].includes(response.status)?'contract_mismatch':response.status===429?'rate_limited':'api_failed';
      if(response.status===422&&message==='标准卷选择格式无效')code='invalid_json_body';
      const classroomAuth=response.status===428&&(serverCode==='classroom_login_required'||serverCode==='GATEWAY_AUTHORIZATION'||
        /云谷登录已失效|课堂会话已失效|课堂登录已失效|云谷账号与当前批阅台账号不一致|学校 AI 登录(?:已失效|已退出|身份已变化|权限已变化)/.test(message||''));
      if(classroomAuth)code='classroom_login_required';
      const next={classroom_login_required:'check_access_then_relogin',invalid_json_body:'verify_json_transport',validation_failed:'inspect_validation_detail',
        version_conflict:'read_current_version',login_required:'restore_authorized_session',
        permission_denied:'verify_identity_scope',contract_mismatch:'verify_deployed_contract',
        rate_limited:'wait_before_reading_state',api_failed:'read_state_before_retry'};
      fail(code,{status:response.status,method,path,retryable:false,next_action:next[code],
        ...(message?{message:message.slice(0,500)}:{}),
        ...(Array.isArray(detail)?{validation_errors:detail.slice(0,8).map(e=>({location:e.loc,type:e.type,message:String(e.msg||'').slice(0,300)}))}:{}),
        ...(typeof serverCode==='string'?{server_code:serverCode.slice(0,100)}:{})});
    }
    try{return await response.json();}
    catch{fail('invalid_api_response',{method,path,retryable:false,next_action:'read_state_before_retry'});}
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
      total_pages:batch.total_pages,analysis_status:a.status,read_version:a.read_version,frame_revision:a.frame_revision,
      catalog_revision:a.catalog_revision,analysis_confirmation_version:batch.analysis_confirmation_version||a.analysis_confirmation_version,
      source_pdf_sha256:a.source_pdf_sha256,reference_student_id:a.reference_student_id,
      reference_start:a.reference_start,frames:(a.frames||[]).map(f=>({id:f.id,label:f.label,parent_id:f.parent_id||null,regions:f.regions,source:f.source})),
      questions:(a.questions||[]).map(catalogQuestion),
      reference_pages:Number.isInteger(a.reference_start)?Array.from({length:batch.pages_per_paper},(_,i)=>({page:i,
        url:input.origin+B+'/pages/'+(a.reference_start+i)+'?original=true&student_id='+encodeURIComponent(a.reference_student_id)})):[],
      reviewed:false};
  }
  function catalogQuestion(q){
    const text=v=>typeof v==='string'?v:typeof v?.text==='string'?v.text:'';
    const plain=v=>Array.isArray(v)?v.map(plain):v&&typeof v==='object'?
      typeof v.text==='string'?{text:v.text}:Object.fromEntries(Object.entries(v).filter(([k])=>!['html','json'].includes(k)).map(([k,x])=>[k,plain(x)])):v;
    return {id:q.id,label:q.label,parent_id:q.parent_id||null,conversion_status:q.conversion_status,
      issue_count:(q.issues||[]).length,question_type_key:q.content?.questionTypeKey,
      child_count:(q.content?.children||[]).length,
      elements:(q.content?.elements||[]).map(e=>({type:e.type,text:text(e.content),
        ...(e.options?{selection_type:e.config?.selectionType,options:e.options.map((o,i)=>({id:o.id,position:i+1,
          text:(o.cells||[]).map(text),...(o.label?{label:o.label}:{})}))}:{}),
        ...(e.blanks?{blank_ids:e.blanks}:{}),...(e.answers!==undefined?{answers:plain(e.answers)}:{})})),
      blank_definitions:(q.blanks||[]).map(b=>({id:b.id,label:b.label})),
      extras:(q.content?.extras||[]).filter(e=>text(e.content)).map(e=>({type:e.type,text:text(e.content)}))};
  }
  function frameProblem(a,pages){
    const failed=a.localization_failed_pages||[],issues=a.localization_issues||[];
    const retryPages=failed.length?failed:!(a.frames||[]).length&&Number.isInteger(pages)&&pages>0?
      Array.from({length:pages},(_,i)=>i):[];
    if(!(a.frames||[]).length||failed.length||issues.length)return {
      code:!(a.frames||[]).length?'precut_empty':'precut_pages_failed',failed_pages:failed,
      issues:issues.map(s=>String(s).slice(0,500)),frame_revision:a.frame_revision,
      retryable_pages:retryPages.filter(p=>!(a.frames||[]).some(f=>f.source==='manual'&&f.regions.some(r=>r.page===p)))};
    return null;
  }
  function reviewTasks(check,a,batch){
    const grouped=new Map();
    for(const issue of check.check?.issues||[]){
      if(!['blocker','failure'].includes(issue.severity))continue;
      const pid=issue.paper_id||null;
      if(!grouped.has(pid)){
        const paper=batch.students.find(s=>s.id===pid);
        grouped.set(pid,{paper_id:pid,index:paper?.index,pdf_pages:paper?[paper.start+1,paper.start+batch.pages_per_paper]:null,issues:[]});
      }
      grouped.get(pid).issues.push(issue);
    }
    const qids=new Set([...grouped.values()].flatMap(g=>g.issues.map(i=>i.question_id).filter(Boolean)));
    return {paper_count:grouped.size,issue_count:[...grouped.values()].reduce((n,g)=>n+g.issues.length,0),
      papers:[...grouped.values()],questions:(a.questions||[]).filter(q=>qids.has(q.id)).map(catalogQuestion),
      identity_pending:check.unlinked||[],accuracy_verified:false};
  }
  function validate(frames,pages) {
    if(!Array.isArray(frames)||frames.length<1||frames.length>600)fail('invalid_frame_count');
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
    if(!Array.isArray(operations))fail('empty_edit_plan');
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
      }else if(op.type==='promote_children'){
        const parent=result.find(f=>f.id===op.id);
        const existing=result.filter(f=>f.parent_id===op.id),ids=new Set(existing.map(f=>f.id));
        if(!parent||parent.parent_id||existing.length<2||!Array.isArray(op.children)||
          op.children.length!==existing.length||new Set(op.children.map(f=>f.id)).size!==ids.size||
          op.children.some(f=>!ids.has(f.id)||!Array.isArray(f.regions)||!f.regions.length)||
          result.some(f=>ids.has(f.parent_id)))fail('invalid_independent_promotion');
        const index=result.findIndex(f=>f.id===op.id);
        const children=op.children.map(f=>({...clone(existing.find(old=>old.id===f.id)),...clone(f),parent_id:null,source:'manual'}));
        result=result.filter(f=>f.id!==op.id&&!ids.has(f.id));result.splice(Math.min(index,result.length),0,...children);
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
    if(frameProblem(a,batch.pages_per_paper)&&!plan.operations?.length)fail('precut_recovery_required');
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
        independent_labels:plan.operations.filter(op=>['split','promote_children'].includes(op.type)).flatMap(op=>op.children.map(f=>f.label))};
      transitions.push({action:'frames_saved',edited_operations:plan.operations.length,frames:next.frames.length});
    }
    if(confirm&&next.status==='awaiting_frames'){
      await api('POST',B+'/analysis/frames/confirm',{frame_revision:next.frame_revision});
      transitions.push({action:'frames_confirmed'});
    }
    return {already_applied:already,frame_revision:next.frame_revision,frame_count:next.frames.length};
  }
  async function inspectOrCheck(action,snapshot){
    const d=await legacy({...input,action,snapshot,api,prepare:action==='check'});
    calls.push(...(d.calls||[]));if(!d.ok)fail(d.error.code,d.error);
    return d.result;
  }
  async function control({resume=false}={}){
    const [imports,tasks]=await Promise.all([api('GET',B+'/lesson-practice/imports?check_source=false'),api('GET',B+'/task-control')]);
    if((imports.items||[]).length)return {outcome:'existing_import_readonly',submitted:false};
    for(const task of Object.values(tasks||{})){
      if((task?.state||task?.status)==='stopping')return {outcome:resume?'waiting':'stopped_readonly',waiting_for:'task_stop',submitted:false};
      if(task&&['stopped','paused'].includes(task.state||task.status)&&!resume)return {outcome:'stopped_readonly',submitted:false};
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
    if(same)return current;
    if(current.revision!==plan.revision)fail('roster_version_conflict');
    await api('PUT',B+'/roster',{revision:plan.revision,semester_id:plan.semester_id,class_ids:plan.class_ids,scope:plan.scope});
    const saved=await api('GET',B+'/roster');
    if(saved.semester_id!==plan.semester_id||JSON.stringify((saved.classes||[]).map(c=>c.id).sort())!==JSON.stringify([...plan.class_ids].sort())||
      Object.entries(plan.scope||{}).some(([k,v])=>saved.scope?.[k]!==v))fail('scope_not_persisted');
    transitions.push({action:'scope_selected'});return saved;
  }
  async function evidence(plan){
    const [batch,a]=await Promise.all([api('GET',B),full()]);
    const paper=batch.students.find(s=>s.id===plan?.paper_id);if(!paper)fail('paper_not_found');
    const ids=plan.question_ids;
    if(ids&&(!Array.isArray(ids)||!ids.length||ids.length>50||new Set(ids).size!==ids.length||
      ids.some(id=>!(a.questions||[]).some(q=>q.id===id))))fail('invalid_question_selection');
    const d=await api('GET',B+'/analysis/students/'+paper.id),student=d.student||{};
    return {source_pdf_sha256:a.source_pdf_sha256,frame_revision:a.frame_revision,catalog_revision:a.catalog_revision,
      paper_id:paper.id,index:paper.index,pdf_pages:[paper.start+1,paper.start+batch.pages_per_paper],
      questions:(a.questions||[]).filter(q=>!ids||ids.includes(q.id)).map(catalogQuestion),
      observations:(student.answers||[]).filter(x=>!ids||ids.includes(x.question_id)).map(x=>({
        question_id:x.question_id,verdict:x.verdict,answer_text:x.answer_text,answer_state:x.answer_state,
        response_conversion_status:x.response_conversion_status,
        blanks:(x.blanks||[]).map(b=>({blank_id:b.blank_id,answer_text:b.answer_text,answer_state:b.answer_state,verdict:b.verdict})),
        response_regions:x.response_regions||[],source_refs:x.source_refs||[]})),reviewed:false,submitted:false};
  }
  async function responses(plan){
    const stop=await control();if(stop)return stop;
    const [batch,initial]=await Promise.all([api('GET',B),api('GET',B+'/analysis')]);let a=initial;
    if(!workflow.organizer(batch))fail('unsupported_workflow');
    if(a.stale||a.status!=='completed')fail('source_not_completed');
    if(!plan||!plan.frame_revision||plan.catalog_revision===undefined||!plan.source_pdf_sha256||
      plan.source_pdf_sha256!==a.source_pdf_sha256||plan.frame_revision!==a.frame_revision||
      plan.catalog_revision!==a.catalog_revision)fail('response_source_changed');
    if(!Array.isArray(plan.assignments)||!plan.assignments.length||plan.assignments.length>100)fail('invalid_responses');
    const seen=new Set(),prepared=[];
    for(const op of plan.assignments){
      const key=JSON.stringify([op.paper_id,op.question_id]);
      const q=(a.questions||[]).find(q=>q.id===op.question_id),s=(a.students||[]).find(s=>s.id===op.paper_id);
      if(seen.has(key)||!q||!batch.students.some(p=>p.id===op.paper_id)||!s?.answers?.some(x=>x.question_id===op.question_id)||
        op.evidence_confirmed!==true||typeof op.evidence_note!=='string'||!op.evidence_note.trim())fail('response_evidence_required');
      seen.add(key);
      const elements=(q.content?.elements||[]).filter(e=>e.type!=='richText');
      if(elements.length!==1)fail('unsupported_response_type');
      const e=elements[0];let response;
      if(e.type==='choice'){
        const positions=op.selected_option_positions,options=e.options||[];
        if(!Array.isArray(positions)||!positions.length||new Set(positions).size!==positions.length||
          positions.some(p=>!Number.isInteger(p)||p<1||p>options.length)||
          (e.config?.selectionType==='single'&&positions.length!==1))fail('invalid_observed_options');
        const ids=positions.map(p=>options[p-1].id);
        if(ids.some(id=>typeof id!=='string'||!id))fail('invalid_option_ids');
        response={answer_text:ids.join(','),blanks:[]};
      }else if(e.type==='inlineFill'){
        const expected=(q.blanks||[]).map(b=>b.id);
        if(!expected.length||!Array.isArray(op.blanks)||op.blanks.length!==expected.length||
          new Set(op.blanks.map(b=>b.blank_id)).size!==expected.length||
          op.blanks.some(b=>!expected.includes(b.blank_id)||typeof b.answer_text!=='string'||b.answer_text.length>10000||
            !['answered','unanswered'].includes(b.answer_state)||
            (b.answer_state==='answered'?!b.answer_text.trim():!!b.answer_text.trim())))fail('invalid_observed_blanks');
        const blanks=expected.map(id=>{const b=op.blanks.find(b=>b.blank_id===id);return {blank_id:id,answer_text:b.answer_text,answer_state:b.answer_state};});
        response={answer_text:blanks.map(b=>b.answer_text).join('；'),blanks};
      }else if(e.type==='textResponse'){
        if(typeof op.answer_text!=='string'||!op.answer_text.trim()||op.answer_text.length>30000)fail('invalid_observed_text');
        response={answer_text:op.answer_text,blanks:[]};
      }else fail('unsupported_response_type');
      prepared.push({paper_id:op.paper_id,question_id:op.question_id,response});
    }
    for(const op of prepared){
      if(!a.review_token)fail('review_token_missing');
      a=await api('PATCH',B+'/analysis/students/'+op.paper_id+'/questions/'+op.question_id,
        {review_token:a.review_token,response_only:true,response:op.response});
      transitions.push({action:'response_saved',paper_id:op.paper_id,question_id:op.question_id});
    }
    return {outcome:'responses_saved',saved:prepared.length,changed_teacher_verdicts:false,submitted:false};
  }
  function granularity(a,expected,independent=[]){
    const parents=new Set((a.questions||[]).map(q=>q.parent_id).filter(Boolean));
    const leaves=(a.questions||[]).filter(q=>!parents.has(q.id));
    if(expected&&(!Array.isArray(expected)||expected.length!==leaves.length||
      new Set(expected).size!==expected.length||expected.some(label=>!leaves.some(q=>q.label===label))))fail('business_split_mismatch');
    if(independent.some(label=>!leaves.some(q=>q.label===label&&!q.parent_id&&!composite(q,a))))fail('business_split_mismatch');
    return leaves;
  }
  async function confirmCatalog(batch,a,plan){
    if(!workflow.organizer(batch))fail('unsupported_workflow');
    if(catalogReceipt?.operation_id===plan?.operation_id){
      if(catalogReceipt.plan_signature!==JSON.stringify(plan))fail('operation_changed');
      if(plan.source_pdf_sha256!==a.source_pdf_sha256||plan.reference_student_id!==a.reference_student_id)fail('source_changed');
      if(catalogReceipt.state==='accepted'&&a.status!=='awaiting_confirmation')return {outcome:'catalog_confirmation_accepted',already_applied:true,submitted:false};
      return {outcome:'needs_confirmation_recovery',operation_id:catalogReceipt.server_operation_id||null,
        next_action:'read_confirmation_operation',submitted:false};
    }
    if(a.stale||a.status!=='awaiting_confirmation')fail('catalog_not_awaiting_confirmation');
    reviewGuard(plan||{},a,batch);
    if(typeof plan.operation_id!=='string'||!/^[A-Za-z0-9_-]{8,100}$/.test(plan.operation_id)||
      plan.catalog_reviewed!==true||plan.frame_revision!==a.frame_revision||plan.catalog_revision!==a.catalog_revision)
      fail('catalog_review_required');
    if(!(a.questions||[]).length||(a.questions||[]).some(q=>q.conversion_status!=='converted'))fail('catalog_not_converted');
    granularity(a,plan.expected_leaf_labels||receipt?.expected_leaf_labels,receipt?.independent_labels||[]);
    // Fetch authoritative rich questions here; the agent need not copy them through a plan.
    // Editing remains a separate save; this operation confirms only the version actually reviewed.
    let body={frame_revision:a.frame_revision,catalog_revision:a.catalog_revision,questions:a.questions};
    if((batch.analysis_confirmation_version||a.analysis_confirmation_version)===2){
      const pre=await api('POST',B+'/merge-preflight',{source_ids:[],frame_revision:a.frame_revision,catalog_revision:a.catalog_revision});
      if(!Array.isArray(pre.duplicates)||!pre.preflight_token||!pre.versions||!pre.operation_id)fail('invalid_confirmation_preflight');
      if(pre.duplicates.length)return {outcome:'needs_duplicate_review',duplicates:pre.duplicates,submitted:false};
      if(pre.source_ids?.length)fail('unexpected_merge_scope');
      body={...body,preflight_token:pre.preflight_token,source_versions:pre.versions,duplicate_choices:{},
        same_paper_confirmed:false,name:batch.name,name_revision:batch.name_revision||0,idempotency_key:plan.operation_id};
      catalogReceipt={operation_id:plan.operation_id,plan_signature:JSON.stringify(plan),
        source_pdf_sha256:a.source_pdf_sha256,reference_student_id:a.reference_student_id,
        expected_leaf_labels:plan.expected_leaf_labels||receipt?.expected_leaf_labels,
        server_operation_id:pre.operation_id,state:'confirming'};
      const accepted=await api('POST',B+'/analysis/confirm-and-start',body);
      if(accepted.status!=='accepted'||accepted.operation_id!==pre.operation_id)fail('invalid_confirmation_response');
      catalogReceipt.state='accepted';
      if(accepted.operation_id)catalogReceipt.server_operation_id=accepted.operation_id;
    }else{
      catalogReceipt={operation_id:plan.operation_id,plan_signature:JSON.stringify(plan),
        source_pdf_sha256:a.source_pdf_sha256,reference_student_id:a.reference_student_id,
        expected_leaf_labels:plan.expected_leaf_labels||receipt?.expected_leaf_labels,state:'confirming'};
      await api('POST',B+'/analysis/confirm',body);catalogReceipt.state='accepted';
    }
    transitions.push({action:'catalog_confirmed',operation_id:catalogReceipt.server_operation_id||null});
    return {outcome:'catalog_confirmation_accepted',operation_id:catalogReceipt.server_operation_id||null,submitted:false};
  }
  function principal(user){
    if(!user||!['employee','teacher'].includes(user.identity)||!user.id||!user.school_id)return null;
    return {user_id:String(user.id),school_id:String(user.school_id),identity:user.identity};
  }
  function rememberPrincipal(user){
    const value=principal(user);if(!value)fail('teacher_identity_required');
    if(authReceipt?.principal&&JSON.stringify(value)!==JSON.stringify(authReceipt.principal))fail('identity_changed',{
      next_action:'verify_identity_scope',retryable:false});
    authReceipt={...authReceipt,principal:value};return value;
  }
  async function access(){
    const session=await api('GET','/api/session?refresh_profile=false&include_models=false');
    const current=rememberPrincipal(session.user);
    let check;
    try{check=await api('GET','/api/classroom/login-check');}
    catch(error){
      if(error.code!=='classroom_login_required')throw error;
      return {outcome:'classroom_login_required',authenticated:true,principal:current,classroom_valid:false,
        next_action:'relogin',submitted:false};
    }
    // The deployed login-check can return HTTP 200 with an embedded authentication failure.
    const status=check['状态码'];const code=check['错误类型'];const message=check['检查结果']||'';
    const valid=check['课堂会话']==='有效'&&check['云谷会话']==='有效且账号一致';
    if(valid){authReceipt.recovery_started=false;return {outcome:'access_verified',authenticated:true,
      principal:current,classroom_valid:true,submitted:false};}
    const loginRequired=status===428&&(code==='classroom_login_required'||code==='GATEWAY_AUTHORIZATION'||
      /云谷登录已失效|课堂会话已失效|课堂登录已失效|学校 AI 登录(?:已失效|已退出|身份已变化|权限已变化)/.test(message));
    return {outcome:loginRequired?'classroom_login_required':'authentication_unverified',authenticated:true,
      principal:current,classroom_valid:false,next_action:loginRequired?'relogin':'inspect_authentication_failure',
      ...(Number.isInteger(status)?{status}:{}),...(typeof code==='string'?{server_code:code}:{}),submitted:false};
  }
  async function relogin(){
    if(authReceipt?.recovery_started)return {outcome:'authentication_recovery_pending',
      next_action:'finish_login_then_access',submitted:false};
    if(typeof document!=='undefined'&&document.querySelector('[role="dialog"],dialog[open],textarea:focus,input:focus,[contenteditable="true"]:focus'))
      return {outcome:'authentication_navigation_deferred',next_action:'preserve_page_edits',submitted:false};
    // This opt-in command starts the existing deployed forced-login flow. The CAS URL stays in memory.
    // It does not assume the newer /auth/refresh route has been deployed.
    if(!authReceipt?.principal){
      try{const session=await api('GET','/api/session?refresh_profile=false&include_models=false');rememberPrincipal(session.user);}
      catch(error){if(error.code!=='login_required')throw error;}
    }
    const path=input.batch?'/exams/'+input.batch+'/analysis':'/';
    const login=await api('POST','/api/login?force=true&return_to='+encodeURIComponent(path));
    let target;try{target=new URL(login.login_url,input.origin);}catch{fail('invalid_login_response');}
    if(!['http:','https:'].includes(target.protocol)||target.username||target.password||!login.login_url||
      (new URL(input.origin).protocol==='https:'&&target.protocol!=='https:'))fail('invalid_login_response');
    authReceipt={...authReceipt,recovery_started:true};
    setTimeout(()=>location.assign(target.href),250);
    return {outcome:'authentication_navigation_started',next_action:'finish_login_then_access',submitted:false};
  }
  async function roster(){
    const [batch,r]=await Promise.all([api('GET',B),api('GET',B+'/roster')]);
    const expected=new Set(batch.students.map(p=>p.id));
    const complete=r.papers.length===expected.size&&new Set(r.papers.map(p=>p.id)).size===expected.size&&r.papers.every(p=>expected.has(p.id));
    const unlinked=r.papers.filter(p=>!p.student_id).map(p=>{
      const paper=batch.students.find(b=>b.id===p.id);const name=typeof p.name==='string'?p.name:'';
      return {paper_id:p.id,index:p.index,pdf_pages:paper?[paper.start+1,paper.start+batch.pages_per_paper]:null,
        recognized_name:name,name_confirmed:p.name_confirmed===true,status:p.status,
        exact_name_candidates:name?(r.students||[]).filter(s=>s.name===name).map(s=>({id:s.id,name:s.name})):[],
        evidence_confirmed:false,
        pages:paper?Array.from({length:batch.pages_per_paper},(_,i)=>input.origin+B+'/pages/'+(paper.start+i)+
          '?original=true&student_id='+encodeURIComponent(p.id)):[]};
    });
    return {outcome:!complete?'roster_coverage_gap':unlinked.length?'identity_pending':'identities_linked',revision:r.revision,
      papers:expected.size,linked:r.papers.filter(p=>p.student_id).length,roster_coverage_complete:complete,
      unlinked,submitted:false};
  }
  const workflow=workflowFactory({input,api,fail,full,selectScope,inspectOrCheck,control,transitions,
    getUpload:()=>uploadReceipt,setUpload:r=>uploadReceipt=r});
  async function run(){
    const readonly=await control({resume:input.plan?.resume_authorized===true});if(readonly)return readonly;
    const batch=await api('GET',B);
    if(!['scan','grading'].includes(batch.workflow_mode))return {outcome:'unsupported_workflow',submitted:false};
    await selectScope(input.plan?.scope);
    if(batch.workflow_mode==='grading'){
      const pending=await workflow.grade(batch);if(pending)return pending;
    }
    let a=await full();
    if(batch.workflow_mode==='grading'&&!workflow.organizer(batch)&&(!a.status||a.status==='not_generated')){
      await api('POST',B+'/lesson-practice/prepare-analysis');transitions.push({action:'analysis_preparation_started'});a=await full();
    }
    if(!workflow.organizer(batch)&&(!a.status||a.status==='not_generated'))return {outcome:'needs_analysis_recovery',submitted:false};
    if(a.stale)return {outcome:'source_stale',submitted:false};
    if(!a.status||a.status==='not_generated'){
      const reference=input.plan?.reference_student_id;
      if(!batch.students.some(s=>s.id===reference)){
        const rate=s=>{const rows=s.judgments?.length?s.judgments:s.results;
          return Array.isArray(rows)&&rows.length&&rows.every(r=>['correct','incorrect','partial','unanswered'].includes(r.verdict))?
            rows.filter(r=>r.verdict==='correct').length/rows.length:null;};
        const ranked=batch.workflow_mode==='grading'&&batch.students.every(s=>rate(s)!==null);
        const candidates=ranked?[...batch.students].sort((x,y)=>rate(y)-rate(x)||x.index-y.index):batch.students;
        return {outcome:'needs_reference',papers:batch.students.length,reference_ranking:ranked?'existing_grading_verdicts':'first_papers',
          candidates:candidates.slice(0,5).map(s=>({id:s.id,index:s.index,pdf_pages:[s.start+1,s.start+batch.pages_per_paper],
            ...(ranked?{correct_rate:rate(s)}:{}),pages:Array.from({length:batch.pages_per_paper},(_,i)=>input.origin+B+'/pages/'+(s.start+i)+'?original=true&student_id='+encodeURIComponent(s.id))})),submitted:false};
      }
      await api('POST',B+'/analysis',{reference_student_id:reference});transitions.push({action:'analysis_started'});
      a=await full();
    }
    const deadline=performance.now()+input.timeout*1000;
    const visited=new Set();
    for(let n=0;n<25;n++){
      if(a.status==='awaiting_frames'){
        const problem=frameProblem(a,batch.pages_per_paper);
        if(problem&&!input.plan?.frames)return {outcome:'needs_precut_recovery',diagnosis:problem,submitted:false};
        if(!input.plan?.frames)return {outcome:'needs_frame_review',review:snapshot(batch,a),submitted:false};
        await apply(batch,a,input.plan.frames,true);a=await full();
      }else if(['generating','catalog_confirmed','frames_confirmed','processing'].includes(a.status)){
        let state;
        do{
          state=await api('GET',B+'/analysis/status');
          if(!['generating','catalog_confirmed','frames_confirmed','processing'].includes(state.status))break;
          if(performance.now()>=deadline)return {outcome:'waiting',analysis_status:state.status,progress:state.progress,submitted:false};
          await new Promise(resolve=>setTimeout(resolve,input.interval*1000));
        }while(true);
        a=await full();
      }else if(a.status==='awaiting_confirmation'){
        if(input.plan?.catalog){
          const confirmed=await confirmCatalog(batch,a,input.plan.catalog);
          if(confirmed.outcome!=='catalog_confirmation_accepted')return confirmed;
          a=await full();
          if(a.status==='awaiting_confirmation')return {outcome:'waiting',analysis_status:a.status,submitted:false};
          continue;
        }
        return {outcome:'needs_catalog_review',review:snapshot(batch,a),submitted:false};
      }else if(a.status==='completed'){
        if(receipt&&(receipt.after_revision!==a.frame_revision||receipt.source_pdf_sha256!==a.source_pdf_sha256||
          receipt.reference_student_id!==a.reference_student_id||receipt.frames_signature!==signature(a.frames||[])))fail('checkpoint_changed');
        const expected=input.plan?.frames?.expected_leaf_labels||input.plan?.expected_leaf_labels||receipt?.expected_leaf_labels||catalogReceipt?.expected_leaf_labels;
        if(catalogReceipt&&(catalogReceipt.source_pdf_sha256!==a.source_pdf_sha256||catalogReceipt.reference_student_id!==a.reference_student_id))fail('source_changed');
        granularity(a,expected,receipt?.independent_labels||[]);
        const unconverted=(a.questions||[]).some(q=>q.conversion_status!=='converted');
        if(unconverted)return {outcome:'needs_catalog_review',review:snapshot(batch,a),submitted:false};
        if(input.plan?.associations)await associate(input.plan.associations);
        const check=await inspectOrCheck('check',{batch});
        return {...check,...(check.waiting_for_media?{outcome:'waiting',waiting_for:'media',analysis_status:a.status}:{}),visual_review_performed:!!receipt||catalogReceipt?.state==='accepted'||input.plan?.reference_reviewed===true,
          expected_granularity_verified:!!expected,review_tasks:reviewTasks(check,a,batch),submitted:false};
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
    if(authReceipt?.recovery_started&&['run','frames','catalog','associate','responses','retry-precut','check','upload','scope','api-call','sync'].includes(input.action)){
      const checked=await access();
      if(checked.outcome!=='access_verified')fail('classroom_login_required',{next_action:'finish_login_then_access',retryable:false});
    }
    if(input.action==='upload')result=await workflow.upload(input.plan);
    else if(input.action==='classes')result=await workflow.classes(input.plan);
    else if(input.action==='class-students')result=await workflow.classStudents(input.plan);
    else if(input.action==='api-call')result=await workflow.call(input.plan);
    else if(input.action==='sync')result=await workflow.sync(input.plan);
    else if(input.action==='scope'){const stop=await control();if(stop)result=stop;else{const saved=await selectScope(input.plan);result={outcome:'scope_selected',roster:workflow.redact(saved),submitted:false};}}
    else if(input.action==='access')result=await access();
    else if(input.action==='relogin')result=await relogin();
    else if(input.action==='roster')result=await roster();
    else if(input.action==='snapshot'){
      const [b,a]=await Promise.all([api('GET',B),full()]);result=snapshot(b,a);
    }else if(input.action==='frames'){
      const stop=await control();if(stop)result=stop;
      else{const [b,a]=await Promise.all([api('GET',B),full()]);result=await apply(b,a,input.plan,input.confirm);}
    }else if(input.action==='associate'){
      const stop=await control();result=stop||await associate(input.plan);
    }
    else if(input.action==='run')result=await run();
    else if(input.action==='catalog'){
      const stop=await control();
      if(stop)result=stop;
      else{const [batch,a]=await Promise.all([api('GET',B),full()]);result=await confirmCatalog(batch,a,input.plan);}
    }
    else if(input.action==='evidence')result=await evidence(input.plan);
    else if(input.action==='responses')result=await responses(input.plan);
    else if(input.action==='retry-precut'){
      const stop=await control();
      if(stop)result=stop;
      else{
        const a=await full(),p=input.plan?.page;
        if(a.status!=='awaiting_frames'||a.frame_revision!==input.plan?.frame_revision)fail('version_conflict');
        const batch=await api('GET',B);
        if(!workflow.organizer(batch))fail('unsupported_workflow');
        if(!Number.isInteger(p)||p<0||p>=batch.pages_per_paper||
          ((a.frames||[]).length&&!(a.localization_failed_pages||[]).includes(p)))fail('invalid_retry_page');
        if((a.frames||[]).some(f=>f.source==='manual'&&f.regions.some(r=>r.page===p)))fail('manual_frames_present');
        await api('POST',B+'/analysis/frames/retry-precut',{frame_revision:a.frame_revision,page:p});
        result={outcome:'retry_started',page:p,submitted:false};
      }
    }else if(input.action==='diagnose'){
      const stop=await control();if(stop)result=stop;
      else{
      const [batch,a]=await Promise.all([api('GET',B),full()]);
      if(a.status==='awaiting_frames'){
        const problem=frameProblem(a,batch.pages_per_paper);
        result={outcome:problem?'needs_precut_recovery':'needs_frame_review',
          diagnosis:problem,review:snapshot(batch,a),submitted:false};
      }
      else if(a.status==='completed'){
        const check=await inspectOrCheck('diagnose');result={...check,review_tasks:reviewTasks(check,a,batch),submitted:false};
      }else result={outcome:a.status==='awaiting_confirmation'?'needs_catalog_review':'needs_targeted_recovery',
        analysis_status:a.status,progress:a.progress,review:snapshot(batch,a),submitted:false};
      }
    }else if(input.action==='usage'){
      const usage=await api('GET',B+'/model-usage'),s=usage.summary||{};
      result={usage_source:usage.usage_source||'unknown',historical_backfill:usage.historical_backfill===true,
        summary:s,phases:usage.phases||{},tokens_complete:Number.isFinite(s.total_tokens)&&s.total_tokens_missing_attempts===0,
        submitted:false};
    }
    else if(input.action==='check'){
      const stop=await control();result=stop||await inspectOrCheck(input.action);
    }else result=await inspectOrCheck(input.action);
    return {ok:true,result,transitions,calls,checkpoint:{origin:input.origin,batch_id:uploadReceipt?.batch_id||input.batch,upload_receipt:uploadReceipt,frame_receipt:receipt,association_receipt:associations,catalog_receipt:catalogReceipt,auth_receipt:authReceipt}};
  }catch(error){return {ok:false,error:{code:error.code||'transport_failed',...(error.details||{})},transitions,calls,
    checkpoint:{origin:input.origin,batch_id:uploadReceipt?.batch_id||input.batch,upload_receipt:uploadReceipt,frame_receipt:receipt,association_receipt:associations,catalog_receipt:catalogReceipt,auth_receipt:authReceipt}};}
}
