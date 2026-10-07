import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

WORK = next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path.insert(0, str(WORK))
from gpt56_vnext.errors import AppError
from gpt56_vnext.installation import verify
from gpt56_vnext.protocol import parse_stream, normalize_usage
from gpt56_vnext.security import SecretGuard
from gpt56_vnext.transport import AsyncTransport
from gpt56_vnext import processes


class AuditRepairTests(unittest.TestCase):
    def test_posix_zombie_denial_is_reaped_but_live_denial_is_not_hidden(self):
        child=processes.AppProcess.__new__(processes.AppProcess)
        child.process=Mock(pid=123456)
        child.process.poll.return_value=0
        stop=Mock(side_effect=[PermissionError(),ProcessLookupError()])
        with patch.object(processes,'os',SimpleNamespace(name='posix',killpg=stop)), patch.object(processes.sys,'platform','linux'):
            self.assertFalse(child._signal_posix(0))
        self.assertEqual(stop.call_count,2)
        child.process.poll.return_value=None
        with patch.object(processes,'os',SimpleNamespace(name='posix',killpg=Mock(side_effect=PermissionError()))):
            with self.assertRaises(PermissionError):child._signal_posix(0)

    def test_darwin_only_zombies_are_not_running(self):
        child=processes.AppProcess.__new__(processes.AppProcess)
        child.process=Mock(pid=123456)
        child.process.poll.return_value=0
        with patch.object(processes.sys,'platform','darwin'), patch.object(processes,'os',SimpleNamespace(killpg=Mock(side_effect=PermissionError()))), patch.object(processes.subprocess,'check_output',return_value='123456 Z\n99 S\n'):
            self.assertFalse(child._signal_posix(0))
        with patch.object(processes.sys,'platform','darwin'), patch.object(processes,'os',SimpleNamespace(killpg=Mock(side_effect=PermissionError()))), patch.object(processes.subprocess,'check_output',return_value='123456 S\n'), patch.object(processes.time,'monotonic',side_effect=[0,3]):
            with self.assertRaises(PermissionError):child._signal_posix(0)

    def test_added_importable_code_blocks_update_but_data_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            content = b'# source\n'
            (root / 'app.py').write_bytes(content)
            value = {'schema': 1, 'kind': 'source', 'version': '4.5.3',
                     'files': {'app.py': hashlib.sha256(content).hexdigest()}}
            (root / 'MEOW_INSTALL.json').write_text(json.dumps(value))
            (root / 'meow_runs').mkdir()
            (root / 'meow_runs/export.py').write_text('# user data; retained independently\n')
            verify(root)
            (root / 'httpx.py').write_text('# user added code\n')
            with self.assertRaisesRegex(AppError, 'modified_installation'):
                verify(root)

    def test_usage_errors_do_not_discard_complete_answer(self):
        event = {'type': 'response.completed', 'response': {'id': 'fixture', 'status': 'completed',
                 'usage': {'cost': 'unknown', 'output_tokens': '1'},
                 'output': [{'content': [{'type': 'output_text', 'text': '47'}]}]}}
        result = parse_stream('data: ' + json.dumps(event) + '\n\n', 'gpt', SecretGuard())
        self.assertEqual(result['answer'], '47')
        self.assertEqual(result['usage']['output_tokens'], 1)
        self.assertIsNone(result['usage']['cost'])
        self.assertIn('invalid_cost', result['usage']['warnings'])
        self.assertIsNone(normalize_usage({'cost': float('inf')})['cost'])

    def test_transport_close_releases_secret_reference_even_on_failure(self):
        transport = AsyncTransport(['synthetic-secret'])
        class Broken:
            async def aclose(self):
                raise RuntimeError('fixture close failure')
        transport._clients['fixture'] = Broken()
        with self.assertRaises(RuntimeError):
            asyncio.run(transport.close())
        self.assertEqual(transport.guard._values, ())

    def test_non_object_usage_does_not_discard_chat_or_claude_answer(self):
        cases = {
            'chat': [{'choices': [{'index': 0, 'delta': {'content': '47'},
                                   'finish_reason': 'stop'}], 'usage': 'unavailable'}],
            'claude': [{'type': 'message_start', 'message': {'usage': 'unavailable'}},
                       {'type': 'content_block_start', 'index': 0,
                        'content_block': {'type': 'text', 'text': '47'}},
                       {'type': 'content_block_stop', 'index': 0},
                       {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'},
                        'usage': {'output_tokens': 1}}, {'type': 'message_stop'}],
        }
        for mode, events in cases.items():
            with self.subTest(mode=mode):
                body = ''.join('data: ' + json.dumps(e) + '\n\n' for e in events) + 'data: [DONE]\n\n'
                result = parse_stream(body, mode, SecretGuard())
                self.assertEqual(result['answer'], '47')
                self.assertIsNone(result['usage']['cost'])
                self.assertIn('invalid_usage', result['usage']['warnings'])

    def test_posix_group_stopped_when_leader_already_exited(self):
        child = processes.AppProcess.__new__(processes.AppProcess)
        child.job, child.process = None, Mock(pid=123456)
        child.process.poll.return_value = 0
        stop = Mock(side_effect=[None,ProcessLookupError()])
        with patch.object(processes, 'os', SimpleNamespace(name='posix', killpg=stop)):
            child.stop()
        self.assertEqual(stop.call_args_list[0].args,(123456,processes.signal.SIGTERM))
        self.assertEqual(stop.call_args_list[1].args,(123456,0))
