import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
paperflow = importlib.import_module('paperflow')


class OutputTests(unittest.TestCase):
    def test_compact_preserves_decision_but_excludes_recovery_signatures(self):
        full = {'ok': True, 'result': {'outcome': 'needs_frame_review',
            'review': {'frame_revision': 'current', 'frames': [{'id': 'one'}], 'questions': []}},
            'checkpoint': {'frame_receipt': {'frames_signature': 'private geometry' * 1000}},
            'calls': [{'status': 200, 'ms': 10}], 'wall_seconds': 1}
        compact = paperflow.compact(full)
        self.assertEqual(compact['result']['review']['frame_count'], 1)
        self.assertEqual(compact['result']['review']['frame_revision'], 'current')
        self.assertNotIn('checkpoint', compact)
        self.assertNotIn('calls', compact)
        self.assertNotIn('private geometry', json.dumps(compact))
        self.assertEqual(len(full['result']['review']['frames']), 1)

    def test_follow_returns_to_agent_only_at_review_boundary_and_keeps_checkpoint(self):
        samples = [
            {'ok': True, 'result': {'outcome': 'waiting'}, 'checkpoint': {'step': 1}, 'calls': [{'status': 200, 'ms': 1}]},
            {'ok': True, 'result': {'outcome': 'waiting'}, 'checkpoint': {'step': 2}, 'calls': [{'status': 200, 'ms': 1}]},
            {'ok': True, 'result': {'outcome': 'needs_frame_review'}, 'checkpoint': {'step': 3}, 'calls': [{'status': 200, 'ms': 1}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            args = ['paperflow', '--base-url', 'https://example.test', '--batch-id', 'test',
                '--browser-session', 'test', '--output', str(output), 'run', '--follow']
            stdout = io.StringIO()
            with patch.object(sys, 'argv', args), patch.object(paperflow, 'execute', side_effect=samples) as execute:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(paperflow.main(), 0)
            self.assertEqual(execute.call_count, 3)
            self.assertEqual(execute.call_args_list[1].args[3], {'step': 1})
            self.assertEqual(json.loads(stdout.getvalue())['http']['count'], 3)
            self.assertEqual(json.loads(output.read_text())['checkpoint'], {'step': 3})
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_follow_passes_only_remaining_budget_to_observation(self):
        clock=[0.0];seen=[]
        def execute(args,action,plan=None,checkpoint=None):
            seen.append((args.timeout,getattr(args,'observe_analysis',False)))
            clock[0]+=2
            return {'ok':True,'result':{'outcome':'waiting','analysis_status':'generating'}} if len(seen)==1 else {'ok':True,'result':{'outcome':'needs_frame_review'}}
        args=['paperflow','--base-url','https://example.test','--batch-id','test','--browser-session','test','run','--follow','--max-seconds','3']
        with patch.object(sys,'argv',args),patch.object(paperflow,'execute',side_effect=execute),patch.object(paperflow.time,'monotonic',side_effect=lambda:clock[0]):
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):self.assertEqual(paperflow.main(),0)
        self.assertEqual(seen,[(3,False),(1,True)])

    def test_follow_stops_on_blocked_result_without_retrying_check(self):
        args = ['paperflow', '--base-url', 'https://example.test', '--batch-id', 'test',
            '--browser-session', 'test', 'run', '--follow']
        with patch.object(sys, 'argv', args), patch.object(paperflow, 'execute', return_value={
            'ok': True, 'result': {'outcome': 'coverage_gap', 'ready': False}}) as execute:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(paperflow.main(), 0)
        self.assertEqual(execute.call_count, 1)


if __name__ == '__main__':
    unittest.main()
