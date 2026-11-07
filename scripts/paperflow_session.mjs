#!/usr/bin/env node
// Credentials stay inside this process and an isolated browser context.
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';

export class SessionError extends Error {
  constructor(code) { super(code); this.code=code; }
}
const fail=code=>{throw new SessionError(code);};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));

export function originOf(value) {
  let u;try {u=new URL(value);}catch {fail('invalid_session_origin');}
  const local=['localhost','127.0.0.1','[::1]'].includes(u.hostname);
  if(u.username||u.password||u.search||u.hash||u.pathname!=='/'||
     !(u.protocol==='https:'||(local&&u.protocol==='http:'))||
     !(local||u.hostname==='piyue.yungu.org'||u.hostname.endsWith('.app.yungu.org')))
    fail('unsupported_session_origin');
  return u.origin;
}

function endpoint(value) {
  let u;try {u=new URL(value);}catch {fail('invalid_browser_endpoint');}
  const local=['localhost','127.0.0.1','[::1]'].includes(u.hostname);
  if(u.username||u.password||u.search||u.hash||
     !['http:','https:','ws:','wss:'].includes(u.protocol)||
     (!local&&!['https:','wss:'].includes(u.protocol))) fail('invalid_browser_endpoint');
  return u;
}

async function jsonGet(url,ms=1500) {
  const r=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(ms)});
  if(!r.ok)fail('browser_endpoint_unavailable');
  return r.json();
}

export class Cdp {
  constructor(ws) {
    this.ws=ws;this.next=0;this.pending=new Map();
    ws.addEventListener('message',event=>{
      let message;try {message=JSON.parse(event.data);}catch{return;}
      const p=this.pending.get(message.id);if(!p)return;
      clearTimeout(p.timer);this.pending.delete(message.id);
      message.error?p.reject(new SessionError('browser_protocol_error')):p.resolve(message.result||{});
    });
    ws.addEventListener('close',()=>this.rejectAll());
    ws.addEventListener('error',()=>this.rejectAll());
  }
  rejectAll() {
    for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(new SessionError('browser_disconnected'));}
    this.pending.clear();
  }
  static async connect(value) {
    if(typeof WebSocket!=='function')fail('node_websocket_unavailable');
    let u=endpoint(value);
    if(['http:','https:'].includes(u.protocol)) {
      const info=await jsonGet(new URL('/json/version',u));
      const remote=endpoint(info.webSocketDebuggerUrl);
      if(remote.hostname!==u.hostname||remote.port!==u.port||
         (u.protocol==='https:'&&remote.protocol!=='wss:'))fail('unexpected_browser_endpoint');
      u=remote;
    }
    const ws=new WebSocket(u);
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{ws.close();reject(new SessionError('browser_connection_timeout'));},3000);
      ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
      ws.addEventListener('error',()=>{clearTimeout(timer);reject(new SessionError('browser_endpoint_unavailable'));},{once:true});
    });
    return new Cdp(ws);
  }
  send(method,params={},sessionId,ms=12000) {
    const id=++this.next;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new SessionError('browser_command_timeout'));},ms);
      this.pending.set(id,{resolve,reject,timer});
      this.ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
    });
  }
  close(){this.ws.close();this.rejectAll();}
}

function identity(data) {
  const u=data?.user;
  if(!u||!['employee','teacher'].includes(u.identity)||u.id==null||u.school_id==null)
    fail('teacher_login_required');
  return {id:String(u.id),school_id:String(u.school_id),identity:u.identity};
}
export function sameIdentity(a,b) {
  return a&&b&&a.id===b.id&&a.school_id===b.school_id&&a.identity===b.identity;
}

