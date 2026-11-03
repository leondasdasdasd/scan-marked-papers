"""Offline entry-point boundaries for generic browser tools."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import paperflow


class ScriptEntryTests(unittest.TestCase):
    def run_cli(self, args):
        out = io.StringIO()
        with patch.object(sys, 'argv', ['paperflow', *args]), contextlib.redirect_stdout(out):
            code = paperflow.main()
        return code, json.loads(out.getvalue())

    def test_emit_from_link_uses_no_browser_and_binds_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory)/'request.js'
            with patch.object(paperflow.base, 'browser', side_effect=AssertionError('must not execute')):
                code, data = self.run_cli(['--batch-url', 'https://example.test/exams/abc/analysis?class_id=4',
                    '--emit-script', str(script), 'run'])
            self.assertEqual(code, 0)
            self.assertFalse(data['result']['executed'])
            self.assertEqual(data['result']['origin'], 'https://example.test')
            text = script.read_text()
            self.assertNotIn('__LEGACY__', text)
            self.assertLess(len(text.encode()),3000)
            self.assertTrue(Path(data['result']['engine_file']).exists())
            self.assertIn('engine_not_loaded',text)
            self.assertEqual(script.stat().st_mode & 0o777, 0o600)

    def test_cached_engine_executes_repeated_small_steps_without_business_page_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);step=root/'step.js'
            code,data=self.run_cli(['--base-url','https://example.test','--emit-script',str(step),'classes'])
            self.assertEqual(code,0)
            engine=Path(data['result']['engine_file'])
            runner=r"""
const fs=require('fs');global.location={origin:'https://example.test'};let requests=0;
global.fetch=async(path,opts)=>{if(path!=='/api/classroom/classes'||opts.method!=='GET')throw Error('unexpected');requests++;return {ok:true,status:200,json:async()=>({semester_id:'1',classes:[]})};};
(async()=>{const step=fs.readFileSync(process.argv[2],'utf8');const first=await eval(step);if(first.error?.code!=='engine_not_loaded'||requests)throw Error('must load engine first');
const loaded=eval(fs.readFileSync(process.argv[3],'utf8'));if(!loaded.ok)throw Error('load failed');
for(let i=0;i<3;i++){const d=await eval(step);if(!d.ok||d.result.outcome!=='class_directory')throw Error('step failed');}
if(requests!==3)throw Error('repeated business actions');location.origin='https://other.test';const wrong=await eval(step);if(wrong.error?.code!=='origin_mismatch')throw Error('cross origin');
console.log(JSON.stringify({step_bytes:Buffer.byteLength(step),requests}));})();
"""
            result=subprocess.run(['node','-',str(step),str(engine)],input=runner,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertLess(json.loads(result.stdout)['step_bytes'],3000)

    def test_conflicting_link_or_nonbusiness_path_rejects_before_browser(self):
        samples = [
            ['--batch-url', 'https://example.test/exams/abc/analysis', '--batch-id', 'other'],
            ['--batch-url', 'https://user:pass@example.test/exams/abc/analysis'],
            ['--batch-url', 'https://example.test/settings'],
            ['--batch-url', 'https://example.test/exams/abc/analysis', '--base-url', 'https://other.test'],
        ]
        with patch.object(paperflow.base, 'browser', side_effect=AssertionError('must not execute')):
            for args in samples:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.run_cli([*args, '--emit-script', '/unused', 'run'])

    def test_collect_persists_only_matching_result_and_compacts_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, checkpoint, output = [root/p for p in ('raw.json', 'checkpoint.json', 'full.json')]
            cp = {'origin': 'https://example.test', 'batch_id': 'abc', 'catalog_receipt': {'state': 'confirming'}}
            data = {'ok': False, 'error': {'code': 'transport_uncertain'}, 'checkpoint': cp,
                'calls': [{'status': 422, 'ms': 2}]}
            raw.write_text(json.dumps(data))
            code, shown = self.run_cli(['--batch-url', 'https://example.test/exams/abc/analysis',
                '--checkpoint', str(checkpoint), '--output', str(output), 'collect', '--result', str(raw)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(checkpoint.read_text()), cp)
            self.assertEqual(json.loads(output.read_text()), data)
            self.assertNotIn('checkpoint', shown)
            self.assertEqual(shown['http']['failed'], 1)
            before = checkpoint.read_bytes()
            data['checkpoint']['batch_id'] = 'other'
            raw.write_text(json.dumps(data))
            code, shown = self.run_cli(['--batch-url', 'https://example.test/exams/abc/analysis',
                '--checkpoint', str(checkpoint), 'collect', '--result', str(raw)])
            self.assertEqual(code, 1)
            self.assertEqual(shown['error']['code'], 'checkpoint_origin_or_batch_mismatch')
            self.assertEqual(before, checkpoint.read_bytes())

    def test_offline_review_reuses_metadata_and_checks_source_without_browser(self):
        import hashlib
        import pymupdf
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, metadata, images = root/'source.pdf', root/'metadata.json', root/'images'
            doc = pymupdf.open();doc.new_page();doc.save(pdf);doc.close()
            review = {'batch_id': 'abc', 'source_pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                'reference_start': 0, 'pages_per_paper': 1, 'frames': [
                    {'id': 'q1', 'label': '1', 'regions': [{'page': 0, 'bbox': [.1, .1, .8, .5]}]}]}
            metadata.write_text(json.dumps({'ok': True, 'result': {'review': review}}))
            args = ['--batch-url', 'https://example.test/exams/abc/analysis', 'review',
                '--metadata', str(metadata), '--pdf', str(pdf), '--out', str(images)]
            with patch.object(paperflow.base, 'browser', side_effect=AssertionError('must not execute')):
                code, data = self.run_cli(args)
                self.assertEqual(code, 0)
                self.assertTrue((images/'reference-page-1.png').exists())
                self.assertFalse(json.loads((images/'review.json').read_text())['reviewed'])
                review['source_pdf_sha256'] = 'wrong'
                metadata.write_text(json.dumps(review))
                code, data = self.run_cli(args)
                self.assertEqual(code, 1)
                self.assertEqual(data['error']['code'], 'source_pdf_hash_mismatch')

    def test_foreign_checkpoint_cannot_generate_a_mutating_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cp = root/'checkpoint.json';cp.write_text(json.dumps({'origin': 'https://other.test', 'batch_id': 'abc'}))
            script = root/'request.js'
            code, data = self.run_cli(['--batch-url', 'https://example.test/exams/abc/analysis',
                '--checkpoint', str(cp), '--emit-script', str(script), 'run'])
            self.assertEqual(code, 1)
            self.assertFalse(script.exists())
            self.assertEqual(data['error']['code'], 'checkpoint_origin_or_batch_mismatch')


if __name__ == '__main__':
    unittest.main()
