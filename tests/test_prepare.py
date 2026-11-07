"""Real-process checks for bounded PDF access and offline preparation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import paperflow_upload as upload

class PrepareTests(unittest.TestCase):
    def test_real_pdf_hash_pages_and_split_without_browser_or_network(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'paper.pdf'
            doc=pymupdf.open();doc.new_page(width=1190.55,height=841.89);doc.new_page(width=1190.55,height=841.89);doc.save(path);doc.close()
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/paperflow.py'),'prepare',
                '--file',str(path),'--pages-per-paper','2'],capture_output=True,text=True,timeout=10)
            self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout)
            data=json.loads(proc.stdout)
            self.assertEqual(data['result']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(data['result']['page_count'],2)
            self.assertEqual(data['result']['paper_count'],1)
            self.assertEqual(data['result']['page_geometry'],[{
                'width_points':1190.55,'height_points':841.89,'paper_size':'A3',
                'orientation':'landscape','pages':2}])
            self.assertFalse(data['capabilities']['browser_authentication_verified'])
            self.assertFalse(data['submitted'])
            self.assertEqual(upload.probe(path,pages_per_paper=3)['error']['code'],'invalid_pdf_split')


    def test_mixed_and_nonstandard_geometry_does_not_invent_one_paper_size(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mixed.pdf'
            doc=pymupdf.open()
            doc.new_page(width=595.28,height=841.89)
            doc.new_page(width=842,height=595)
            doc.new_page(width=500,height=500)
            doc.save(path);doc.close()
            data=upload.probe(path)
            self.assertTrue(data['ok'],data)
            sizes=data['result']['page_geometry']
            self.assertEqual([(s['paper_size'],s['orientation'],s['pages']) for s in sizes],
                [('A4','portrait',1),('A4','landscape',1),(None,'square',1)])
            self.assertNotIn('paper_count',data['result'])

    def test_stalled_worker_is_bounded_and_does_not_echo_os_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'stall.pdf';path.write_bytes(b'%PDF-')
            # A worker import stall exercises the same subprocess deadline as an OS read.
            shadow=Path(directory)/'pymupdf.py';shadow.write_text('import time; time.sleep(30)')
            previous=os.environ.get('PYTHONPATH')
            os.environ['PYTHONPATH']=directory
            started=time.monotonic()
            try:data=upload.probe(path,timeout=.25)
            finally:
                if previous is None:os.environ.pop('PYTHONPATH',None)
                else:os.environ['PYTHONPATH']=previous
            self.assertLess(time.monotonic()-started,3)
            self.assertEqual(data['error']['code'],'pdf_read_timeout')
            self.assertEqual(data['error']['next_action'],'use_existing_file_tool_or_accessible_copy')
            self.assertNotIn(directory,json.dumps(data))

    def test_page_limit_applies_without_split_and_encryption_has_specific_diagnostic(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);doc=pymupdf.open()
            for _ in range(601):doc.new_page()
            doc.save(root/'large.pdf');doc.close()
            self.assertEqual(upload.probe(root/'large.pdf')['error']['code'],'invalid_pdf_page_count')
            doc=pymupdf.open();doc.new_page();doc.save(root/'encrypted.pdf',encryption=pymupdf.PDF_ENCRYPT_AES_256,user_pw='fixture');doc.close()
            self.assertEqual(upload.probe(root/'encrypted.pdf')['error']['code'],'pdf_password_required')

    def test_default_python_reuses_existing_environment_for_page_count(self):
        import pymupdf
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pdf=root/'paper.pdf';doc=pymupdf.open();doc.new_page();doc.new_page();doc.save(pdf);doc.close()
            # The first real worker shadows its parser with an ImportError; fallback uses the existing environment.
            shadow=root/'pymupdf.py';shadow.write_text("raise ImportError('fixture parser absent')")
            original=upload.subprocess.run;calls=[]
            def run(command,**kwargs):
                calls.append(command[0])
                if len(calls)==1:kwargs['env']={**kwargs['env'],'PYTHONPATH':str(root)}
                return original(command,**kwargs)
            with patch('paperflow_runtime.python_candidates',return_value=iter((Path(sys.executable),))),patch.object(upload.subprocess,'run',side_effect=run):
                result=upload.probe(pdf,pages_per_paper=2)
            self.assertTrue(result['ok'],result);self.assertEqual(result['result']['paper_count'],1);self.assertEqual(len(calls),2)

    def test_invalid_header_is_rejected_before_business_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'paper.pdf';path.write_text('not a PDF')
            data=upload.probe(path)
            self.assertFalse(data['ok'])
            self.assertEqual(data['error']['code'],'invalid_pdf_header')

if __name__=='__main__':unittest.main()
