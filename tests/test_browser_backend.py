"""Exercise browser transport with a real subprocess and isolated fake CLI."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import paperflow
import paperflow_base as base


class BrowserBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.executable=self.root/'browser with spaces'
        self.record=self.root/'request.json'
        self.executable.write_text('#!'+sys.executable+'\n'+
            'import json,sys\nfrom pathlib import Path\n'+
            'Path('+repr(str(self.record))+').write_text(json.dumps({"args":sys.argv[1:],"stdin":sys.stdin.read()}))\n'+
            'print(json.dumps({"success":True,"data":{"result":{"ok":True,"result":{"ready":False,"outcome":"needs_frame_review"}}}}))\n')
        self.executable.chmod(0o700)
        self.args=argparse.Namespace(browser_backend='agent-browser',browser_executable=str(self.executable),
            browser_session='teacher-test',timeout=1,interval=2,base_url='https://example.test',
            batch_id='test',checkpoint=None)

    def tearDown(self):self.temp.cleanup()

    def test_expression_passed_through_stdin_without_shell_or_credentials(self):
        result=paperflow.execute(self.args,'run')
        self.assertTrue(result['ok'])
        request=json.loads(self.record.read_text())
        self.assertEqual(request['args'],['--session','teacher-test','--json','eval','--stdin'])
        self.assertNotIn('async(page)',request['stdin'])
        self.assertIn('location.origin!==input.origin',request['stdin'])
        self.assertIn('"origin": "https://example.test"',request['stdin'])
        self.assertIn('"action": "run"',request['stdin'])

    def test_native_upload_required_does_not_invoke_process(self):
        result=base.browser(self.args,'native page upload')
        self.assertEqual(result['error']['code'],'upload_requires_native_browser_file_tool')
        self.assertFalse(self.record.exists())

    def test_error_and_confirmation_outputs_are_not_business_success(self):
        samples=[[],None,{'success':False,'error':'private token must not be echoed'},
                 {'success':True,'data':{'confirmation_required':True}},
                 {'success':True,'data':{'result':None}}]
        for sample in samples:
            self.executable.write_text('#!'+sys.executable+'\nprint('+repr(json.dumps(sample))+')\n')
            result=base.browser(self.args,'unused','1')
            self.assertFalse(result['ok'])
            self.assertNotIn('private token',json.dumps(result))

    def test_existing_node_cli_uses_same_session_without_npx_or_wrapper(self):
        cli=self.root/'existing cli.js'
        cli.write_text('const fs=require("fs");fs.writeFileSync('+json.dumps(str(self.record))+',JSON.stringify(process.argv.slice(2)));console.log("### Result\\n"+JSON.stringify({ok:true,result:{outcome:"access_verified"}}));')
        self.args.browser_backend='playwright';self.args.playwright_cli=cli
        self.args.wrapper=str(self.root/'must never be run')
        result=base.browser(self.args,'async(page)=>42','unused')
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['outcome'],'access_verified')
        self.assertEqual(json.loads(self.record.read_text()),['-s=teacher-test','run-code','async(page)=>42'])
        cli.unlink()
        result=base.browser(self.args,'unused','unused')
        self.assertEqual(result['error']['code'],'existing_playwright_cli_unavailable')

    def test_default_origin_is_internal_and_override_is_preserved(self):
        for extra,expected in [([],base.DEFAULT_ORIGIN),(['--base-url','https://example.test'],'https://example.test')]:
            argv=['paperflow',*extra,'--batch-id','test','--browser-session','teacher','inspect']
            with patch.object(sys,'argv',argv),patch.object(paperflow,'execute',return_value={'ok':True,'result':{}}) as run:
                with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(paperflow.main(),0)
                self.assertEqual(run.call_args.args[0].base_url,expected)


if __name__=='__main__':unittest.main()