export function selectCookies(cookies,origin) {
  const host=new URL(origin).hostname,now=Date.now()/1000;
  const result=cookies.filter(c=>{
    const domain=String(c.domain||'').toLowerCase();
    const matches=domain.startsWith('.')?(host===domain.slice(1)||host.endsWith(domain)):host===domain;
    const scope=c.path||'/';
    return matches&&['paper_session','SESSION','paper_logged_out'].includes(c.name)&&
      ('/api/session'===scope||'/api/session'.startsWith(scope.endsWith('/')?scope:scope+'/'))&&
      (!c.expires||c.expires===-1||c.expires>now)&&!c.partitionKey;
  });
  if(result.length>8||result.some(c=>typeof c.value!=='string'||c.value.length>4096||/[\x00-\x20\x7f;,]/.test(c.value)))
    fail('invalid_source_session');
  if(result.some(c=>c.name==='paper_logged_out'))fail('source_login_required');
  return result;
}

async function probe(origin,route,cookies) {
  const response=await fetch(origin+route,{headers:{Cookie:cookies.map(c=>c.name+'='+c.value).join('; '),Accept:'application/json'},
    redirect:'manual',signal:AbortSignal.timeout(10000)});
  if(response.status===401||response.status===403||response.status===428)return null;
  if(response.status!==200)fail('source_authentication_unavailable');
  try{return await response.json();}catch{fail('source_authentication_unavailable');}
}

async function sourceSession(cdp,input) {
  const {targetInfos}=await cdp.send('Target.getTargets');
  let pages=targetInfos.filter(t=>t.type==='page');
  if(input.source_target)pages=pages.filter(t=>t.targetId===input.source_target);
  else {
    const matching=pages.filter(t=>{try{return new URL(t.url).origin===input.origin;}catch{return false;}});
    if(matching.length)pages=matching;
    else pages=pages.filter(t=>!t.browserContextId);
    if(new Set(pages.map(t=>t.browserContextId||'default')).size>1)fail('source_context_selection_required');
  }
  if(!pages.length)fail('source_browser_page_unavailable');
  const {sessionId}=await cdp.send('Target.attachToTarget',{targetId:pages[0].targetId,flatten:true});
  try {
    const raw=await cdp.send('Network.getCookies',{urls:[input.origin+'/api/session']},sessionId);
    const cookies=selectCookies(raw.cookies||[],input.origin);
    const upstream=cookies.filter(c=>c.name==='SESSION');
    if(!upstream.length)fail('classroom_session_missing');
    if(upstream.length>4)fail('source_context_selection_required');
    const login=await probe(input.origin,'/api/login-identity',upstream);
    if(!login?.can_login||login.refresh_required)fail('source_login_required');
    const expected=identity(login);
    const app=cookies.filter(c=>c.name==='paper_session');
    if(app.length) {
      const local=await probe(input.origin,'/api/session?refresh_profile=false&include_models=false',app);
      if(local&&!sameIdentity(identity(local),expected))fail('source_identity_mismatch');
    }
    const verified=[];
    for(const cookie of upstream) {
      const actual=await probe(input.origin,'/api/login-identity',[cookie]);
      if(actual?.can_login&&sameIdentity(identity(actual),expected))verified.push(cookie);
    }
    if(verified.length)return {user:expected,cookies:verified,source_targets:targetInfos.map(t=>t.targetId)};
    fail('classroom_session_missing');
  } finally {await cdp.send('Target.detachFromTarget',{sessionId}).catch(()=>{});}
}

async function runtime(cdp,sessionId,expression,ms=20000) {
  const r=await cdp.send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,timeout:ms},sessionId,ms+1000);
  if(r.exceptionDetails||r.result?.subtype==='error')fail('isolated_script_failed');
  return r.result?.value;
}

async function browserIdentity(cdp,sessionId,origin,{classroom=false}={}) {
  return runtime(cdp,sessionId,'(async()=>{'+
    'if(location.origin!=='+JSON.stringify(origin)+')return {ok:false,error:{code:"isolated_origin_changed"}};'+
    'const r=await fetch("/api/session?refresh_profile=false&include_models=false",{credentials:"same-origin",redirect:"error"});'+
    'if(!r.ok)return {ok:false,error:{code:"isolated_session_expired"}};'+
    'const d=await r.json();const u=d.user;'+
    'const result={ok:true,user:u?{id:String(u.id),school_id:String(u.school_id),identity:u.identity}:null};'+
    (classroom?'const c=await fetch("/api/classroom/login-check",{credentials:"same-origin",redirect:"error"});result.classroom=c.ok?await c.json():null;':'')+
    'return result;})()');
}

