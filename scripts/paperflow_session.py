"""Isolated browser transport; no Cookie or storage-state files are exchanged."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent


def state_path(args):
    base = os.environ.get('XDG_CACHE_HOME') or os.environ.get('LOCALAPPDATA') or str(Path.home() / '.cache')
    key = hashlib.sha256((args.base_url + '\0' + args.browser_session).encode()).hexdigest()[:24]
    return Path(base) / 'scan-marked-papers-sessions' / (key + '.json')


def available(args):
    return bool(args.browser_session and state_path(args).is_file())


def invoke(args, action, expression=None):
    node = shutil.which('node')
    if not node:
        return {'ok': False, 'error': {'code': 'isolated_browser_requires_existing_node'}}
    payload = {'action': action, 'origin': args.base_url, 'session': args.browser_session,
               'timeout': args.timeout}
    for key in ('source_url', 'source_target', 'target_url', 'executable'):
        value = getattr(args, key, None)
        if value:
            payload[key] = value
    if expression is not None:
        payload['expression'] = expression
        if getattr(args, 'action', None) == 'upload':
            payload['file'] = str(args.file.resolve())
            payload['file_selector'] = args.file_input_selector
    try:
        proc = subprocess.run([node, str(ROOT / 'paperflow_session.mjs')],
                              input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              text=True, timeout=args.timeout + 90)
        result = json.loads(proc.stdout)
        if proc.returncode or not isinstance(result, dict) or not isinstance(result.get('ok'), bool):
            raise ValueError('invalid_session_result')
        return result
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': {'code': 'isolated_transport_uncertain',
                                      'next_action': 'read_state_before_retry'}}
    except (OSError, ValueError):
        return {'ok': False, 'error': {'code': 'isolated_browser_unavailable'}}
