"""Exercise automatic updater entry, restart and offline exclusions in real CLI."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        shutil.copytree(ROOT/'scripts',self.root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        self.log=self.root/'update-calls.json'
        self.cli=self.root/'scripts/paperflow.py'
        self.updater=self.root/'scripts/skill_update.py'
        self.prefix=[sys.executable,str(self.cli),'--base-url','https://example.test','--emit-script',str(self.root/'step.js')]

    def stub(self, body):
        self.updater.write_text("import json\nfrom pathlib import Path\nLOG=Path("+repr(str(self.log))+")\ndef ensure(root):\n"+body)

    def call(self, arguments):
        result=subprocess.run(arguments,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return json.loads(result.stdout)

    def test_first_use_bootstrap_restarts_into_updated_code_before_emitting(self):
        self.stub("    calls=json.loads(LOG.read_text()) if LOG.exists() else []\n"
                  "    calls.append('called');LOG.write_text(json.dumps(calls))\n"
                  "    return {'updated':len(calls)==1,'outcome':'updated' if len(calls)==1 else 'cached_today'}\n")
        data=self.call([*self.prefix,'classes'])
        self.assertFalse(data['result']['executed'])
        self.assertEqual(json.loads(self.log.read_text()),['called','called'])
        self.assertTrue((self.root/'step.js').exists())

    def test_update_failure_preserves_cli_execution_and_reports_real_failure(self):
        self.stub("    LOG.write_text('called')\n    return {'updated':False,'outcome':'update_failed','error':'update_check_unavailable'}\n")
        result=subprocess.run([*self.prefix,'classes'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertEqual(json.loads(result.stderr)['skill_update']['outcome'],'update_failed')
        self.assertTrue(self.log.exists())

    def test_help_api_catalog_and_collect_never_start_updater(self):
        self.stub("    raise RuntimeError('offline action invoked updater')\n")
        help_result=subprocess.run([sys.executable,str(self.cli),'--help'],capture_output=True,text=True)
        self.assertEqual(help_result.returncode,0)
        listed=self.call([sys.executable,str(self.cli),'api-list'])
        self.assertTrue(listed['operations'])
        raw=self.root/'result.json'
        raw.write_text(json.dumps({'ok':True,'result':{'outcome':'waiting'},'checkpoint':{'origin':'https://example.test','batch_id':'test'}}))
        result=self.call([sys.executable,str(self.cli),'--base-url','https://example.test','collect','--result',str(raw)])
        self.assertEqual(result['result']['outcome'],'waiting')
        self.assertFalse(self.log.exists())


if __name__=='__main__':unittest.main()