function classroomReady(data) {
  return data&&data['批阅台登录']==='有效'&&data['云谷会话']==='有效且账号一致'&&data['课堂会话']==='有效'&&!data['状态码'];
}

async function cacheDirectory(input) {
  const base=input.cache_dir||process.env.XDG_CACHE_HOME||process.env.LOCALAPPDATA||path.join(os.homedir(),'.cache');
  const dir=path.join(base,'scan-marked-papers-sessions');
  await fs.mkdir(dir,{recursive:true,mode:0o700});
  if((await fs.lstat(dir)).isSymbolicLink())fail('unsafe_session_cache');
  await fs.chmod(dir,0o700);return dir;
}
async function stateFile(input) {
  if(!/^[A-Za-z0-9_-]{1,80}$/.test(input.session||''))fail('invalid_browser_session');
  const hash=createHash('sha256').update(input.origin+'\0'+input.session).digest('hex').slice(0,24);
  return path.join(await cacheDirectory(input),hash+'.json');
}
async function readState(file) {
  try {
    if((await fs.lstat(file)).isSymbolicLink())fail('unsafe_session_cache');
    return JSON.parse(await fs.readFile(file,'utf8'));
  }catch(error){if(error.code==='ENOENT')return null;throw error;}
}
function validateState(state,input) {
  if(!state)return null;
  const expectedProfile=path.join(path.dirname(input.state_file),'browser-');
  const connecting=state.phase==='connecting';
  if(state.schema!==1||state.origin!==input.origin||state.session!==input.session||
     !state.user||!['employee','teacher'].includes(state.user.identity)||
     typeof state.user.id!=='string'||typeof state.user.school_id!=='string'||
     (!connecting&&(typeof state.context!=='string'||typeof state.target!=='string'))||!state.browser||
     typeof state.browser.owned!=='boolean')fail('invalid_isolated_session_state');
  endpoint(state.browser.endpoint);
  if(state.browser.owned&&(!state.browser.profile||
      !path.resolve(state.browser.profile).startsWith(expectedProfile)||
      path.dirname(path.resolve(state.browser.profile))!==path.dirname(input.state_file)))
    fail('invalid_isolated_session_state');
  return state;
}
async function loadState(input) {
  const file=await stateFile(input);
  return validateState(await readState(file),{...input,state_file:file});
}
async function writeState(file,state) {
  const tmp=file+'.'+process.pid+'.tmp';
  try {await fs.writeFile(tmp,JSON.stringify(state),{mode:0o600,flag:'wx'});await fs.rename(tmp,file);}
  finally {await fs.unlink(tmp).catch(()=>{});}
}

async function discoverSources(input) {
  if(input.source_url)return [endpoint(input.source_url).href];
  if(process.env.PAPERFLOW_SOURCE_CDP_URL)return [endpoint(process.env.PAPERFLOW_SOURCE_CDP_URL).href];
  const home=os.homedir();
  const roots=process.platform==='darwin'?[
    'Library/Application Support/Google/Chrome','Library/Application Support/Microsoft Edge',
    'Library/Application Support/Chromium']:
    process.platform==='win32'?[
      path.join(process.env.LOCALAPPDATA||home,'Google/Chrome/User Data'),
      path.join(process.env.LOCALAPPDATA||home,'Microsoft/Edge/User Data')]:[
      '.config/google-chrome','.config/microsoft-edge','.config/chromium'];
  const found=[];
  for(const root of roots) {
    try {
      const port=Number((await fs.readFile(path.join(path.isAbsolute(root)?root:path.join(home,root),'DevToolsActivePort'),'utf8')).split('\n')[0]);
      if(Number.isInteger(port)&&port>0&&port<65536)found.push('http://127.0.0.1:'+port);
    }catch{}
  }
  found.push('http://127.0.0.1:9222','http://127.0.0.1:9223');
  const live=await Promise.all([...new Set(found)].map(async url=>{
    try {await jsonGet(new URL('/json/version',url),350);return url;}catch{return null;}
  }));
  return live.filter(Boolean);
}

