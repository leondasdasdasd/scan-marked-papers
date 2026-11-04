#!/usr/bin/env python3
"""Daily, cached, verified updates for the installed scan-marked-papers skill."""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import zipfile

REPOSITORY = 'leondasdasdasd/scan-marked-papers'
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'release-manifest.json'
SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
REQUIRED = {'SKILL.md', 'agents/openai.yaml', 'references/skill-update.md', 'references/cli.md',
            'scripts/paperflow.py', 'scripts/paperflow.js', 'scripts/paperflow_base.py',
            'scripts/paperflow_upload.py', 'scripts/paperflow_workflow.js',
            'scripts/api_contracts.json', 'scripts/skill_update.py',
            'scripts/paperflow_session.py', 'scripts/paperflow_session.mjs'}
MAX_DOWNLOAD = 12 * 1024 * 1024


class UpdateError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def version(text):
    front = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
    if not front or not re.search(r'^name:\s*scan-marked-papers\s*$', front[1], re.M):
        raise UpdateError('invalid_skill_metadata')
    match = re.search(r'^\s+version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)["\']?\s*$', front[1], re.M)
    if not match or not SEMVER.fullmatch(match[1]):
        raise UpdateError('invalid_skill_version')
    return match[1]


def version_key(value):
    if not isinstance(value, str) or not SEMVER.fullmatch(value):
        raise UpdateError('invalid_skill_version')
    return tuple(int(n) for n in value.split('.'))


def current_version(root):
    return version((root / 'SKILL.md').read_text(encoding='utf-8'))


def cache_directory(root):
    base = os.environ.get('XDG_CACHE_HOME') or os.environ.get('LOCALAPPDATA')
    base = Path(base) if base else Path.home() / '.cache'
    return base / 'scan-marked-papers' / sha256(str(root.resolve()).encode())[:16]


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def fetch(url, limit=MAX_DOWNLOAD):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'scan-marked-papers-updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=8) as response:
        # Only official GitHub endpoints are used; credentials are never read.
        target = urllib.parse.urlsplit(response.geturl())
        if target.scheme != 'https' or target.hostname not in ('api.github.com', 'raw.githubusercontent.com'):
            raise UpdateError('unexpected_update_redirect')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError('update_download_too_large')
    return data


def safe_path(value):
    if not isinstance(value, str) or '\\' in value or ':' in value:
        raise UpdateError('unsafe_package_path')
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ('..', '.') for part in path.parts) or str(path) != value:
        raise UpdateError('unsafe_package_path')
    allowed = value in ('SKILL.md', 'README.md') or path.parts[0] in ('agents', 'references', 'scripts')
    if not allowed or any(part.startswith('.') or part == '__pycache__' for part in path.parts):
        raise UpdateError('unsafe_package_path')
    return value


def validate_manifest(data, expected=None):
    if not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('repository') != REPOSITORY:
        raise UpdateError('invalid_release_manifest')
    version_key(data.get('version'))
    if expected is not None and data['version'] != expected:
        raise UpdateError('release_version_mismatch')
    files = data.get('files')
    if not isinstance(files, dict) or not REQUIRED <= files.keys() or len(files) > 200:
        raise UpdateError('incomplete_release_manifest')
    for name, digest in files.items():
        safe_path(name)
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise UpdateError('invalid_release_digest')
    return data


def file_digest(path):
    if not path.is_file() or path.is_symlink():
        return None
    return sha256(path.read_bytes())


def local_conflicts(root, baseline, incoming):
    conflicts = []
    if (root / MANIFEST).is_symlink():
        conflicts.append(MANIFEST)
    for name, digest in baseline['files'].items():
        if file_digest(root / name) != digest:
            conflicts.append(name)
    for name in incoming['files']:
        path = root / name
        if name not in baseline['files'] and (path.exists() or path.is_symlink()):
            conflicts.append(name)
        if any(parent.is_symlink() for parent in path.parents if parent != root.parent):
            conflicts.append(name)
    return sorted(set(conflicts))


