import assert from 'node:assert/strict';
import {test} from 'node:test';
import http from 'node:http';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {Cdp,main,originOf,selectCookies} from '../scripts/paperflow_session.mjs';

test('cookie selection limits domain, path, lifetime and names while retaining HttpOnly',()=>{
  const cookies=[
    {name:'SESSION',value:'needed',domain:'.yungu.org',path:'/',httpOnly:true,expires:-1},
    {name:'paper_session',value:'app',domain:'piyue.yungu.org',path:'/',httpOnly:true},
    {name:'SESSION',value:'unrelated',domain:'other.yungu.org',path:'/'},
    {name:'SESSION',value:'wrong-path',domain:'.yungu.org',path:'/private'},
    {name:'SESSION',value:'expired',domain:'.yungu.org',path:'/',expires:1},
    {name:'password',value:'unrelated',domain:'.yungu.org',path:'/'},
  ];
  const filtered=selectCookies(cookies,'https://piyue.yungu.org');
  assert.deepEqual(filtered.map(c=>c.value),['needed','app']);
  assert.ok(filtered.every(c=>c.httpOnly));
  assert.throws(()=>selectCookies([...cookies,{name:'paper_logged_out',value:'1',domain:'.yungu.org',path:'/'}],
    'https://piyue.yungu.org'),/source_login_required/);
});

test('unsupported origins and insecure remote endpoints stop before credentials are read',async()=>{
  assert.throws(()=>originOf('https://example.com'),/unsupported_session_origin/);
  assert.throws(()=>originOf('http://piyue.yungu.org'),/unsupported_session_origin/);
  assert.throws(()=>originOf('https://piyue.yungu.org/path'),/unsupported_session_origin/);
  const result=await main({action:'connect',session:'test',origin:'https://example.com'});
  assert.equal(result.error.code,'unsupported_session_origin');
  await assert.rejects(()=>Cdp.connect('http://192.0.2.1:9222'),/invalid_browser_endpoint/);
});

test('status and close with no owned session do not discover or launch browsers',async()=>{
  const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'paperflow-empty-'));
  try {
    const input={origin:'http://127.0.0.1:1',session:'empty',cache_dir:tmp};
    assert.equal((await main({...input,action:'status'})).result.connected,false);
    assert.equal((await main({...input,action:'close'})).result.outcome,'isolated_session_closed');
  }finally{await fs.rm(tmp,{recursive:true,force:true});}
});