async function executable(input) {
  const names=process.platform==='darwin'?[
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']:
    process.platform==='win32'?[
      path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google/Chrome/Application/chrome.exe'),
      path.join(process.env['PROGRAMFILES(X86)']||'C:\\Program Files (x86)','Microsoft/Edge/Application/msedge.exe')]:[
      '/usr/bin/chromium','/usr/bin/chromium-browser','/usr/bin/google-chrome','/opt/google/chrome/chrome'];
  const cache=process.env.PLAYWRIGHT_BROWSERS_PATH||
    (process.platform==='darwin'?path.join(os.homedir(),'Library/Caches/ms-playwright'):
      path.join(process.env.LOCALAPPDATA||path.join(os.homedir(),'.cache'),'ms-playwright'));
  for(const directory of [...new Set([cache,...(process.platform==='linux'?['/ms-playwright']:[])])])try {
    for(const name of (await fs.readdir(directory)).sort().reverse()) {
      if(name.startsWith('chromium-')) {
        const layouts=process.platform==='win32'?['chrome-win/chrome.exe','chrome-win64/chrome.exe']:
          process.platform==='darwin'?['chrome-mac/Chromium.app/Contents/MacOS/Chromium','chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium']:
          ['chrome-linux/chrome','chrome-linux64/chrome'];
        for(const layout of layouts)names.push(path.join(directory,name,layout));
      }
    }
  }catch{}
  if(input.executable)names.unshift(input.executable);
  for(const name of names)try {if((await fs.stat(name)).isFile())return name;}catch{}
  fail('isolated_browser_executable_unavailable');
}

async function startBrowser(input) {
  if(input.target_url) {
    endpoint(input.target_url);return {endpoint:input.target_url,owned:false};
  }
  const program=await executable(input),base=await cacheDirectory(input);
  const profile=await fs.mkdtemp(path.join(base,'browser-'));
  const args=['--headless=new','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
    '--user-data-dir='+profile,'--no-first-run','--no-default-browser-check','--disable-background-networking','about:blank'];
  if(process.env.PAPERFLOW_BROWSER_NO_SANDBOX==='1')args.unshift('--no-sandbox');
  const child=spawn(program,args,{detached:true,stdio:'ignore'});
  let launchError=false;child.on('error',()=>{launchError=true;});child.unref();
  for(let i=0;i<60;i++) {
    if(launchError||child.exitCode!==null)break;
    try {
      const port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);
      if(port>0&&port<65536)return {endpoint:'http://127.0.0.1:'+port,owned:true,profile,pid:child.pid};
    }catch{}
    await pause(100);
  }
  try {child.kill();}catch{}
  await fs.rm(profile,{recursive:true,force:true});fail('isolated_browser_launch_failed');
}

async function attachState(state) {
  const cdp=await Cdp.connect(state.browser.endpoint);
  try {
    const {targetInfos}=await cdp.send('Target.getTargets');
    if(!targetInfos.some(t=>t.targetId===state.target&&t.browserContextId===state.context))fail('isolated_session_closed');
    const {sessionId}=await cdp.send('Target.attachToTarget',{targetId:state.target,flatten:true});
    return {cdp,sessionId};
  }catch(error){cdp.close();throw error;}
}

