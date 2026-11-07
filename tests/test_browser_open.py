import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import paperflow_browser as browser


class BrowserOpenTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.record=self.root/'request.json';self.wrapper=self.root/'existing wrapper'
        self.wrapper.write_text('#!'+sys.executable+'\nimport json,sys\nfrom pathlib import Path\n'+
            'p=Path(sys.argv[-1]);d={"args":sys.argv[1:],"config":json.loads(p.read_text()),"file_mode":p.stat().st_mode&511,"dir_mode":p.parent.stat().st_mode&511}\n'+
            'Path('+repr(str(self.record))+').write_text(json.dumps(d))\n'+
            'print("### Browser `test` opened\\n### Page\\nhttps://login.test/?ticket=must-not-leak")\n')
        self.wrapper.chmod(0o700)
        self.args=argparse.Namespace(browser_backend='playwright',wrapper=str(self.wrapper),playwright_cli=None,
            browser_session='new-task',base_url='https://example.test',timeout=2,executable='/existing/browser with spaces')
    def tearDown(self):self.temp.cleanup()

    def test_native_launch_uses_private_config_without_echoing_redirects(self):
        with patch.object(Path,'cwd',return_value=self.root):r=browser.open_browser(self.args)
        self.assertTrue(r['ok']);self.assertFalse(r['result']['authentication_verified'])
        self.assertNotIn('must-not-leak',json.dumps(r));request=json.loads(self.record.read_text())
        self.assertEqual(request['args'][:4],['-s=new-task','open','https://example.test','--browser'])
        self.assertEqual(request['config']['browser']['launchOptions']['executablePath'],self.args.executable)
        self.assertEqual((request['file_mode'],request['dir_mode']),(0o600,0o700))
        self.assertFalse(Path(request['args'][-1]).parent.exists())

    def test_known_cloud_wrapper_probes_existing_runtime_without_installing(self):
        self.args.executable=None;run=subprocess.run;commands=[]
        def dispatch(command,**kw):
            commands.append(command)
            if command[0]=='docker':return subprocess.CompletedProcess(command,0,json.dumps('/ms-playwright/chromium-1237/chrome-linux64/chrome'),'')
            return run(command,**kw)
        with patch.object(browser,'DEFAULT_WRAPPER',self.wrapper),patch.object(Path,'cwd',return_value=self.root),patch.object(browser.subprocess,'run',side_effect=dispatch):
            r=browser.open_browser(self.args)
        self.assertTrue(r['ok']);self.assertEqual(r['result']['executable_source'],'existing_docker_runtime')
        self.assertEqual(commands[0][:3],['docker','exec','codex-playwright-browser'])
        self.assertEqual(len(commands),2)
        self.assertNotIn('install',' '.join(commands[0]))

    def test_launch_timeout_cleans_private_config_and_preserves_uncertainty(self):
        paths=[]
        def timeout(command,**kw):
            paths.append(Path(command[-1]));self.assertTrue(paths[-1].is_file())
            raise subprocess.TimeoutExpired(command,17)
        with patch.object(Path,'cwd',return_value=self.root),patch.object(browser.subprocess,'run',side_effect=timeout):
            r=browser.open_browser(self.args)
        self.assertEqual(r['error']['code'],'browser_start_uncertain');self.assertFalse(r['error']['retryable'])
        self.assertFalse(paths[0].parent.exists())

    def test_close_targets_only_selected_session_and_suppresses_raw_output(self):
        reply=subprocess.CompletedProcess([],0,'Browser closed https://login.test/?ticket=must-not-leak','')
        with patch.object(browser.subprocess,'run',return_value=reply) as run:
            r=browser.close_browser(self.args)
        self.assertTrue(r['ok']);self.assertEqual(r['result']['outcome'],'browser_closed')
        self.assertEqual(run.call_args.args[0],[str(self.wrapper),'-s=new-task','close'])
        self.assertFalse(r['result']['application_logout_performed'])
        self.assertFalse(r['result']['shared_runtime_stopped'])
        self.assertNotIn('must-not-leak',json.dumps(r))

    def test_close_respects_isolated_owner_and_does_not_launch_native_tool(self):
        with patch('paperflow_session.available',return_value=True),patch.object(browser.subprocess,'run') as run:
            r=browser.close_browser(self.args)
        self.assertEqual(r['error']['next_action'],'session-close');run.assert_not_called()

    def test_close_timeout_never_retries_or_reports_success(self):
        with patch.object(browser.subprocess,'run',side_effect=subprocess.TimeoutExpired('close',17)) as run:
            r=browser.close_browser(self.args)
        self.assertEqual(r['error']['code'],'browser_close_uncertain')
        self.assertFalse(r['error']['retryable']);self.assertEqual(run.call_count,1)


if __name__=='__main__':unittest.main()