const endpointsFile=process.env.PAPERFLOW_SESSION_TEST_ENDPOINTS;
test('two real Chromium browsers use isolated auth and leave the source page untouched',
  {skip:!endpointsFile,timeout:90000},async t=>{
  const endpoints=JSON.parse(await fs.readFile(endpointsFile,'utf8'));
  const sourceUrl='http://127.0.0.1:'+endpoints.source,targetUrl='http://127.0.0.1:'+endpoints.target;
  const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'paperflow-isolated-e2e-'));
  const user={id:'teacher-fixture',school_id:'school-fixture',identity:'employee'};
  const sourceApp='source-application-session',upstream='source-upstream-session';
  const active=new Set([sourceApp]);let created=0,revoked=0,validClassroom=true,changed=false,uploaded=null;
  const seen=[];
  const server=http.createServer(async(req,res)=>{
    const cookies=Object.fromEntries((req.headers.cookie||'').split(';').map(x=>x.trim().split('=')));
    const route=req.url.split('?')[0];seen.push({route,method:req.method});
    const send=(code,body)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
    if(route==='/api/healthz')return send(200,{status:'ok'});
    if(route==='/api/login-identity')return send(200,cookies.SESSION===upstream?
      {can_login:true,user:changed?{...user,id:'different-teacher'}:user}:{can_login:false,user:null});
    if(route==='/api/session') {
      if(!active.has(cookies.paper_session)) {
        if(cookies.SESSION!==upstream)return send(401,{});
        const token='isolated-application-'+(++created);active.add(token);
        res.setHeader('Set-Cookie','paper_session='+token+'; Path=/; HttpOnly; SameSite=Lax');
      }
      return send(200,{ok:true,user:changed?{...user,id:'different-teacher'}:user});
    }
    if(route==='/api/classroom/login-check')return send(200,
      validClassroom&&cookies.SESSION===upstream&&active.has(cookies.paper_session)?
        {'批阅台登录':'有效','云谷会话':'有效且账号一致','课堂会话':'有效'}:
        {'批阅台登录':'有效','状态码':428,'错误类型':'classroom_login_required','课堂会话':'未验证'});
    if(route==='/api/logout') {
      if(cookies.paper_session===sourceApp)throw Error('source session must never be revoked');
      active.delete(cookies.paper_session);revoked++;
      return send(200,{logout_url:'https://login.yungu.org/do-not-follow'});
    }
    if(route==='/api/fixture/upload') {
      const chunks=[];for await(const chunk of req)chunks.push(chunk);
      uploaded=Buffer.concat(chunks);return send(200,{ok:true,bytes:uploaded.length});
    }
    res.writeHead(200,{'Content-Type':'text/html'});
    res.end('<html><body><input id="teacher-draft" value="unsaved work"></body></html>');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  let source,sourceContext,sourceTarget,sourceSession;
  const request={origin,session:'real-test',cache_dir:tmp,source_url:sourceUrl,target_url:targetUrl};
  try {
    source=await Cdp.connect(sourceUrl);
    sourceContext=(await source.send('Target.createBrowserContext',{disposeOnDetach:false})).browserContextId;
    sourceTarget=(await source.send('Target.createTarget',{url:origin+'/teacher-working',browserContextId:sourceContext,background:true})).targetId;
    sourceSession=(await source.send('Target.attachToTarget',{targetId:sourceTarget,flatten:true})).sessionId;
    await source.send('Network.setCookies',{cookies:[
      {name:'SESSION',value:upstream,url:origin+'/',path:'/',httpOnly:true,sameSite:'Lax'},
      {name:'paper_session',value:sourceApp,url:origin+'/',path:'/',httpOnly:true,sameSite:'Lax'},
      {name:'unrelated_secret',value:'never-copy-this',url:origin+'/',path:'/',httpOnly:true},
    ]},sourceSession);
    request.source_target=sourceTarget;
    for(let i=0;i<30;i++) {
      const state=await source.send('Runtime.evaluate',{expression:'document.readyState',returnByValue:true},sourceSession);
      if(state.result.value==='complete')break;await new Promise(r=>setTimeout(r,50));
    }
    await source.send('Runtime.evaluate',{expression:'document.querySelector("#teacher-draft").value="unsaved teacher edits"'},sourceSession);
    await t.test('connect creates a fresh app session and verifies both login boundaries',async()=>{
      const result=await main({...request,action:'connect'});
      assert.equal(result.ok,true,JSON.stringify(result));
      assert.equal(result.result.outcome,'isolated_session_connected');
      assert.equal(result.result.classroom_verified,true);
      assert.ok(created>=1);
      assert.ok(active.has(sourceApp));
      const text=JSON.stringify(result);
      assert.ok(!text.includes(sourceApp)&&!text.includes(upstream)&&!text.includes('never-copy-this'));
    });
    await t.test('repeat connect reuses the same session without new authentication',async()=>{
      const before=created,result=await main({...request,action:'connect'});
      assert.equal(result.result.outcome,'isolated_session_reused');assert.equal(created,before);
    });
    await t.test('business execution reads HttpOnly auth inside a distinct target context',async()=>{
      const result=await main({...request,action:'execute',expression:
        '(async()=>({origin:location.origin,visible:document.cookie,ok:(await fetch("/api/session?refresh_profile=false&include_models=false")).ok}))()'});
      assert.equal(result.origin,origin);assert.equal(result.ok,true);assert.equal(result.visible,'');
      const files=await fs.readdir(path.join(tmp,'scan-marked-papers-sessions'));
      assert.equal(files.filter(f=>f.endsWith('.json')).length,1);
      const content=await fs.readFile(path.join(tmp,'scan-marked-papers-sessions',files.find(f=>f.endsWith('.json'))),'utf8');
      assert.ok(!content.includes(upstream)&&!content.includes(sourceApp)&&!content.includes('never-copy-this'));
      const state=JSON.parse(content),target=await Cdp.connect(targetUrl);
      try {
        const {sessionId}=await target.send('Target.attachToTarget',{targetId:state.target,flatten:true});
        const cookies=(await target.send('Network.getCookies',{urls:[origin+'/']},sessionId)).cookies;
        assert.deepEqual(cookies.map(c=>c.name).sort(),['SESSION','paper_session']);
        assert.equal(cookies.find(c=>c.name==='SESSION').domain,new URL(origin).hostname);
        assert.notEqual(cookies.find(c=>c.name==='paper_session').value,sourceApp);
      }finally{target.close();}
      if(process.platform!=='win32')assert.equal((await fs.stat(path.join(tmp,'scan-marked-papers-sessions',files.find(f=>f.endsWith('.json'))))).mode&0o777,0o600);
    });
    await t.test('native file transfer works for an existing remote target browser',async()=>{
      const file=path.join(tmp,'paper.pdf');await fs.writeFile(file,'%PDF-1.4\nfixture paper\n');
      const result=await main({...request,action:'execute',file,expression:
        '(async()=>{const form=new FormData();form.append("file",document.querySelector("#paperflow-upload").files[0]);return (await fetch("/api/fixture/upload",{method:"POST",body:form})).json()})()'});
      assert.equal(result.ok,true,JSON.stringify(result));assert.ok(uploaded.includes(Buffer.from('%PDF-1.4')));
      const removed=await main({...request,action:'execute',expression:'({ok:!document.getElementById("paperflow-upload")})'});
      assert.equal(removed.ok,true);
    });
    await t.test('normal Python CLI automatically uses the connected isolated session',async()=>{
      const script=path.join(path.dirname(fileURLToPath(import.meta.url)),'../scripts/paperflow.py');
      const output=await new Promise((resolve,reject)=>{
        const child=spawn(process.env.PAPERFLOW_TEST_PYTHON||'python3',[script,'--base-url',origin,'--browser-session','real-test','access'],
          {env:{...process.env,XDG_CACHE_HOME:tmp,PAPERFLOW_AUTO_UPDATE:'0'}});
        let stdout='',stderr='';child.stdout.on('data',c=>stdout+=c);child.stderr.on('data',c=>stderr+=c);
        child.on('error',reject);child.on('close',code=>resolve({code,stdout,stderr}));
      });
      assert.equal(output.code,0,output.stdout+output.stderr);
      assert.equal(JSON.parse(output.stdout).result.outcome,'access_verified');
      assert.ok(!output.stdout.includes(upstream)&&!output.stdout.includes(sourceApp));
    });
    await t.test('identity change stops a planned write before it reaches the server',async()=>{
      changed=true;const before=seen.length;
      const result=await main({...request,action:'execute',expression:'fetch("/api/fixture/forbidden-write",{method:"POST"})'});
      assert.equal(result.error.code,'isolated_identity_changed');
      assert.ok(!seen.slice(before).some(r=>r.method==='POST'));changed=false;
    });
    await t.test('business 428 in an HTTP 200 is reported as an expired session',async()=>{
      validClassroom=false;
      const result=await main({...request,action:'status'});
      assert.equal(result.result.outcome,'isolated_session_expired');assert.equal(result.result.connected,false);
      validClassroom=true;
    });
    await t.test('source URL, unsaved edits and all source cookies remain unchanged',async()=>{
      const r=await source.send('Runtime.evaluate',{expression:'({url:location.href,draft:document.querySelector("#teacher-draft").value})',returnByValue:true},sourceSession);
      assert.deepEqual(r.result.value,{url:origin+'/teacher-working',draft:'unsaved teacher edits'});
      const cookies=(await source.send('Network.getCookies',{urls:[origin+'/']},sourceSession)).cookies;
      assert.equal(cookies.find(c=>c.name==='paper_session').value,sourceApp);
      assert.equal(cookies.find(c=>c.name==='unrelated_secret').value,'never-copy-this');
    });
    await t.test('close revokes only the task app session and preserves both existing browsers',async()=>{
      const r=await main({...request,action:'close'});
      assert.equal(r.ok,true);assert.ok(revoked>=1);assert.ok(active.has(sourceApp));
      assert.equal((await main({...request,action:'status'})).result.connected,false);
      const target=await Cdp.connect(targetUrl);assert.ok((await target.send('Target.getTargets')).targetInfos.length>0);target.close();
      assert.ok((await source.send('Target.getTargets')).targetInfos.some(t=>t.targetId===sourceTarget));
    });
    await t.test('same browser as source and target is rejected without closing user pages',async()=>{
      const r=await main({...request,session:'same-browser',target_url:sourceUrl,action:'connect'});
      assert.equal(r.error.code,'target_browser_must_be_independent');
      assert.ok((await source.send('Target.getTargets')).targetInfos.some(t=>t.targetId===sourceTarget));
    });
    await t.test('a closed target can reconnect and revalidate the original teacher',async()=>{
      assert.equal((await main({...request,action:'connect'})).ok,true);
      const directory=path.join(tmp,'scan-marked-papers-sessions');
      const files=await fs.readdir(directory),file=files.find(f=>f.endsWith('.json'));
      const state=JSON.parse(await fs.readFile(path.join(directory,file),'utf8'));
      const target=await Cdp.connect(targetUrl);
      await target.send('Target.disposeBrowserContext',{browserContextId:state.context});target.close();
      changed=true;
      const refused=await main({...request,action:'connect'});
      assert.equal(refused.error.code,'source_identity_changed');
      assert.deepEqual(JSON.parse(await fs.readFile(path.join(directory,file),'utf8')),state);
      changed=false;
      const reconnected=await main({...request,action:'connect'});
      assert.equal(reconnected.result.outcome,'isolated_session_connected');
      assert.equal((await main({...request,action:'status'})).result.connected,true);
      assert.ok(active.has(sourceApp));
      await main({...request,action:'close'});
    });
    await t.test('an existing session lock stops parallel handoff without network requests',async()=>{
      const directory=path.join(tmp,'scan-marked-papers-sessions');
      assert.equal((await main({...request,action:'connect'})).ok,true);
      const files=await fs.readdir(directory),file=files.find(f=>f.endsWith('.json'));
      await fs.writeFile(path.join(directory,file+'.lock'),'locked');const before=seen.length;
      try {
        const result=await main({...request,action:'connect'});
        assert.equal(result.error.code,'isolated_session_in_progress');assert.equal(seen.length,before);
      }finally{await fs.unlink(path.join(directory,file+'.lock'));}
      await main({...request,action:'close'});
    });
    await t.test('default launch owns a separate Chromium and removes its disposable profile',
      {skip:!process.env.PAPERFLOW_SESSION_TEST_BROWSER},async()=>{
      const owned={...request,session:'owned-test',target_url:undefined,executable:process.env.PAPERFLOW_SESSION_TEST_BROWSER};
      try {
        const result=await main({...owned,action:'connect'});assert.equal(result.ok,true,JSON.stringify(result));
        assert.equal((await main({...owned,action:'status'})).result.connected,true);
        const directories=(await fs.readdir(path.join(tmp,'scan-marked-papers-sessions'))).filter(f=>f.startsWith('browser-'));
        assert.equal(directories.length,1);
      }finally{assert.equal((await main({...owned,action:'close'})).ok,true);}
      assert.deepEqual((await fs.readdir(path.join(tmp,'scan-marked-papers-sessions'))).filter(f=>f.startsWith('browser-')),[]);
      assert.ok((await source.send('Target.getTargets')).targetInfos.some(t=>t.targetId===sourceTarget));
    });
  }finally {
    await main({...request,action:'close'});
    if(sourceContext)await source?.send('Target.disposeBrowserContext',{browserContextId:sourceContext}).catch(()=>{});
    source?.close();await new Promise(resolve=>server.close(resolve));
    await fs.rm(tmp,{recursive:true,force:true});
  }
});