async function dispose(state,{verifyContext=false}={}) {
  let cdp,contextDisposed=!state.context;
  try {
    cdp=await Cdp.connect(state.browser.endpoint);
    if(state.context)await cdp.send('Target.disposeBrowserContext',{browserContextId:state.context}).catch(()=>{});
    if(verifyContext&&!state.browser.owned&&state.context) {
      const contexts=await cdp.send('Target.getBrowserContexts');
      contextDisposed=Array.isArray(contexts.browserContextIds)&&!contexts.browserContextIds.includes(state.context);
    }
    if(state.browser.owned)await cdp.send('Browser.close').catch(()=>{});
  }catch{}finally{cdp?.close();}
  if(verifyContext&&!state.browser.owned&&!contextDisposed)fail('isolated_cleanup_incomplete');
  if(state.browser.owned&&state.browser.profile) {
    const address=new URL(state.browser.endpoint);
    address.protocol=address.protocol==='wss:'?'https:':'http:';
    let stopped=false;
    for(let i=0;i<40;i++) {
      try {
        const live=await jsonGet(new URL('/json/version',address),250);
        if(live.webSocketDebuggerUrl!==state.browser.endpoint){stopped=true;break;}
      }catch{stopped=true;break;}
      await pause(100);
    }
    if(!stopped)fail('isolated_cleanup_incomplete');
    // The DevTools server can stop just before Chromium finishes writing prefs.
    await pause(150);
    try {await fs.rm(state.browser.profile,{recursive:true,force:true,maxRetries:10,retryDelay:100});}
    catch{fail('isolated_cleanup_incomplete');}
  }
}

export async function connect(input) {
  const file=await stateFile(input),previous=await loadState(input);
  if(previous) {
    let attached;
    try {
      attached=await attachState(previous);
      const live=await browserIdentity(attached.cdp,attached.sessionId,input.origin,{classroom:true});
      if(live.ok&&sameIdentity(live.user,previous.user)&&classroomReady(live.classroom))
        return {ok:true,result:{outcome:'isolated_session_reused',user:live.user,session:input.session,isolated:true}};
    }catch{}finally{attached?.cdp.close();}
  }
  const sources=await discoverSources(input);
  if(!sources.length)fail('source_browser_access_unavailable');
  if(sources.length>1)fail('source_browser_selection_required');
  const source=await Cdp.connect(sources[0]);let credential;
  try {credential=await sourceSession(source,input);}finally{source.close();}
  if(previous&&!sameIdentity(previous.user,credential.user))fail('source_identity_changed');
  let browser,cdp,state,recorded=false;
  try {
    browser=await startBrowser(input);
    cdp=await Cdp.connect(browser.endpoint);
    const targetInfo=await cdp.send('Target.getTargets');
    if(source.ws.url===cdp.ws.url||targetInfo.targetInfos.some(t=>credential.source_targets.includes(t.targetId)))
      fail('target_browser_must_be_independent');
    browser.endpoint=cdp.ws.url;
    state={schema:1,phase:'connecting',origin:input.origin,session:input.session,user:credential.user,browser};
    await writeState(file,state);recorded=true;
    const {browserContextId}=await cdp.send('Target.createBrowserContext',{disposeOnDetach:false});
    state.context=browserContextId;await writeState(file,state);
    const {targetId}=await cdp.send('Target.createTarget',{url:'about:blank',browserContextId,background:true});state.target=targetId;
    await writeState(file,state);
    const {sessionId}=await cdp.send('Target.attachToTarget',{targetId,flatten:true});
    await cdp.send('Page.navigate',{url:input.origin+'/api/healthz'},sessionId);
    let ready=false;
    for(let i=0;i<60;i++) {
      try {ready=await runtime(cdp,sessionId,'location.origin==='+JSON.stringify(input.origin)+'&&document.readyState==="complete"',1000);}catch{}
      if(ready)break;await pause(100);
    }
    if(!ready)fail('isolated_origin_unavailable');
    let live;
    for(const cookie of credential.cookies) {
      await cdp.send('Network.setCookies',{cookies:[{name:'SESSION',value:cookie.value,url:input.origin+'/',
        path:'/',httpOnly:true,secure:input.origin.startsWith('https:'),sameSite:'Lax'}]},sessionId);
      live=await browserIdentity(cdp,sessionId,input.origin,{classroom:true});
      if(!live.ok||!sameIdentity(live.user,state.user))fail('isolated_identity_mismatch');
      if(classroomReady(live.classroom))break;
    }
    credential=null;
    if(!classroomReady(live?.classroom))fail('isolated_classroom_session_invalid');
    state.phase='ready';await writeState(file,state);
    if(previous)await dispose(previous);
    return {ok:true,result:{outcome:'isolated_session_connected',user:live.user,session:input.session,
      isolated:true,source_browser_modified:false,credential_files_created:false,credentials_in_output:false,classroom_verified:true}};
  }catch(error){
    if(state)await dispose(state);else if(browser)await dispose({browser});
    if(recorded) {
      if(previous)await writeState(file,previous);else await fs.unlink(file).catch(()=>{});
    }
    throw error;
  }
  finally{credential=null;cdp?.close();}
}

