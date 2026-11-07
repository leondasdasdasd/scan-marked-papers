"""Open an explicitly named Playwright session using an existing browser only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

DEFAULT_WRAPPER = Path.home()/'.codex/skills/playwright/scripts/playwright_cli.sh'
DOCKER_BROWSER_PROBE = r"""const fs=require('fs');let found=null;
try{for(const name of fs.readdirSync('/ms-playwright').filter(n=>/^chromium-\d+$/.test(n)).sort((a,b)=>Number(b.split('-')[1])-Number(a.split('-')[1]))){
 for(const leaf of ['chrome-linux64/chrome','chrome-linux/chrome']){const p='/ms-playwright/'+name+'/'+leaf;
  try{fs.accessSync(p,fs.constants.X_OK);if(fs.statSync(p).isFile()){found=p;break;}}catch{}}
 if(found)break;}}catch{}process.stdout.write(JSON.stringify(found));"""


def open_browser(args):
    started=time.monotonic()
    def result(ok,**fields):
        return {'ok':ok,**fields,'wall_seconds':round(time.monotonic()-started,3)}
    if args.browser_backend!='playwright':
        return result(False,error={'code':'playwright_backend_required'})
    import paperflow_session
    if paperflow_session.available(args):
        return result(False,error={'code':'isolated_session_already_bound','next_action':'session-status'})
    cli=args.playwright_cli
    if cli:
        node=shutil.which('node')
        if not node or not cli.is_file():
            return result(False,error={'code':'existing_playwright_cli_unavailable'})
        command=[node,str(cli)]
    else:
        if not shutil.which(args.wrapper):
            return result(False,error={'code':'playwright_wrapper_unavailable'})
        command=[args.wrapper]
    command+=['-s='+args.browser_session,'open',args.base_url,'--browser','chromium']
    executable=getattr(args,'executable',None)
    source='explicit' if executable else 'cli_default'
    if executable and not cli and Path(args.wrapper).resolve()==DEFAULT_WRAPPER.resolve():
        # A host executable is not necessarily visible inside the cloud wrapper.
        source='explicit_wrapper_runtime'
    if not executable and not cli and Path(args.wrapper).resolve()==DEFAULT_WRAPPER.resolve() and shutil.which('docker'):
        try:
            probe=subprocess.run(['docker','exec',os.environ.get('PLAYWRIGHT_DOCKER_CONTAINER','codex-playwright-browser'),
                'node','-e',DOCKER_BROWSER_PROBE],capture_output=True,text=True,timeout=min(args.timeout,5))
            found=json.loads(probe.stdout) if probe.returncode==0 else None
            if isinstance(found,str) and found.startswith('/ms-playwright/chromium-') and found.endswith('/chrome'):
                executable=found;source='existing_docker_runtime'
        except (OSError,ValueError,subprocess.TimeoutExpired):
            pass
    try:
        if executable:
            if not Path(executable).is_absolute():
                return result(False,error={'code':'browser_executable_must_be_absolute'})
            with tempfile.TemporaryDirectory(prefix='.paperflow-browser-',dir=Path.cwd()) as directory:
                config=Path(directory)/'launch.json'
                config.write_text(json.dumps({'browser':{'browserName':'chromium','launchOptions':{
                    'executablePath':executable,'headless':True}}}),encoding='utf-8');config.chmod(0o600)
                proc=subprocess.run(command+['--config',str(config)],capture_output=True,text=True,timeout=args.timeout+15)
        else:
            proc=subprocess.run(command,capture_output=True,text=True,timeout=args.timeout+15)
    except subprocess.TimeoutExpired:
        return result(False,error={'code':'browser_start_uncertain','retryable':False,'next_action':'inspect_named_browser_session'})
    except OSError:
        return result(False,error={'code':'browser_backend_unavailable','retryable':False})
    if proc.returncode or '### Browser' not in proc.stdout:
        missing='is not installed' in proc.stderr or 'executable doesn' in proc.stderr
        return result(False,error={'code':'browser_executable_unavailable' if missing else 'browser_open_failed',
            'retryable':False,'next_action':'verify_existing_browser_runtime'})
    # CLI output may contain an SSO redirect URL. Return no page URL or raw log.
    return result(True,result={'outcome':'browser_opened','session':args.browser_session,
        'executable_source':source,**({'executable':executable} if executable else {}),
        'authentication_verified':False,'business_execution_verified':False,'submitted':False})
