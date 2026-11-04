"""Updater uses a pinned synthetic release and real on-disk installs; no network."""
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import skill_update as updater

DAY = dt.datetime(2026, 11, 4, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
COMMIT = 'a' * 40


def contents(release):
    files = {name: b'pass\n' if name.endswith('.py') else b'content\n' for name in updater.REQUIRED}
    files['SKILL.md'] = ('---\nname: scan-marked-papers\nmetadata:\n  version: "' + release + '"\n---\n').encode()
    files['scripts/api_contracts.json'] = b'{"operations":[{"name":"classes"}]}'
    return files


def manifest_for(files, release):
    return {'schema_version': 1, 'repository': updater.REPOSITORY, 'version': release,
            'files': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}


def archive_for(files, manifest, extras=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as package:
        for name, value in files.items():
            package.writestr('scan-marked-papers/' + name, value)
        package.writestr('scan-marked-papers/' + updater.MANIFEST, json.dumps(manifest).encode())
        for name, value in (extras or {}).items():
            package.writestr(name, value)
    return out.getvalue()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'skills' / 'scan-marked-papers'
        self.root.mkdir(parents=True)
        self.cache = Path(self.tmp.name) / 'cache'
        self.local = contents('1.9.0')
        for name, value in self.local.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        self.baseline = manifest_for(self.local, '1.9.0')
        (self.root / updater.MANIFEST).write_text(json.dumps(self.baseline))
        self.calls = []
        self.set_remote('1.9.1')

    def set_remote(self, release):
        self.remote = contents(release)
        self.manifest = manifest_for(self.remote, release)
        self.package = archive_for(self.remote, self.manifest)

    def get(self, url):
        self.calls.append(url)
        if url.endswith('/commits/main'):
            return json.dumps({'sha': COMMIT}).encode()
        self.assertIn('/' + COMMIT + '/', url)
        if url.endswith('/SKILL.md'):
            return self.remote['SKILL.md']
        if url.endswith('/' + updater.MANIFEST):
            return json.dumps(self.manifest).encode()
        if url.endswith('/scan-marked-papers.zip'):
            return self.package
        raise AssertionError(url)

    def ensure(self, **kwargs):
        return updater.ensure(self.root, cache=self.cache, now=DAY, get=self.get, **kwargs)

    def test_latest_is_recorded_and_same_day_calls_make_no_network_requests(self):
        self.set_remote('1.9.0')
        first = self.ensure()
        self.assertEqual(first['outcome'], 'up_to_date')
        self.assertEqual(len(self.calls), 2)
        again = self.ensure()
        self.assertEqual(again['outcome'], 'cached_today')
        self.assertFalse(again['network_checked'])
        self.assertEqual(len(self.calls), 2)
        state = json.loads((self.cache / 'state.json').read_text())
        self.assertEqual(state['checked_date'], '2026-11-04')
        self.assertEqual(state['source_commit'], COMMIT)

    def test_next_local_day_checks_again_and_force_refreshes_today(self):
        self.set_remote('1.9.0')
        self.ensure()
        self.ensure(force=True)
        self.assertEqual(len(self.calls), 4)
        next_day = updater.ensure(self.root, cache=self.cache, now=DAY + dt.timedelta(days=1), get=self.get)
        self.assertEqual(next_day['outcome'], 'up_to_date')
        self.assertEqual(len(self.calls), 6)

    def test_newer_release_is_verified_installed_and_cached_without_touching_task_data(self):
        checkpoint = self.root / 'teacher-checkpoint.json'
        checkpoint.write_text('{"stop_after":"grading"}')
        another = self.root.parent / 'another-skill'
        another.mkdir()
        (another / 'SKILL.md').write_text('other skill')
        before_checkpoint = checkpoint.read_bytes()
        result = self.ensure()
        self.assertEqual(result['outcome'], 'updated')
        self.assertTrue(result['updated'])
        self.assertEqual(result['installed_version'], '1.9.1')
        for name, value in self.remote.items():
            self.assertEqual((self.root / name).read_bytes(), value)
        self.assertEqual(checkpoint.read_bytes(), before_checkpoint)
        self.assertEqual((another / 'SKILL.md').read_text(), 'other skill')
        self.assertFalse(list(self.cache.glob('skill-update-*')))
        again = self.ensure()
        self.assertEqual(again['outcome'], 'cached_today')
        self.assertFalse(again['updated'])
        self.assertEqual(len(self.calls), 4)

    def test_local_edits_are_preserved_and_not_repeatedly_checked(self):
        target = self.root / 'scripts/paperflow.js'
        target.write_text('my local change')
        result = self.ensure()
        self.assertEqual(result['outcome'], 'local_changes_preserved')
        self.assertIn('scripts/paperflow.js', result['conflicts'])
        self.assertEqual(target.read_text(), 'my local change')
        self.assertEqual(updater.current_version(self.root), '1.9.0')
        self.assertEqual(len(self.calls), 3)
        self.ensure()
        self.assertEqual(len(self.calls), 3)

    def test_download_failure_is_cached_for_the_day_and_never_claims_latest(self):
        def failed(url):
            self.calls.append(url)
            raise OSError('private network detail must not be logged')
        first = updater.ensure(self.root, cache=self.cache, now=DAY, get=failed)
        self.assertEqual(first['outcome'], 'update_failed')
        self.assertNotIn('private network', json.dumps(first))
        again = self.ensure()
        self.assertEqual(again['previous_outcome'], 'update_failed')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(updater.current_version(self.root), '1.9.0')

    def test_older_remote_never_downgrades_even_with_force(self):
        self.set_remote('1.8.0')
        result = self.ensure(force=True)
        self.assertEqual(result['outcome'], 'local_version_newer')
        self.assertFalse(result['updated'])
        self.assertEqual(updater.current_version(self.root), '1.9.0')

    def test_legacy_install_without_manifest_is_not_overwritten(self):
        (self.root / updater.MANIFEST).unlink()
        result = self.ensure()
        self.assertEqual(result['outcome'], 'baseline_missing')
        self.assertFalse(result['updated'])
        self.assertEqual(updater.current_version(self.root), '1.9.0')

    def test_changed_archive_bytes_cannot_pass_manifest_verification(self):
        files = dict(self.remote)
        files['scripts/paperflow.js'] = b'unverified code'
        self.package = archive_for(files, self.manifest)
        result = self.ensure()
        self.assertEqual(result['outcome'], 'update_failed')
        self.assertEqual(result['error'], 'package_checksum_mismatch')
        self.assertEqual(updater.current_version(self.root), '1.9.0')

    def test_unexpected_or_traversal_entries_are_rejected_without_writes(self):
        self.package = archive_for(self.remote, self.manifest, {'scan-marked-papers/../../escape': b'bad'})
        result = self.ensure()
        self.assertEqual(result['outcome'], 'update_failed')
        self.assertEqual(result['error'], 'unsafe_package_path')
        self.assertFalse((Path(self.tmp.name) / 'escape').exists())
        self.assertEqual(updater.current_version(self.root), '1.9.0')

    def test_install_failure_rolls_back_every_applied_file(self):
        original = updater.os.replace
        failed = False
        def replace(source, destination):
            nonlocal failed
            if Path(destination) == self.root / 'scripts/paperflow_workflow.js' and not failed:
                failed = True
                raise OSError('synthetic disk failure')
            return original(source, destination)
        with patch.object(updater.os, 'replace', side_effect=replace):
            result = self.ensure()
        self.assertEqual(result['outcome'], 'update_failed')
        self.assertEqual(result['error'], 'update_rolled_back')
        for name, value in self.local.items():
            self.assertEqual((self.root / name).read_bytes(), value)
        self.assertEqual(json.loads((self.root / updater.MANIFEST).read_text()), self.baseline)
        self.assertFalse(list(self.root.rglob('*.skill-update')))

    def test_explicitly_disabled_updates_stay_offline_even_when_forced(self):
        with patch.dict(updater.os.environ, {'PAPERFLOW_AUTO_UPDATE':'0'}):
            result=self.ensure(force=True)
        self.assertEqual(result['outcome'],'auto_update_disabled')
        self.assertFalse(self.calls)

    def test_source_checkout_and_status_are_offline(self):
        (self.root / '.git').mkdir()
        result = self.ensure(force=True)
        self.assertEqual(result['outcome'], 'development_checkout')
        self.assertFalse(self.calls)
        result = updater.status(self.root, cache=self.cache)
        self.assertFalse(result['network_checked'])
        self.assertEqual(result['installed_version'], '1.9.0')

    def test_concurrent_update_uses_one_lock_and_does_not_request_network_twice(self):
        self.cache.mkdir()
        (self.cache / 'update.lock').write_text('locked')
        result = self.ensure()
        self.assertEqual(result['outcome'], 'update_in_progress')
        self.assertFalse(self.calls)
        updater.atomic_json(self.cache / 'state.json', {
            'checked_date': DAY.date().isoformat(), 'installed_version': '1.9.0', 'outcome': 'checking'})
        result = self.ensure()
        self.assertEqual(result['outcome'], 'update_in_progress')
        self.assertFalse(self.calls)
        (self.cache / 'update.lock').unlink()
        result = self.ensure()
        self.assertEqual(result['outcome'], 'updated')
        self.assertEqual(updater.current_version(self.root), '1.9.1')

    def test_new_upstream_file_cannot_replace_untracked_local_customization(self):
        self.remote['scripts/local.py'] = b'upstream value\n'
        self.manifest = manifest_for(self.remote, '1.9.1')
        self.package = archive_for(self.remote, self.manifest)
        target = self.root / 'scripts/local.py'
        target.write_text('my customization')
        result = self.ensure()
        self.assertEqual(result['outcome'], 'local_changes_preserved')
        self.assertEqual(target.read_text(), 'my customization')

    def test_removed_official_files_are_cleaned_but_unmanaged_files_survive(self):
        old = self.root / 'scripts/obsolete.py'
        old.write_text('old file')
        self.baseline['files']['scripts/obsolete.py'] = updater.file_digest(old)
        (self.root / updater.MANIFEST).write_text(json.dumps(self.baseline))
        result = self.ensure()
        self.assertEqual(result['outcome'], 'updated')
        self.assertFalse(old.exists())

    def test_symlinks_are_preserved_as_conflicts_not_followed(self):
        target = self.root / 'scripts/paperflow.js'
        external = Path(self.tmp.name) / 'external.txt'
        external.write_text('outside')
        target.unlink()
        target.symlink_to(external)
        result = self.ensure()
        self.assertEqual(result['outcome'], 'local_changes_preserved')
        self.assertEqual(external.read_text(), 'outside')


if __name__ == '__main__':
    unittest.main()