async function execute(input) {
  const state=await loadState(input);
  if(!state)fail('isolated_session_missing');
  const {cdp,sessionId}=await attachState(state);let created=false;
  try {
    const live=await browserIdentity(cdp,sessionId,input.origin);
    if(!live.ok)fail(live.error?.code||'isolated_session_expired');
    if(!sameIdentity(live.user,state.user))fail('isolated_identity_changed');
    if(input.file) {
      const selector=input.file_selector||'#paperflow-upload';
      if(selector==='#paperflow-upload')created=await runtime(cdp,sessionId,
        '(()=>{if(document.getElementById("paperflow-upload"))return false;const e=document.createElement("input");e.type="file";e.id="paperflow-upload";e.hidden=true;document.body.appendChild(e);return true;})()');
      if(state.browser.owned) {
        const {root}=await cdp.send('DOM.getDocument',{},sessionId);
        const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:root.nodeId,selector},sessionId);
        if(!nodeId)fail('upload_input_missing');
        await cdp.send('DOM.setFileInputFiles',{nodeId,files:[path.resolve(input.file)]},sessionId);
      } else {
        const file=path.resolve(input.file),info=await fs.stat(file);
        if(!info.isFile()||info.size>100*1024*1024)fail('invalid_upload_file');
        const key='__paperflow_file_'+process.pid;
        await runtime(cdp,sessionId,'globalThis['+JSON.stringify(key)+']=[]');
        try {
          const handle=await fs.open(file,'r');
          try {
            const buffer=Buffer.alloc(512*1024);
            for(;;) {
              const {bytesRead}=await handle.read(buffer,0,buffer.length,null);if(!bytesRead)break;
              const chunk=buffer.subarray(0,bytesRead).toString('base64');
              await runtime(cdp,sessionId,'globalThis['+JSON.stringify(key)+'].push(Uint8Array.from(atob('+JSON.stringify(chunk)+'),c=>c.charCodeAt(0)))');
            }
          }finally{await handle.close();}
          const assigned=await runtime(cdp,sessionId,'(()=>{const e=document.querySelector('+JSON.stringify(selector)+');if(!e)return false;'+
            'const d=new DataTransfer();d.items.add(new File(globalThis['+JSON.stringify(key)+'],'+JSON.stringify(path.basename(file))+',{type:"application/pdf"}));e.files=d.files;return true;})()');
          if(!assigned)fail('upload_input_missing');
        }finally{await runtime(cdp,sessionId,'delete globalThis['+JSON.stringify(key)+']').catch(()=>{});}
      }
    }
    return await runtime(cdp,sessionId,input.expression,(input.timeout||45)*1000+60000);
  }finally {
    if(created)await runtime(cdp,sessionId,'document.getElementById("paperflow-upload")?.remove()').catch(()=>{});
    cdp.close();
  }
}

async function status(input) {
  const state=await loadState(input);
  if(!state)return {ok:true,result:{outcome:'isolated_session_missing',connected:false}};
  let attached;
  try {
    attached=await attachState(state);
    const live=await browserIdentity(attached.cdp,attached.sessionId,input.origin,{classroom:true});
    const valid=live.ok&&sameIdentity(live.user,state.user)&&classroomReady(live.classroom);
    return {ok:true,result:{outcome:valid?'isolated_session_ready':'isolated_session_expired',connected:valid,
      isolated:true,user:state.user,session:input.session}};
  }catch{return {ok:true,result:{outcome:'isolated_session_closed',connected:false,session:input.session}};}
  finally{attached?.cdp.close();}
}

