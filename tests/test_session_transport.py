"""Verify CLI routing and transport failure boundaries without a user browser."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import paperflow
import paperflow_base
import paperflow_session


class SessionTransportTests(unittest.TestCase):
    def args(self, **values):
        return argparse.Namespace(base_url='https://piyue.yungu.org', browser_session='task',
                                  timeout=45, browser_backend='playwright', **values)

    def test_existing_isolated_state_wins_over_another_browser_backend(self):
        args = self.args()
        args.browser_backend = 'agent-browser'
        with patch.object(paperflow_session, 'available', return_value=True), \
             patch.object(paperflow_session, 'invoke', return_value={'ok': True, 'result': {'isolated': True}}) as invoke, \
             patch.object(paperflow_base.subprocess, 'run') as other:
            result = paperflow_base.browser(args, 'unused', '(async()=>true)()')
        self.assertTrue(result['result']['isolated'])
        invoke.assert_called_once_with(args, 'execute', '(async()=>true)()')
        other.assert_not_called()

    def test_expired_isolated_transport_never_silently_falls_back_or_replays(self):
        args = self.args()
        with patch.object(paperflow_session, 'available', return_value=True), \
             patch.object(paperflow_session, 'invoke', return_value={'ok': False, 'error': {'code': 'isolated_session_expired'}}) as invoke, \
             patch.object(paperflow_base.subprocess, 'run') as other:
            result = paperflow_base.browser(args, 'unused', 'writeOperation()')
        self.assertEqual(result['error']['code'], 'isolated_session_expired')
        self.assertEqual(invoke.call_count, 1)
        other.assert_not_called()

    def test_session_commands_work_without_a_batch_and_do_not_run_business(self):
        for action in ('session-connect', 'session-status', 'session-close'):
            with self.subTest(action=action):
                output = io.StringIO()
                argv = ['paperflow.py', '--browser-session', 'task', action]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output), \
                     patch.object(paperflow_session, 'invoke', return_value={'ok': True, 'result': {'outcome': action}}) as invoke, \
                     patch.object(paperflow, 'execute') as business:
                    self.assertEqual(paperflow.main(), 0)
                self.assertEqual(json.loads(output.getvalue())['result']['outcome'], action)
                self.assertEqual(invoke.call_args.args[1], action.removeprefix('session-'))
                business.assert_not_called()

    def test_missing_runtime_reports_a_capability_gap_without_installing_anything(self):
        with patch.object(paperflow_session.shutil, 'which', return_value=None), \
             patch.object(paperflow_session.subprocess, 'run') as run:
            result = paperflow_session.invoke(self.args(), 'connect')
        self.assertEqual(result['error']['code'], 'isolated_browser_requires_existing_node')
        run.assert_not_called()

    def test_uncertain_execution_stops_once_and_requests_readback(self):
        with patch.object(paperflow_session.shutil, 'which', return_value='/existing/node'), \
             patch.object(paperflow_session.subprocess, 'run', side_effect=subprocess.TimeoutExpired('node', 10)) as run:
            result = paperflow_session.invoke(self.args(), 'execute', 'writeOperation()')
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result['error']['next_action'], 'read_state_before_retry')
        self.assertEqual(result['error']['code'], 'isolated_transport_uncertain')


if __name__ == '__main__':
    unittest.main()