def stage_package(raw, manifest, manifest_raw, metadata_raw, destination):
    expected = set(manifest['files']) | {MANIFEST}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            seen = set()
            total = 0
            for info in package.infolist():
                name = info.filename
                if not name.startswith('scan-marked-papers/') or info.is_dir():
                    raise UpdateError('unsafe_package_path')
                relative = name.removeprefix('scan-marked-papers/')
                if relative != MANIFEST:
                    safe_path(relative)
                if relative not in expected or relative in seen or stat.S_ISLNK(info.external_attr >> 16):
                    raise UpdateError('unexpected_package_entry')
                seen.add(relative)
                total += info.file_size
                if total > MAX_DOWNLOAD or info.file_size > MAX_DOWNLOAD:
                    raise UpdateError('update_package_too_large')
                data = package.read(info)
                if relative == MANIFEST:
                    if data != manifest_raw:
                        raise UpdateError('package_manifest_mismatch')
                elif sha256(data) != manifest['files'][relative]:
                    raise UpdateError('package_checksum_mismatch')
                if relative == 'SKILL.md' and data != metadata_raw:
                    raise UpdateError('package_metadata_mismatch')
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            if seen != expected:
                raise UpdateError('incomplete_update_package')
    except (zipfile.BadZipFile, RuntimeError, KeyError) as exc:
        raise UpdateError('invalid_update_package') from exc
    if current_version(destination) != manifest['version']:
        raise UpdateError('package_version_mismatch')
    for name in manifest['files']:
        if name.endswith('.py'):
            compile((destination / name).read_bytes(), name, 'exec')
    registry = json.loads((destination / 'scripts/api_contracts.json').read_text())
    if not isinstance(registry.get('operations'), list) or not registry['operations']:
        raise UpdateError('invalid_api_registry')


