"""Input preservation and frame syntax checks before browser dispatch."""
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


class LocalGuardTests(unittest.TestCase):
    def run_cli(self,args):
        out=io.StringIO()
        with patch.object(sys,'argv',['paperflow',*args]),contextlib.redirect_stdout(out):
            code=paperflow.main()
        return code,json.loads(out.getvalue())

    def test_aliases_cannot_overwrite_plan_or_checkpoint(self):
        for alias in ('exact','relative','symlink','hardlink','checkpoint','snapshot','temporary'):
            with self.subTest(alias=alias),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'plan.json';source.write_text('{"operations":[]}')
                target=source
                if alias=='relative':target=root/'sub'/'..'/'plan.json';(root/'sub').mkdir()
                if alias=='symlink':target=root/'alias.json';target.symlink_to(source)
                if alias=='hardlink':target=root/'alias.json';target.hardlink_to(source)
                if alias=='temporary':target=root/'plan';source.rename(root/'plan.tmp');source=root/'plan.tmp'
                before=source.read_bytes()
                args=['--base-url','https://example.test','--batch-id','abc','--browser-session','test']
                if alias=='checkpoint':args+=['--checkpoint',str(target),'frames','--edits',str(source)]
                elif alias=='snapshot':args+=['--checkpoint',str(target),'snapshot','--output',str(source)]
                else:args+=['--output',str(target),'frames','--edits',str(source)]
                with patch.object(paperflow.base,'browser',side_effect=AssertionError('must not dispatch')):
                    code,data=self.run_cli(args)
                self.assertEqual(code,1);self.assertEqual(data['error']['code'],'file_path_conflict')
                self.assertEqual(source.read_bytes(),before)
                if alias=='temporary':self.assertFalse(target.exists())

    def test_collect_preserves_raw_result_when_output_aliases_input(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory)/'raw.json';raw.write_text('{"ok":true}')
            code,data=self.run_cli(['--output',str(raw),'collect','--result',str(raw)])
            self.assertEqual(code,1);self.assertEqual(data['error']['code'],'file_path_conflict')
            self.assertEqual(raw.read_text(),'{"ok":true}')

    def test_invalid_frames_leave_checkpoint_untouched_and_do_not_dispatch(self):
        samples=[
            ({'type':'set','id':'二(7)'},'invalid_frame_id'),
            ({'type':'set','id':'x'*101},'invalid_frame_id'),
            ({'type':'set','id':'q1','regions':[{'page':0,'bbox':[0,.1,1,float('nan')]}]},'invalid_region'),
            ({'type':'set','id':'q1','regions':[{'page':True,'bbox':[0,0,1,1]}]},'invalid_region'),
            ({'type':'set','id':'q1','regions':[{'page':0,'bbox':[.8,.1,.2,.9]}]},'invalid_region'),
            ({'type':'split','id':'q1','children':[{'id':'bad.id'},{'id':'q2'}]},'invalid_frame_id'),
            ({'type':'shift','ids':['q1'],'dx':float('inf'),'dy':0},'invalid_shift'),
        ]
        for action in ('frames','run'):
            for operation,error in samples:
                with self.subTest(action=action,operation=operation),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);plan=root/'plan.json';cp=root/'checkpoint.json';step=root/'step.js'
                    cp.write_text(json.dumps({'origin':'https://example.test','batch_id':'abc'}));before=cp.read_bytes()
                    edits={'operations':[operation]};plan.write_text(json.dumps(edits if action=='frames' else {'frames':edits}))
                    args=['--base-url','https://example.test','--batch-id','abc','--checkpoint',str(cp),
                          '--emit-script',str(step),action,'--edits' if action=='frames' else '--plan',str(plan)]
                    with patch.object(paperflow.base,'browser',side_effect=AssertionError('must not dispatch')):
                        code,data=self.run_cli(args)
                    self.assertEqual(code,1);self.assertEqual(data['error']['code'],error)
                    self.assertEqual(cp.read_bytes(),before);self.assertFalse(step.exists())
                    if error=='invalid_frame_id':self.assertEqual(data['error']['constraint'],'[A-Za-z0-9_-]{1,100}')

    def test_valid_ascii_id_and_chinese_label_still_use_browser_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            plan=Path(directory)/'plan.json'
            plan.write_text(json.dumps({'operations':[{'type':'set','id':'q_2-7','label':'二(7)',
                'regions':[{'page':0,'bbox':[0,0,1,1]}]}]}))
            with patch.object(paperflow.base,'browser',return_value={'ok':False,'error':{'code':'version_conflict'}}) as browser:
                code,data=self.run_cli(['--batch-url','https://example.test/exams/abc/analysis',
                    '--browser-session','test','frames','--edits',str(plan)])
            self.assertEqual(code,1);self.assertEqual(data['error']['code'],'version_conflict')
            browser.assert_called_once()


if __name__=='__main__':unittest.main()
