"""Convert explicitly selected raw review-image pixels without guessing geometry."""
import copy
import hashlib
import json
import math
from pathlib import Path
import struct


def normalize_pixel_plan(plan,review_path,batch_id):
    review_path=Path(review_path);review=json.loads(review_path.read_text())
    if not isinstance(plan,dict) or plan.get('coordinate_space')!='pixels':raise ValueError('pixel_coordinate_space_required')
    if review.get('batch_id')!=batch_id or any(not plan.get(k) or plan[k]!=review.get(k)
        for k in ('frame_revision','source_pdf_sha256','reference_student_id')):
        raise ValueError('pixel_review_source_mismatch')
    result=copy.deepcopy(plan);result.pop('coordinate_space');sizes={}
    def regions(values):
        if not isinstance(values,list):raise ValueError('invalid_region')
        for region in values:
            page=region.get('page')
            if type(page) is not int or page<0 or page>=review.get('pages_per_paper',0):raise ValueError('invalid_region')
            if page not in sizes:
                name=f'raw-page-{page+1}.png';path=review_path.parent/name
                if path.is_symlink():raise ValueError('pixel_review_image_changed')
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=review.get('file_sha256',{}).get(name):raise ValueError('pixel_review_image_changed')
                if raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR' or len(raw)<24:raise ValueError('pixel_review_image_invalid')
                sizes[page]=struct.unpack('>II',raw[16:24])
            width,height=sizes[page];box=region.get('bbox')
            if (not width or not height or not isinstance(box,list) or len(box)!=4 or
                any(type(v) not in (int,float) or not math.isfinite(v) for v in box) or
                not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height):raise ValueError('invalid_pixel_region')
            region['bbox']=[box[0]/width,box[1]/height,box[2]/width,box[3]/height]
    for op in result.get('operations',[]):
        if op.get('type')=='set':
            if 'regions' in op:regions(op['regions'])
        elif op.get('type') in ('split','promote_children','replace_page'):
            for frame in op.get('frames' if op['type']=='replace_page' else 'children',[]):regions(frame.get('regions'))
        else:raise ValueError('unsupported_pixel_edit')
    return result,[review_path.parent/f'raw-page-{page+1}.png' for page in sizes]
