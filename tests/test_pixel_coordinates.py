import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import paperflow
from paperflow_coordinates import normalize_pixel_plan


class PixelCoordinatesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.image=self.root/'raw-page-1.png'
        self.image.write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',2000,1000))
        self.metadata={'batch_id':'test','pages_per_paper':1,'frame_revision':'r1','source_pdf_sha256':'a'*64,
            'reference_student_id':'p1','reviewed':False,'file_sha256':{self.image.name:hashlib.sha256(self.image.read_bytes()).hexdigest()}}
        self.review=self.root/'review.json';self.review.write_text(json.dumps(self.metadata))
        self.plan={'coordinate_space':'pixels','frame_revision':'r1','source_pdf_sha256':'a'*64,'reference_student_id':'p1',
            'reference_reviewed':False,'operations':[{'type':'set','id':'one','regions':[{'page':0,'bbox':[100,50,900,450]}]}]}
    def tearDown(self):self.temp.cleanup()

    def test_image_bound_conversion_preserves_review_and_plan_without_clamping(self):
        original=copy.deepcopy(self.plan);result,images=normalize_pixel_plan(self.plan,self.review,'test')
        self.assertEqual(result['operations'][0]['regions'][0]['bbox'],[.05,.05,.45,.45])
        self.assertFalse(result['reference_reviewed']);self.assertEqual(self.plan,original)
        self.assertEqual(images,[self.image]);paperflow.validate_frame_plan('frames',result)
        with self.assertRaisesRegex(ValueError,'file_path_conflict'):
            paperflow.validate_file_paths(argparse.Namespace(output=self.image),protected_inputs=images)
        self.plan['operations'][0]['regions'][0]['bbox'][2]=2001
        with self.assertRaisesRegex(ValueError,'invalid_pixel_region'):normalize_pixel_plan(self.plan,self.review,'test')

    def test_stale_source_and_changed_review_image_fail_before_dispatch(self):
        for field,value in [('frame_revision','r2'),('source_pdf_sha256','b'*64),('reference_student_id','other')]:
            plan={**self.plan,field:value}
            with self.assertRaisesRegex(ValueError,'pixel_review_source_mismatch'):normalize_pixel_plan(plan,self.review,'test')
        self.image.write_bytes(self.image.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'pixel_review_image_changed'):normalize_pixel_plan(self.plan,self.review,'test')

    def test_pixel_marker_cannot_silently_pass_as_normalized_or_shift(self):
        with self.assertRaisesRegex(ValueError,'pixel_review_required'):paperflow.validate_frame_plan('frames',self.plan)
        plan={**self.plan,'operations':[{'type':'shift','ids':['one'],'dx':1,'dy':1}]}
        with self.assertRaisesRegex(ValueError,'unsupported_pixel_edit'):normalize_pixel_plan(plan,self.review,'test')


if __name__=='__main__':unittest.main()
