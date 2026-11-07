"""Exercise offline checks against complete and damaged on-disk installations."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_release
import paperflow_doctor


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name);self.root=self.directory/'skill'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('.git','tests','__pycache__','scan-marked-papers.zip'))
        build_release.build(self.root)
        # Existence checks must never launch the wrapper: it could install or connect.
        self.wrapper=self.directory/'wrapper';self.marker=self.directory/'launched'
        self.wrapper.write_text('#!/bin/sh\ntouch "'+str(self.marker)+'"\nexit 2\n');self.wrapper.chmod(0o700)
        self.args=argparse.Namespace(browser_backend='playwright',browser_session=None,playwright_cli=None,
            wrapper=str(self.wrapper),browser_executable='missing-doctor-agent-browser',read_timeout=5)

    def test_complete_install_checks_real_imports_without_launching_wrapper(self):
        result=paperflow_doctor.doctor(self.args,self.root)
        self.assertTrue(result['ok'],result)
        self.assertGreater(result['result']['installation']['checked_files'],15)
        self.assertTrue(result['result']['python']['renderer_python'])
        self.assertFalse(self.marker.exists());self.assertFalse(result['result']['network_checked'])
        self.assertFalse(result['result']['browser']['execution_verified'])
        self.assertFalse(result['result']['browser']['authentication_verified'])

    def test_missing_modified_and_linked_files_fail_before_helper_execution(self):
        (self.root/'scripts/paperflow_runtime.py').unlink()
        (self.root/'references/cli.md').write_text('modified local instructions')
        saved=self.root/'agents/openai.yaml';saved.unlink();saved.symlink_to(self.wrapper)
        with patch.object(paperflow_doctor,'python_runtime',side_effect=AssertionError('must not run modified helpers')):
            result=paperflow_doctor.doctor(self.args,self.root)
        self.assertFalse(result['ok']);checked=result['result']['installation']
        self.assertIn('scripts/paperflow_runtime.py',checked['missing'])
        self.assertIn('references/cli.md',checked['modified']);self.assertIn('agents/openai.yaml',checked['unsafe'])
        self.assertFalse(self.marker.exists())

    def test_default_python_cli_finds_explicit_existing_renderer_without_updates(self):
        system=Path('/usr/bin/python3')
        if not system.is_file():self.skipTest('no separate system Python')
        env={**os.environ,'PAPERFLOW_AUTO_UPDATE':'1','PAPERFLOW_PYTHON':sys.executable,
             'PYTHONDONTWRITEBYTECODE':'1','XDG_CACHE_HOME':str(self.directory/'cache')}
        proc=subprocess.run([str(system),str(self.root/'scripts/paperflow.py'),'--wrapper',str(self.wrapper),'doctor'],
                            cwd=self.directory,env=env,capture_output=True,text=True,timeout=15)
        result=json.loads(proc.stdout)
        self.assertEqual(proc.returncode,0,result);self.assertTrue(result['ok'])
        self.assertTrue(result['result']['python']['renderer_python'])
        self.assertFalse((self.directory/'cache').exists());self.assertFalse(self.marker.exists())

    def test_selected_missing_browser_entries_are_diagnosed_without_execution(self):
        for backend in ('playwright','agent-browser','wrapper'):
            with self.subTest(backend=backend):
                self.args.browser_backend='playwright' if backend=='wrapper' else backend
                self.args.playwright_cli=self.directory/'absent.js' if backend=='playwright' else None
                self.args.wrapper=str(self.directory/'absent-wrapper')
                result=paperflow_doctor.doctor(self.args,self.root)
                self.assertFalse(result['ok']);self.assertTrue(result['result']['installation']['ok'])
                self.assertFalse(result['result']['browser']['entrypoint_found'])
                self.assertIn('unavailable',result['result']['browser']['error'])
                self.assertFalse(self.marker.exists())

    def test_absent_doctor_helper_returns_structured_installation_error(self):
        (self.root/'scripts/paperflow_doctor.py').unlink()
        proc=subprocess.run([sys.executable,str(self.root/'scripts/paperflow.py'),'doctor'],cwd=self.directory,
            env={**os.environ,'PAPERFLOW_AUTO_UPDATE':'0','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,1);self.assertEqual(json.loads(proc.stdout)['error']['code'],'installation_incomplete')
        self.assertNotIn('Traceback',proc.stderr)

    def test_bad_manifest_is_reported_without_echoing_contents(self):
        (self.root/'release-manifest.json').write_text('not-json private-fixture-marker')
        result=paperflow_doctor.doctor(self.args,self.root)
        self.assertFalse(result['ok']);self.assertEqual(result['result']['installation']['error'],'installation_manifest_unavailable')
        self.assertNotIn('private-fixture-marker',json.dumps(result))


if __name__=='__main__':unittest.main()