async function close(input) {
  const file=await stateFile(input),state=await loadState(input);
  let logoutAttempted=false,logoutHttpStatus=null;
  if(state) {
    let attached;
    try {
      attached=await attachState(state);
      const live=await browserIdentity(attached.cdp,attached.sessionId,input.origin);
      if(live.ok&&sameIdentity(live.user,state.user)) {
        logoutAttempted=true;
        const logout=await runtime(attached.cdp,attached.sessionId,
          '(async()=>{const r=await fetch("/api/logout",{method:"POST",credentials:"same-origin",redirect:"error"});return {status:r.status};})()');
        logoutHttpStatus=Number.isInteger(logout?.status)?logout.status:null;
      }
    }catch{}finally{attached?.cdp.close();}
    await dispose(state,{verifyContext:true});await fs.unlink(file);
  }
  return {ok:true,result:{outcome:state?'isolated_session_closed':'isolated_session_missing',session:input.session,
    isolated_record_found:!!state,logout_attempted:logoutAttempted,logout_http_status:logoutHttpStatus,
    native_browser_cleanup_performed:false,source_browser_modified:false}};
}

export async function main(input) {
  try {
    input.origin=originOf(input.origin);
    if(input.action==='connect')return await withSessionLock(input,()=>connect(input));
    if(input.action==='status')return await status(input);
    if(input.action==='close')return await withSessionLock(input,()=>close(input));
    if(input.action==='execute')return await execute(input);
    fail('invalid_session_action');
  }catch(error) {
    const rawCode=error instanceof SessionError?error.code:'isolated_browser_unavailable';
    const code=input.action==='execute'&&['browser_disconnected','browser_command_timeout','isolated_script_failed'].includes(rawCode)?
      'isolated_transport_uncertain':rawCode;
    const nextAction=code==='isolated_transport_uncertain'?'read_state_before_retry':/identity/.test(code)?'stop_and_verify_identity':
      /source_browser_access_unavailable|node_websocket_unavailable|executable_unavailable/.test(code)?'use_existing_authorized_browser_tool':
      /selection_required/.test(code)?'select_existing_authorized_source':
      /source_login_required|classroom_session/.test(code)?'refresh_source_login_once':
      /session_missing|session_closed|session_expired/.test(code)?'session_connect':
      code==='isolated_session_in_progress'?'wait_for_existing_session_operation':'check_session_access_before_retry';
    return {ok:false,error:{code,retryable:false,next_action:nextAction}};
  }
}

async function withSessionLock(input,fn) {
  const lock=(await stateFile(input))+'.lock';let descriptor;
  try {descriptor=await fs.open(lock,'wx',0o600);}
  catch(error){
    if(error.code!=='EEXIST')throw error;
    const old=await fs.lstat(lock);
    if(old.isSymbolicLink())fail('unsafe_session_cache');
    let owner;try {owner=JSON.parse(await fs.readFile(lock,'utf8'));}catch{}
    let dead=false;
    if(Number.isInteger(owner?.pid)&&owner.pid>0) {
      try {process.kill(owner.pid,0);}catch(e){dead=e.code==='ESRCH';}
    }else dead=Date.now()-old.mtimeMs>600000;
    if(!dead)fail('isolated_session_in_progress');
    const current=await fs.lstat(lock);
    if(current.ino!==old.ino||current.mtimeMs!==old.mtimeMs)fail('isolated_session_in_progress');
    await fs.unlink(lock);
    try {descriptor=await fs.open(lock,'wx',0o600);}catch{fail('isolated_session_in_progress');}
  }
  try{await descriptor.writeFile(JSON.stringify({pid:process.pid}));return await fn();}
  finally{await descriptor.close();await fs.unlink(lock).catch(()=>{});}
}

if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href) {
  let raw='';for await(const chunk of process.stdin)raw+=chunk;
  let result;try {result=await main(JSON.parse(raw));}catch {result={ok:false,error:{code:'invalid_session_request'}};}
  process.stdout.write(JSON.stringify(result)+'\n');
}
