(ctx) => {
  const {input,api,fail,full,selectScope,inspectOrCheck,control,transitions}=ctx;
  const contracts=__CONTRACTS__;
  const B='/api/batches/'+input.batch;
  const id=v=>typeof v==='string'&&/^[A-Za-z0-9_-]{1,200}$/.test(v);
  const evidence=p=>{if(p?.evidence_confirmed!==true||typeof p.evidence_note!=='string'||!p.evidence_note.trim())fail('evidence_required');};
  const redact=v=>Array.isArray(v)?v.map(redact):v&&typeof v==='object'?Object.fromEntries(Object.entries(v)
    .filter(([k])=>!/(?:token|cookie|authorization|login_url|request_json|request_body)/i.test(k))
    .map(([k,x])=>[k,redact(x)])):v;
  const organizer=b=>b.workflow_mode==='scan'||b.workflow_mode==='grading'&&['xueersi','doubao'].includes(b.grading_engine);
  function scopeQuery(p){
    const q={source:p.source||'teaching'};
    if(!['teaching','general'].includes(q.source))fail('invalid_scope_source');
    for(const k of ['grade','subject_id','course_id'])if(p[k]!==undefined&&p[k]!==null&&p[k]!=='')q[k]=String(p[k]);
    return q;
  }
  function queryPath(path,values,allowed){
    if(!values||typeof values!=='object'||Array.isArray(values))fail('invalid_query');
    const q=new URLSearchParams();
    for(const[k,v]of Object.entries(values)){
      if(!allowed.includes(k)||!['string','number','boolean'].includes(typeof v))fail('invalid_query_field',{field:k});
      q.set(k,String(v));
    }
    return path+(q.size?'?'+q:'');
  }
  async function classes(plan={}){
    const source=plan.source||'teaching';
    const q=scopeQuery(plan);delete q.source;
    const d=await api('GET',source==='teaching'?'/api/classroom/classes':queryPath('/api/classroom/general-options',q,['grade','subject_id','course_id']));
    return {outcome:'class_directory',source,...redact(d),scope_query:q,
      ...(source==='teaching'&&!(d.classes||[]).length&&!(d.courses||[]).length?
        {next_action:'query_general_directory'}:{}),submitted:false};
  }
  async function classStudents(p){
    if(!/^\d{1,30}$/.test(p?.class_id||''))fail('invalid_class_id');
    const d=await api('GET',queryPath('/api/classroom/classes/'+p.class_id+'/students',scopeQuery(p),['source','grade','subject_id','course_id']));
    return {outcome:'class_students',...redact(d),submitted:false};
  }
  async function call(p){
    const op=contracts.operations.find(o=>o.name===p?.operation);
    if(!op)fail('unknown_operation');
    if(op.special)fail('dedicated_command_required',{operation:op.name,command:op.special==='sync'?'sync':op.special==='catalog'?'catalog':op.special});
    const params=p.params||{};let path=op.path.replace(/\{([^}]+)\}/g,(_,key)=>{
      const value=key==='bid'?input.batch:['page','index'].includes(key)&&Number.isInteger(params[key])?String(params[key]):params[key];
      if(!id(value))fail('invalid_route_parameter',{field:key});return encodeURIComponent(value);
    });
    const parameterNames=[...op.path.matchAll(/\{([^}]+)\}/g)].map(x=>x[1]).filter(k=>k!=='bid');
    if(Object.keys(params).some(k=>!parameterNames.includes(k)))fail('invalid_route_parameter');
    path=queryPath(path,p.query||{},op.query);
    if(op.transport==='artifact')return {outcome:'artifact_location',operation:op.name,url:input.origin+path,downloaded:false,submitted:false};
    let body=p.body;
    if(op.method==='GET'){
      if(body!==undefined)fail('unexpected_request_body');
      return {outcome:'api_result',operation:op.name,data:redact(await api('GET',path)),submitted:false};
    }
    evidence(p);
    const stop=await control({resume:p.resume_authorized===true&&['grading-start','analysis-start','prepare-analysis'].includes(op.name)});if(stop)return stop;
    let batch;
    if(op.modes||['grading-retry','scan-retry','student-save'].includes(op.name)){
      batch=await api('GET',B);
      const actual=organizer(batch)?batch.workflow_mode==='scan'?'scan':'quick':batch.workflow_mode;
      if(op.modes&&!op.modes.some(mode=>mode===batch.workflow_mode||mode===actual||mode==='organizer'&&organizer(batch)))fail('unsupported_workflow');
      if(params.sid&&!batch.students.some(s=>s.id===params.sid))fail('paper_not_found');
      if(op.name==='grading-retry'&&batch.students.find(s=>s.id===params.sid)?.status==='done'&&p.regrade_authorized!==true)fail('completed_paper_protected');
      if(op.name==='answers-extract'&&(batch.grading_engine!=='llm'||!batch.has_answer_paper))fail('answer_paper_required');
      if(op.name==='student-save'&&batch.workflow_mode==='scan'&&body?.identity_only!==true)fail('unsupported_workflow');
    }
    if(op.transport==='empty'){
      if(body!==undefined)fail('unexpected_request_body');
    }else{
      if(body!==undefined&&(!body||typeof body!=='object'||Array.isArray(body)))fail('invalid_request_body');
      body={...(body||{})};
      for(const key of op.required)if(!(key in body))fail('required_body_field',{field:key});
      if(['review_token','token','check_token','confirmed_check_token','preflight_token'].some(k=>k in body))fail('runtime_token_only');
      if(op.runtime_token==='review'){
        const a=await full();
        if(!a.read_version||p.expected?.read_version!==a.read_version||!a.review_token)fail('review_version_conflict');
        body.review_token=a.review_token;
      }else if(op.runtime_token==='task'){
        const tasks=await api('GET',B+'/task-control'),t=tasks[body.kind];
        if(!t?.token||p.expected?.started_at!==t.started_at)fail('task_version_conflict');body.token=t.token;
      }
    }
    if(op.name==='reference-answers-resume'&&body.resume_reference_answers!==true)fail('invalid_recovery_plan');
    if(op.name==='sync-config-save'&&body.selected_paper_ids!==null){
      const b=batch||await api('GET',B),ids=new Set(b.students.map(s=>s.id)),chosen=body.selected_paper_ids;
      if(!Array.isArray(chosen)||chosen.length!==ids.size||new Set(chosen).size!==ids.size||chosen.some(x=>!ids.has(x)))fail('full_batch_scope_required');
    }
    const saved=await api(op.method,path,body);
    // Return authoritative persistence, rather than equating a 200 with completion.
    let readback;
    if(op.method==='PUT'||op.method==='PATCH'){
      if(op.name==='scope-save'||op.name==='associate')readback=await api('GET',B+'/roster');
      else if(op.name==='sync-config-save')readback=await api('GET',B+'/lesson-practice/config');
      else if(op.name==='student-save')readback=await api('GET',B+'/students/'+params.sid);
      else if(['layout-save'].includes(op.name))readback=await api('GET',B);
      else readback=await full();
    }
    return {outcome:'api_saved',operation:op.name,data:redact(saved),...(readback?{readback:redact(readback)}:{}),submitted:false};
  }
  async function live(){
    try{return await api('GET',B+'/live-state');}
    catch(e){if(e.details?.status!==404)throw e;
      const [progress,tasks,a]=await Promise.all([api('GET',B+'/progress'),api('GET',B+'/task-control'),api('GET',B+'/analysis/status')]);
      return {progress,task_control:tasks,analysis_status:a};
    }
  }
  async function grade(batch){
    let state=await live(),t=state.task_control?.grading||{},progress=state.progress||{};
    if(t.status==='stopping')return {outcome:'waiting',waiting_for:'grading_stop',submitted:false};
    if(['stopped','paused'].includes(t.status)&&input.plan?.resume_authorized!==true)return {outcome:'stopped_readonly',submitted:false};
    const active=['extracting','grading','queued','processing'];
    const deadline=performance.now()+input.timeout*1000;let polled=false;
    while(['running','waiting'].includes(t.status)||active.includes(progress.status)){
      if(performance.now()>=deadline)return {outcome:'waiting',waiting_for:'grading',progress:redact(progress),submitted:false};
      await new Promise(resolve=>setTimeout(resolve,Math.min(input.interval*1000,Math.max(1,deadline-performance.now()))));
      state=await live();t=state.task_control?.grading||{};progress=state.progress||{};polled=true;
      if(t.status==='stopping')return {outcome:'waiting',waiting_for:'grading_stop',submitted:false};
      if(['stopped','paused'].includes(t.status)&&input.plan?.resume_authorized!==true)return {outcome:'stopped_readonly',submitted:false};
    }
    if(polled)Object.assign(batch,await api('GET',B));
    const unfinished=batch.students.filter(s=>s.status!=='done');
    if(!unfinished.length)return null;
    const retry=input.plan?.grading_retry;
    if(retry){
      evidence(retry);
      if(!Array.isArray(retry.paper_ids)||!retry.paper_ids.length||new Set(retry.paper_ids).size!==retry.paper_ids.length||retry.paper_ids.some(x=>!batch.students.some(s=>s.id===x)))fail('invalid_retry_scope');
      const remaining=retry.paper_ids.filter(x=>unfinished.some(s=>s.id===x));
      if(!remaining.length)return {outcome:'needs_grading_recovery',failed:unfinished.map(s=>({paper_id:s.id,index:s.index,status:s.status})),submitted:false};
      // The backend serializes grading jobs. Dispatch one remaining paper, then wait.
      const sid=remaining[0];await api('POST',B+'/students/'+sid+'/retry');
      transitions.push({action:'grading_retry_started',paper_id:sid});
      return {outcome:'waiting',waiting_for:'grading',submitted:false};
    }
    if(unfinished.some(s=>s.status==='failed'||s.error))return {outcome:'needs_grading_recovery',
      failed:unfinished.map(s=>({paper_id:s.id,index:s.index,status:s.status,error:String(s.error||'').slice(0,400)})),submitted:false};
    if(batch.grading_engine==='llm'&&!batch.has_answer_paper)fail('answer_paper_required');
    await api('POST',B+'/start');transitions.push({action:'grading_started'});
    return {outcome:'waiting',waiting_for:'grading',submitted:false};
  }
  function gradingSummary(batch){
    const papers=batch.students||[],counts={},missingResults=[],pending=[];
    let observations=0,resultPapers=0;
    for(const paper of papers){
      if(paper.status!=='done')pending.push(paper.id);
      const rows=paper.judgments?.length?paper.judgments:paper.results;
      const available=Array.isArray(rows)&&rows.length>0;
      if(available){
        resultPapers++;
        for(const row of rows){
          const verdict=typeof row.verdict==='string'&&row.verdict?row.verdict:'unknown';
          counts[verdict]=(counts[verdict]||0)+1;observations++;
        }
      }else if(Array.isArray(paper.provider_results)&&paper.provider_results.length)resultPapers++;
      else missingResults.push(paper.id);
    }
    const ids=new Set(papers.map(p=>p.id));
    const complete=papers.length>0&&ids.size===papers.length&&pending.length===0&&missingResults.length===0;
    return {outcome:complete?'grading_completed':'grading_incomplete',workflow_mode:batch.workflow_mode,
      grading_engine:batch.grading_engine,papers:papers.length,graded_papers:papers.filter(p=>p.status==='done').length,
      result_papers:resultPapers,missing_result_papers:missingResults,pending_papers:pending,
      duplicate_papers:papers.length-ids.size,observations,verdicts:counts,grading_complete:complete,
      stopped_at:'grading',stop_after:'grading',organization_started:false,submitted:false,
      full_accuracy_verified:false,link:input.origin+'/exams/'+input.batch};
  }
  async function upload(p){
    if(!p||typeof p.key!=='string'||!/^[A-Za-z0-9_-]{8,100}$/.test(p.key)||!/^[a-f0-9]{64}$/.test(p.sha256))fail('invalid_upload_plan');
    if(p.scope)evidence(p.scope);
    let previous=ctx.getUpload();
    const signature=JSON.stringify([p.key,p.sha256,p.fields,p.scope||null]);
    if(previous&&previous.signature!==signature)fail('upload_plan_changed');
    const state=await api('GET','/api/uploads/'+encodeURIComponent(p.key));
    let batch;
    if(state.status==='deleted')fail('uploaded_batch_deleted');
    if(state.status==='completed'){
      if(!id(state.batch_id))fail('invalid_upload_status');
      batch=await api('GET','/api/batches/'+state.batch_id);
    }else if(state.status!=='not_found')fail('invalid_upload_status');
    else{
      if(previous?.state==='dispatching'&&input.upload_first_dispatch!==true)
        return {outcome:'upload_uncertain',next_action:'read_upload_status',submitted:false};
      const file=document.querySelector(p.file_input_selector||'#paperflow-upload')?.files?.[0];
      if(!file){ctx.setUpload({key:p.key,signature,sha256:p.sha256,state:'prepared'});
        return {outcome:'needs_file_binding',next_action:'bind_pdf_with_native_file_tool',submitted:false};}
      if(file.size!==p.size||file.size>100*1024*1024)fail('upload_file_mismatch');
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))).map(v=>v.toString(16).padStart(2,'0')).join('');
      if(digest!==p.sha256)fail('upload_file_mismatch');
      const form=new FormData();form.append('file',file);
      for(const[k,v]of Object.entries(p.fields))form.append(k,String(v));
      ctx.setUpload({key:p.key,signature,sha256:p.sha256,state:'dispatching'});
      // api() handles multipart without setting Content-Type; the browser supplies its boundary.
      batch=await api('POST','/api/batches',form,{'Idempotency-Key':p.key});
    }
    if(!id(batch.id)||!Array.isArray(batch.students))fail('invalid_upload_response');
    ctx.setUpload({key:p.key,signature,sha256:p.sha256,state:'uploaded',batch_id:batch.id});
    if(p.scope){
      evidence(p.scope);
      const path='/api/batches/'+batch.id+'/roster',current=await api('GET',path);
      const wanted=p.scope;
      const same=current.semester_id===wanted.semester_id&&JSON.stringify((current.classes||[]).map(x=>x.id).sort())===JSON.stringify([...(wanted.class_ids||[])].sort())&&
        Object.entries(wanted.scope||{}).every(([k,v])=>current.scope?.[k]===v);
      if(!same)await api('PUT',path,{revision:current.revision,semester_id:wanted.semester_id,class_ids:wanted.class_ids,scope:wanted.scope});
      const saved=await api('GET',path);
      if(saved.semester_id!==wanted.semester_id||JSON.stringify((saved.classes||[]).map(x=>x.id).sort())!==JSON.stringify([...wanted.class_ids].sort()))fail('scope_not_persisted');
    }
    return {outcome:'uploaded',batch_id:batch.id,link:input.origin+'/exams/'+batch.id+(batch.workflow_mode==='scan'?'/analysis':''),
      workflow_mode:batch.workflow_mode,grading_engine:batch.grading_engine,total_pages:batch.total_pages,pages_per_paper:batch.pages_per_paper,
      papers:batch.students.length,submitted:false};
  }
  async function sync(p){
    if(input.authorize_sync!==true)fail('sync_authorization_required');evidence(p);
    if(p.reference_reviewed!==true||p.scope_reviewed!==true||p.catalog_reviewed!==true)fail('review_required');
    const attempts=await api('GET',B+'/lesson-practice/imports?check_source=false');
    if(attempts.items?.length){
      const a=attempts.items[0];
      if(a.state==='SUCCEEDED')return {outcome:'already_synchronized',attempt:redact(a),submitted:false};
      if(p.resume_attempt_id){
        if(p.resume_attempt_id!==a.id||!id(a.id))fail('import_attempt_mismatch');
        const d=await api('POST',B+'/lesson-practice/imports/'+a.id+'/resume');
        return {outcome:'synchronization_resumed',attempt:redact(d),submitted:true};
      }
      return {outcome:'existing_import_readonly',attempt:redact(a),submitted:false};
    }
    const checked=await inspectOrCheck('check');
    if(!checked.ready)return {...checked,submitted:false};
    const cfg=await api('GET',B+'/lesson-practice/config');
    if(cfg.config.revision!==p.revision||checked.check?.source_version!==p.source_version)fail('check_version_conflict');
    const fresh=await api('POST',B+'/lesson-practice/preflight',{revision:cfg.config.revision,allow_pending_formula_protocol:false});
    const warnings=(fresh.issues||[]).filter(i=>i.severity==='warning').map(i=>i.id).sort();
    if(!fresh.ready||fresh.source_version!==p.source_version||!fresh.check_token||
      !Array.isArray(p.accepted_warning_ids)||JSON.stringify([...new Set(p.accepted_warning_ids)].sort())!==JSON.stringify(warnings))fail('check_confirmation_required');
    const a=await api('POST',B+'/lesson-practice/imports',{revision:cfg.config.revision,
      check_token:fresh.check_token,confirmed_check_token:fresh.check_token,
      accepted_warning_ids:p.accepted_warning_ids,allow_pending_formula_protocol:false});
    return {outcome:a.state==='SUCCEEDED'?'synchronized':'synchronization_accepted',attempt:redact(a),submitted:true};
  }
  return {classes,classStudents,call,grade,gradingSummary,live,sync,upload,organizer,redact};
}
