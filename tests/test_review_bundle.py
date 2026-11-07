import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from paperflow import render_bundle


class ReviewBundleTests(unittest.TestCase):
    def fixture(self,directory):
        import pymupdf
        path=Path(directory)/'paper.pdf';doc=pymupdf.open()
        for color in ((1,0,0),(0,0,1)):
            page=doc.new_page(width=600,height=800)
            page.draw_rect(page.rect,color=color,fill=color)
        doc.save(path);doc.close()
        metadata={'batch_id':'batch','source_pdf_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'frame_revision':'rev-1','reference_student_id':'ref','reference_start':1,'pages_per_paper':1,
            'frames':[{'id':f'f{i}','label':f'题{i}','parent_id':None,
                'regions':[{'page':0,'bbox':[.1,.02+i*.12,.9,.10+i*.12]}]} for i in range(7)]}
        return path,metadata

    def test_reference_offset_context_and_bounded_sheets_preserve_all_frames(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            path,metadata=self.fixture(directory);out=Path(directory)/'review'
            result=render_bundle(metadata,path,out)
            self.assertFalse(result['reviewed']);self.assertEqual(result['decoded_pages'],1)
            self.assertEqual(len(result['detail_sheets']),2)
            index=json.loads((out/'frame-index.json').read_text())
            self.assertFalse(index['reviewed']);self.assertEqual(index['frame_revision'],'rev-1')
            self.assertEqual(index['source_pdf_sha256'],metadata['source_pdf_sha256'])
            self.assertEqual([f['frame_id'] for f in index['frames']],[f'f{i}' for i in range(7)])
            self.assertTrue(all(f['pdf_page']==2 for f in index['frames']))
            with Image.open(out/'raw-page-1.png') as raw:
                self.assertEqual(raw.getpixel((0,0)),(0,0,255))
            for name in result['detail_sheets']:
                members=[f for f in index['frames'] if f['image_file']==name]
                self.assertLessEqual(len(members),6)
                with Image.open(out/name) as sheet:
                    self.assertEqual(sheet.width,1600);self.assertLessEqual(sheet.height,1404)
            manifest=json.loads((out/'review.json').read_text())
            self.assertFalse(manifest['reviewed'])
            self.assertEqual(manifest['frame_index'],'frame-index.json')

    def test_missing_renderer_dependency_is_explicit_and_does_not_create_output(self):
        import builtins
        from unittest.mock import patch
        original_import=builtins.__import__
        def without_renderer(name,*args,**kwargs):
            if name=='pymupdf':raise ModuleNotFoundError('test renderer unavailable')
            return original_import(name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'review'
            with patch('builtins.__import__',side_effect=without_renderer), patch('paperflow_runtime.python_candidates',return_value=iter(())):
                with self.assertRaisesRegex(ValueError,'review_dependency_unavailable'):
                    render_bundle({},Path(directory)/'absent.pdf',out)
            self.assertFalse(out.exists())

    def test_identical_bundle_reuses_images_and_never_approves_review(self):
        from unittest.mock import patch
        import pymupdf
        with tempfile.TemporaryDirectory() as directory:
            pdf,metadata=self.fixture(directory);out=Path(directory)/'review'
            render_bundle(metadata,pdf,out)
            before={p.name:p.stat().st_mtime_ns for p in out.glob('*.png')}
            with patch.object(pymupdf,'open',side_effect=AssertionError('must not decode')):
                result=render_bundle(metadata,pdf,out)
            self.assertTrue(result['cache_hit']);self.assertEqual(result['decoded_pages'],0)
            self.assertFalse(result['reviewed']);self.assertEqual(before,{p.name:p.stat().st_mtime_ns for p in out.glob('*.png')})

    def test_changed_frames_reuse_raw_page_but_rebuild_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf,metadata=self.fixture(directory);out=Path(directory)/'review'
            render_bundle(metadata,pdf,out);raw=(out/'raw-page-1.png').read_bytes()
            metadata['frame_revision']='rev-2';metadata['frames'][0]['regions'][0]['bbox']=[.2,.02,.9,.1]
            result=render_bundle(metadata,pdf,out)
            self.assertFalse(result['cache_hit']);self.assertEqual(result['decoded_pages'],0)
            self.assertEqual(result['raw_pages_reused'],1);self.assertEqual(raw,(out/'raw-page-1.png').read_bytes())
            index=json.loads((out/'frame-index.json').read_text())
            self.assertEqual(index['frame_revision'],'rev-2');self.assertEqual(index['frames'][0]['bbox'],[.2,.02,.9,.1])

    def test_corrupted_cached_image_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf,metadata=self.fixture(directory);out=Path(directory)/'review'
            render_bundle(metadata,pdf,out);image=out/'raw-page-1.png';original=image.read_bytes();image.write_bytes(b'bad')
            result=render_bundle(metadata,pdf,out)
            self.assertFalse(result['cache_hit']);self.assertEqual(result['decoded_pages'],1)
            self.assertEqual(image.read_bytes(),original)

    def test_wrong_source_is_rejected_before_creating_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            path,metadata=self.fixture(directory);metadata['source_pdf_sha256']='wrong'
            out=Path(directory)/'review'
            with self.assertRaisesRegex(ValueError,'source_pdf_hash_mismatch'):
                render_bundle(metadata,path,out)
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
