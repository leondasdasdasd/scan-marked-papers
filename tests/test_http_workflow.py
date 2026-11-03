"""Real HTTP/CLI round trip with synthetic papers; no browser, login or model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/paperflow.py'


class HttpWorkflowTests(unittest.TestCase):
    def test_emitted_script_and_collect_finish_23_papers_with_six_independent_questions(self):
        batch = {'id': 'test', 'workflow_mode': 'scan', 'pages_per_paper': 1,
            'total_pages': 23, 'name': 'Synthetic exercise', 'name_revision': 0,
            'analysis_confirmation_version': 2,
            'students': [{'id': f'p{i}', 'index': i, 'start': i-1} for i in range(1, 24)]}
        analysis = {'status': 'not_generated', 'source_pdf_sha256': 'a'*64,
            'frame_revision': 'r1', 'catalog_revision': 'c1', 'students': [], 'questions': [],
            'frames': [], 'reference_student_id': None}
        roster = {'revision': 1, 'papers': [dict(s, student_id=str(i))
            for i, s in enumerate(batch['students'], 1)]}
        trace = []
        request_errors = []
        B = '/api/batches/test'
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self):
                route = urlsplit(self.path).path
                raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                body = json.loads(raw) if raw else None
                trace.append((self.command, route, body))
                if raw and (not isinstance(body, dict) or self.headers.get('Content-Type') != 'application/json'):
                    request_errors.append('body is not a JSON object')
                status = 200
                if route == '/api/session':
                    owner.assertEqual(urlsplit(self.path).query, 'refresh_profile=false&include_models=false')
                    result = {'user': {'id': 'teacher1', 'school_id': 'school1', 'identity': 'teacher'}}
                elif route == '/api/classroom/login-check':
                    result = {'云谷会话': '有效且账号一致', '课堂会话': '有效'}
                elif route == B:
                    result = batch
                elif route == B+'/lesson-practice/imports':
                    result = {'items': []}
                elif route == B+'/task-control':
                    result = {}
                elif route == B+'/analysis' and self.command == 'GET':
                    result = analysis.copy()
                    if 'view=catalog' in self.path:
                        result.pop('students', None)
                elif route == B+'/analysis' and self.command == 'POST':
                    if body != {'reference_student_id': 'p1'}:
                        result = {'detail': '标准卷选择格式无效'}
                        status = 422
                    else:
                        analysis.update(status='awaiting_frames', reference_student_id='p1', reference_start=0,
                            frames=[{'id': 'group', 'label': '计算题', 'parent_id': None,
                                'regions': [{'page': 0, 'bbox': [.1, .1, .9, .9]}]}])
                        result = analysis
                elif route == B+'/analysis/frames' and self.command == 'PATCH':
                    owner.assertEqual(body['frame_revision'], analysis['frame_revision'])
                    analysis.update(frames=body['frames'], frame_revision='r2')
                    result = analysis
                elif route == B+'/analysis/frames/confirm':
                    owner.assertEqual(body['frame_revision'], 'r2')
                    analysis.update(status='awaiting_confirmation', questions=[dict(f,
                        conversion_status='converted', content={'elements': [
                            {'type': 'richText', 'content': {'text': f['label'], 'html': '<p>source</p>'}},
                            {'type': 'textResponse'}]}) for f in analysis['frames']])
                    result = analysis
                elif route == B+'/merge-preflight':
                    owner.assertEqual(body['source_ids'], [])
                    result = {'operation_id': 'op1', 'preflight_token': 'op1',
                        'versions': {'test': {'scope': 1}}, 'duplicates': []}
                elif route == B+'/analysis/confirm-and-start':
                    owner.assertEqual(body['questions'], analysis['questions'])
                    owner.assertEqual(body['source_versions'], {'test': {'scope': 1}})
                    owner.assertEqual(body['duplicate_choices'], {})
                    analysis.update(status='completed', students=[dict(s, answers=[
                        {'question_id': q['id'], 'verdict': 'correct'} for q in analysis['questions']])
                        for s in batch['students']])
                    result = {'status': 'accepted', 'operation_id': 'op1'}
                elif route == B+'/roster':
                    result = roster
                elif route == B+'/lesson-practice/config':
                    result = {'config': {'revision': 1, 'selected_paper_ids': None}}
                elif route == B+'/lesson-practice/preflight':
                    result = {'ready': True, 'status': 'awaiting_confirmation', 'issues': [],
                        'counts': {'students': 23, 'skippedPapers': 0, 'gradableQuestions': 6, 'questionResults': 138}}
                else:
                    status = 404
                    result = {'detail': route}
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())

            do_GET = do_POST = do_PATCH = respond

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory() as d:
                directory = Path(d)
                checkpoint = directory/'checkpoint.json'
                def command(*args):
                    result = subprocess.run([sys.executable, str(CLI), '--batch-url',
                        origin+'/exams/test/analysis?class_id=47071', '--checkpoint', str(checkpoint), *args],
                        text=True, capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    return json.loads(result.stdout)

                def step(plan=None, action='run'):
                    path = directory/'plan.json';path.write_text(json.dumps(plan))
                    script = directory/'run.js'
                    emitted = command('--standalone-script','--emit-script', str(script), action, *(['--plan', str(path)] if plan else []))
                    self.assertFalse(emitted['result']['executed'])
                    bootstrap = ('global.location={origin:'+json.dumps(origin)+'};'
                        'const actualFetch=global.fetch;global.fetch=(p,o)=>actualFetch(new URL(p,location.origin),o);'
                        'Promise.resolve(eval(require("fs").readFileSync(0,"utf8")))'
                        '.then(x=>process.stdout.write(JSON.stringify(x))).catch(e=>{console.error(e);process.exitCode=1});')
                    evaluated = subprocess.run(['node', '-e', bootstrap], input=script.read_text(),
                        text=True, capture_output=True, timeout=15)
                    self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
                    raw_result = directory/'browser-result.json';raw_result.write_text(evaluated.stdout)
                    return command('collect', '--result', str(raw_result))

                verified = step(action='access')
                self.assertEqual(verified['result']['outcome'], 'access_verified')
                first = step({'reference_student_id': 'p1'})
                self.assertEqual(first['result']['outcome'], 'needs_frame_review')
                children = [{'id': f'calc{i}', 'label': f'1({i})', 'parent_id': None,
                    'regions': [{'page': 0, 'bbox': [.1, .1+(i-1)*.12, .9, .2+(i-1)*.12]}]}
                    for i in range(1, 7)]
                review = {'source_pdf_sha256': 'a'*64, 'reference_student_id': 'p1',
                    'frame_revision': 'r1', 'reference_reviewed': True, 'scope_reviewed': True,
                    'reviewed_pages': [0], 'expected_leaf_labels': [c['label'] for c in children]}
                second = step({'frames': dict(review, operation_id='frames1',
                    operations=[{'type': 'split', 'id': 'group', 'children': children}])})
                self.assertEqual(second['result']['outcome'], 'needs_catalog_review')
                third = step({'catalog': dict(review, operation_id='catalog1', frame_revision='r2',
                    catalog_revision='c1', catalog_reviewed=True)})
                self.assertTrue(third['result']['ready'])
                self.assertEqual(third['result']['answers'], 138)
                self.assertEqual(third['result']['papers'], 23)
                self.assertEqual(third['result']['leaf_questions'], 6)
                self.assertFalse(third['result']['submitted'])
                self.assertFalse(request_errors)
                self.assertEqual(sum(m=='POST' and p==B+'/analysis' for m,p,b in trace), 1)
                self.assertFalse(any(m=='POST' and p.endswith('/imports') for m,p,b in trace))
                self.assertTrue(all(q['parent_id'] is None for q in analysis['questions']))
                print(json.dumps({'isolated_http_seconds': round(time.monotonic()-started, 3),
                    'agent_boundaries': 3, 'http_requests': len(trace), 'papers': 23,
                    'questions': 6, 'answers': 138, 'model_calls': 0}))
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
