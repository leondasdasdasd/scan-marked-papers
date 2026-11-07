"""Offline installation and existing-runtime checks; never launch a browser."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import skill_update


def installation(root):
    try:
        if (root/skill_update.MANIFEST).is_symlink():raise skill_update.UpdateError('unsafe_release_manifest')
        manifest=skill_update.validate_manifest(json.loads((root/skill_update.MANIFEST).read_text()),skill_update.current_version(root))
        missing=[];modified=[];unsafe=[]
        for name,digest in manifest['files'].items():
            path=root/name
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root)):
                unsafe.append(name)
            elif not path.is_file():missing.append(name)
            elif skill_update.file_digest(path)!=digest:modified.append(name)
        return {'ok':not (missing or modified or unsafe),'version':manifest['version'],
            'checked_files':len(manifest['files']),'missing':missing,'modified':modified,'unsafe':unsafe}
    except (OSError,ValueError,skill_update.UpdateError) as exc:
        return {'ok':False,'error':str(exc) if isinstance(exc,skill_update.UpdateError) else 'installation_manifest_unavailable'}


def python_runtime(timeout):
    from paperflow_runtime import python_candidates
    started=time.monotonic();attempts=[];parser_python=None;renderer_python=None
    worker="""import importlib,json
result={}
for name in ('pymupdf','PIL.Image','PIL.ImageDraw'):
 try:importlib.import_module(name);result[name]=True
 except Exception:result[name]=False
print(json.dumps(result))
"""
    for candidate in (sys.executable,*python_candidates()):
        remaining=timeout-(time.monotonic()-started)
        if remaining<=0:break
        attempt={'python':str(candidate),'parser_available':False,'renderer_available':False}
        try:
            result=subprocess.run([str(candidate),'-c',worker],capture_output=True,text=True,
                timeout=remaining,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
            data=json.loads(result.stdout)
            if result.returncode or not isinstance(data,dict):raise ValueError()
            attempt['parser_available']=data.get('pymupdf') is True
            attempt['renderer_available']=all(data.get(name) is True for name in ('pymupdf','PIL.Image','PIL.ImageDraw'))
            if attempt['parser_available'] and parser_python is None:parser_python=str(candidate)
            if attempt['renderer_available']:renderer_python=str(candidate)
        except subprocess.TimeoutExpired:attempt['error']='runtime_check_timeout'
        except (OSError,ValueError):attempt['error']='runtime_check_failed'
        attempts.append(attempt)
        if renderer_python:break
    return {'ok':True,'interpreter':sys.executable,
        'parser_available':parser_python is not None,'renderer_available':renderer_python is not None,
        'parser_python':parser_python,'renderer_python':renderer_python,
        'attempts':attempts,'wall_seconds':round(time.monotonic()-started,3)}


def browser_entrypoint(args,root):
    import paperflow_session
    backend=args.browser_backend
    if args.browser_session and paperflow_session.available(args):backend='isolated'
    node=shutil.which('node')
    result={'backend':backend,'entrypoint_found':False,'execution_verified':False,'authentication_verified':False}
    if backend=='isolated':
        result['entrypoint_found']=bool(node and (root/'scripts/paperflow_session.mjs').is_file())
        if result['entrypoint_found']:
            try:
                check=subprocess.run([node,'-e',"console.log(JSON.stringify({fetch:typeof fetch==='function',websocket:typeof WebSocket==='function'}))"],
                    capture_output=True,text=True,timeout=3)
                features=json.loads(check.stdout)
                if check.returncode or not isinstance(features,dict):raise ValueError()
                result['node_features']={name:features.get(name) is True for name in ('fetch','websocket')}
                result['entrypoint_found']=all(result['node_features'].values())
            except (OSError,ValueError,subprocess.TimeoutExpired):result['entrypoint_found']=False
        if not result['entrypoint_found']:result['error']='isolated_browser_requires_node_fetch_websocket'
    elif backend=='agent-browser':
        result['entrypoint_found']=bool(shutil.which(args.browser_executable))
        if not result['entrypoint_found']:result['error']='agent_browser_executable_unavailable'
    elif args.playwright_cli:
        result['entrypoint_kind']='direct_cli'
        result['entrypoint_found']=bool(node and args.playwright_cli.is_file())
        if not result['entrypoint_found']:result['error']='existing_playwright_cli_unavailable'
    else:
        result['entrypoint_kind']='wrapper'
        result['entrypoint_found']=bool(shutil.which(args.wrapper))
        if not result['entrypoint_found']:result['error']='playwright_wrapper_unavailable'
    return result


def doctor(args,root):
    checked=installation(root)
    # Do not execute helper files from an installation already known to be modified.
    if checked['ok']:
        try:runtime=python_runtime(args.read_timeout);browser=browser_entrypoint(args,root)
        except ImportError:
            runtime={'ok':False,'error':'runtime_helper_unavailable'}
            browser={'entrypoint_found':False,'execution_verified':False,'authentication_verified':False}
    else:
        runtime={'ok':False,'skipped':'installation_integrity_failed'}
        browser={'entrypoint_found':False,'execution_verified':False,'authentication_verified':False,'skipped':'installation_integrity_failed'}
    ready=checked['ok'] and runtime['ok'] and browser['entrypoint_found']
    return {'ok':ready,'result':{'outcome':'offline_prerequisites_available' if ready else 'offline_prerequisites_incomplete',
        'installation':checked,'python':runtime,'browser':browser,'network_checked':False,
        'business_execution_verified':False,'submitted':False}}