def install(root, stage, baseline, manifest, workspace):
    conflicts = local_conflicts(root, baseline, manifest)
    if conflicts:
        return {'outcome': 'local_changes_preserved', 'conflicts': conflicts, 'updated': False}
    backup = workspace / 'backup'
    changed = set(baseline['files']) | set(manifest['files']) | {MANIFEST}
    for name in changed:
        path = root / name
        if path.exists():
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    applied = []
    try:
        for name in sorted(changed - {MANIFEST}) + [MANIFEST]:
            target = root / name
            applied.append(name)
            if name not in manifest['files'] and name != MANIFEST:
                target.unlink(missing_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name('.' + target.name + '.skill-update')
            shutil.copyfile(stage / name, temporary)
            if target.exists():
                os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
            else:
                os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        if current_version(root) != manifest['version'] or any(file_digest(root / name) != digest for name, digest in manifest['files'].items()):
            raise UpdateError('installed_verification_failed')
    except Exception as original:
        failed = []
        for name in reversed(applied):
            target, saved = root / name, backup / name
            try:
                if saved.exists():
                    shutil.copy2(saved, target)
                else:
                    target.unlink(missing_ok=True)
            except OSError:
                failed.append(name)
        if failed:
            raise UpdateError('update_rollback_failed') from original
        raise UpdateError('update_rolled_back') from original
    finally:
        for name in changed:
            path = root / name
            path.with_name('.' + path.name + '.skill-update').unlink(missing_ok=True)
    for name in changed:
        if name.endswith('.py'):
            parent=(root/name).parent/'__pycache__'
            for cached in parent.glob(Path(name).stem+'.*.pyc'):
                cached.unlink(missing_ok=True)
    return {'outcome': 'updated', 'updated': True}


def ensure(root=ROOT, *, force=False, cache=None, now=None, get=fetch):
    root = Path(root).resolve()
    cache = Path(cache) if cache else cache_directory(root)
    checked_at = now or dt.datetime.now().astimezone()
    day = checked_at.date().isoformat()
    installed_version = current_version(root)
    # A source checkout contains unpublished development changes and is never an update destination.
    if os.environ.get('PAPERFLOW_AUTO_UPDATE','1').lower() in ('0','false','off'):
        return {'outcome':'auto_update_disabled','updated':False,'installed_version':installed_version,'network_checked':False}
    if (root / '.git').exists():
        return {'outcome': 'development_checkout', 'updated': False, 'installed_version': installed_version, 'network_checked': False}
    cache.mkdir(parents=True, exist_ok=True)
    state_path = cache / 'state.json'
    lock = cache / 'update.lock'
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > 600:
            lock.unlink()
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return {'outcome': 'update_in_progress', 'updated': False, 'network_checked': False}
    os.close(descriptor)
    result = {'repository': REPOSITORY, 'checked_date': day, 'checked_at': checked_at.isoformat(),
              'installed_version': installed_version, 'updated': False, 'network_checked': False}
    workspace = None
    try:
        # Check again under the lock: another invocation may have just finished.
        previous = read_json(state_path)
        if (not force and previous.get('outcome') != 'checking'
                and previous.get('checked_date') == day and previous.get('installed_version') == installed_version):
            return {**previous, 'outcome': 'cached_today', 'previous_outcome': previous.get('outcome'), 'updated': False, 'network_checked': False}
        atomic_json(state_path, {**result, 'outcome': 'checking'})
        result['network_checked'] = True
        latest = json.loads(get('https://api.github.com/repos/' + REPOSITORY + '/commits/main'))
        commit = latest.get('sha')
        if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise UpdateError('invalid_release_commit')
        base = 'https://raw.githubusercontent.com/' + REPOSITORY + '/' + commit + '/'
        metadata = get(base + 'SKILL.md')
        remote_version = version(metadata.decode('utf-8'))
        result.update(source_commit=commit, latest_version=remote_version)
        if version_key(remote_version) <= version_key(installed_version):
            result['outcome'] = 'up_to_date' if remote_version == installed_version else 'local_version_newer'
        elif not (root / MANIFEST).is_file():
            result['outcome'] = 'baseline_missing'
        else:
            baseline = validate_manifest(read_json(root / MANIFEST), installed_version)
            manifest_raw = get(base + MANIFEST)
            manifest = validate_manifest(json.loads(manifest_raw), remote_version)
            conflicts = local_conflicts(root, baseline, manifest)
            if conflicts:
                result.update(outcome='local_changes_preserved', conflicts=conflicts)
            else:
                package = get(base + 'scan-marked-papers.zip')
                result['package_sha256'] = sha256(package)
                workspace = Path(tempfile.mkdtemp(prefix='skill-update-', dir=cache))
                stage = workspace / 'staged'
                stage.mkdir()
                stage_package(package, manifest, manifest_raw, metadata, stage)
                result.update(install(root, stage, baseline, manifest, workspace))
                result['installed_version'] = current_version(root)
        atomic_json(state_path, result)
        return result
    except Exception as exc:
        result.update(outcome='update_failed', error=exc.args[0] if isinstance(exc, UpdateError) else 'update_check_unavailable')
        # Never put URLs from exception messages, auth headers or arbitrary remote text in state/logs.
        if result['error'] == 'update_rollback_failed':
            result['recovery_directory'] = str(workspace)
            workspace = None
        try:
            atomic_json(state_path, result)
        except OSError:
            pass
        return result
    finally:
        if workspace:
            shutil.rmtree(workspace, ignore_errors=True)
        lock.unlink(missing_ok=True)


def status(root=ROOT, *, cache=None):
    root = Path(root).resolve()
    state = read_json((Path(cache) if cache else cache_directory(root)) / 'state.json')
    return {'outcome': 'update_status', 'installed_version': current_version(root), 'network_checked': False, 'last_check': state or None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('ensure')
    p.add_argument('--force', action='store_true')
    commands.add_parser('status')
    args = parser.parse_args()
    try:
        result = ensure(force=args.force) if args.command == 'ensure' else status()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, UpdateError) as exc:
        print(json.dumps({'outcome': 'update_failed', 'updated': False, 'error': str(exc) if isinstance(exc, UpdateError) else 'update_check_unavailable'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
