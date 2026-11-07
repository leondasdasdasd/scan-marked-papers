"""Input preservation and frame syntax checks before browser dispatch."""
import contextlib
import hashlib
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

    def test_generated_scripts_cannot_replace_input_receipts_or_checkpoint(self):
        engine='paperflow-engine-'+hashlib.sha256(paperflow.source().encode()).hexdigest()[:20]+'.js'
        for generated in ('step-poll.js',engine):
            for argument in ('plan','output','checkpoint','emit_script'):
                with self.subTest(generated=generated,argument=argument),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);target=root/generated;target.write_text('{}')
                    cp=root/'checkpoint.json';cp.write_text('{"origin":"https://example.test","batch_id":"abc"}')
                    args=['--base-url','https://example.test','--batch-id','abc','--checkpoint',str(cp),'--sync-evaluate']
                    if argument=='emit_script':
                        # The generated engine path may also be chosen as the requested step.
                        if generated=='step-poll.js':continue
                        args+=['--emit-script',str(target),'run']
                    else:
                        args+=['--emit-script',str(root/'step.js')]
                        if argument=='output':args+=['--output',str(target)]
                        if argument=='checkpoint':
                            args[args.index('--checkpoint')+1]=str(target)
                            target.write_text(cp.read_text())
                        args+=['run']
                        if argument=='plan':args+=['--plan',str(target)]
                    before={path:path.read_bytes() for path in root.iterdir()}
                    with patch.object(paperflow.base,'browser',side_effect=AssertionError('must not dispatch')):
                        code,data=self.run_cli(args)
                    self.assertEqual(code,1);self.assertEqual(data['error']['code'],'file_path_conflict')
                    self.assertEqual({path:path.read_bytes() for path in root.iterdir()},before)

    def test_review_assets_preserve_metadata_pdf_and_existing_receipts(self):
        import pymupdf
        for name in ('review.json','frame-index.json.tmp','raw-page-1.png','contact-sheet.png'):
            for kind in ('metadata','output','pdf'):
                with self.subTest(name=name,kind=kind),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);out=root/'review';out.mkdir();pdf=root/'paper.pdf'
                    doc=pymupdf.open();doc.new_page();pdf.write_bytes(doc.tobytes());doc.close()
                    if kind=='pdf':pdf.rename(out/name);pdf=out/name
                    meta={'batch_id':'abc','source_pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                        'reference_start':0,'pages_per_paper':1,'frames':[{'id':'q1','label':'1',
                        'regions':[{'page':0,'bbox':[.1,.1,.9,.9]}]}]}
                    metadata=out/name if kind=='metadata' else root/'metadata.json';metadata.write_text(json.dumps(meta))
                    args=['--batch-id','abc']
                    if kind=='output':
                        (out/name).write_text('existing receipt');args+=['--output',str(out/name)]
                    args+=['review','--metadata',str(metadata),'--pdf',str(pdf),'--out',str(out)]
                    before={path:path.read_bytes() for path in root.rglob('*') if path.is_file()}
                    code,data=self.run_cli(args)
                    self.assertEqual(code,1);self.assertEqual(data['error']['code'],'file_path_conflict')
                    self.assertEqual({path:path.read_bytes() for path in root.rglob('*') if path.is_file()},before)
                    if kind=='pdf':
                        with self.assertRaisesRegex(ValueError,'file_path_conflict'):paperflow.render_bundle(meta,pdf,out)

    def test_generated_aliases_and_legal_emit(self):
        for kind in ('symlink','hardlink','relative'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);plan=root/'plan.json';plan.write_text('{}');alias=root/'step-poll.js'
                if kind=='symlink':alias.symlink_to(plan)
                elif kind=='hardlink':alias.hardlink_to(plan)
                else:
                    plan=alias;plan.write_text('{}');(root/'sub').mkdir();plan=root/'sub/../step-poll.js'
                code,data=self.run_cli(['--batch-id','abc','--emit-script',str(root/'step.js'),'--sync-evaluate','run','--plan',str(plan)])
                self.assertEqual(code,1);self.assertEqual(data['error']['code'],'file_path_conflict');self.assertEqual(plan.read_text(),'{}')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan=root/'plan.json';plan.write_text('{}')
            code,data=self.run_cli(['--batch-id','abc','--emit-script',str(root/'step.js'),'--sync-evaluate','run','--plan',str(plan)])
            self.assertEqual(code,0);self.assertTrue(Path(data['result']['engine_file']).is_file())
            self.assertTrue(Path(data['result']['poll_file']).is_file());self.assertEqual(plan.read_text(),'{}')

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
