"""Current-version metadata regression, promoted from v4.5.2."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

WORK = next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path[:0] = [str(WORK), str(WORK / 'versions/v4.5.1/tests')]
from test_benchmarks import fixture
from test_execution import EchoModel, SECRET
from test_audit_regressions import FakeVault, one_job_package, BASE
from gpt56_vnext import __version__
from gpt56_vnext.benchmark import build_package
from gpt56_vnext.detector import DetectorSession
from gpt56_vnext.errors import AppError, RequestError
from gpt56_vnext.server import AppState
from gpt56_vnext.store import SQLiteStateStore


class MetadataTests(unittest.TestCase):
    def test_schedule_preserves_group_and_rejects_secret_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            app = AppState(folder, bundled=False)
            app.presets.vault = FakeVault()
            async def no_calls(_body):
                return 'synthetic-run'
            app.schedule.launch = no_calls
            try:
                package = one_job_package()
                app.catalog.install_local(package)
                preset = app.presets.save({'name': 'fake', 'mode': 'gpt', 'base_url': BASE, 'model': 'a'}, SECRET)
                detection = {'endpoint_id': preset['id'], 'package_id': package['id'],
                             'package_version': package['version'], 'claimed_model': 'a', 'site_group': '组 A'}
                app.call(app.start_schedule({'detection': detection, 'round_limit': 1}))
                app.call(asyncio.wait_for(app.schedule.task, 3))
                previous = app.store.document('schedule', 'active')
                self.assertEqual(previous['detection']['site_group'], '组 A')
                with self.assertRaises((AppError, RequestError)):
                    app.call(app.start_schedule({'detection': {**detection, 'site_group': SECRET}, 'round_limit': 1}))
                self.assertEqual(app.store.document('schedule', 'active'), previous)
            finally:
                app.close()

    def test_new_version_and_group_leave_old_report_frozen(self):
        package = build_package(*fixture())
        with tempfile.TemporaryDirectory() as folder:
            app = AppState(folder, bundled=False)
            try:
                config = {'base_url': 'https://fixture.invalid/v1', 'claimed_model': 'a', 'sample_ratio': .6}
                old = DetectorSession(app.store, 'old', package, config, SECRET, transport=EchoModel())
                app.store.save_report('old', old.report())
                original, frozen = app.store.report('old'), app.store.session('old')['config']
                async def start():
                    identity = await app.start_run('detection', {**config, 'key': SECRET, 'site_group': '  便宜组  ',
                        'package_id': package['id'], 'package_version': package['version']})
                    await app.active[identity][1]
                    return identity
                local = [{'id': package['id'], 'version': package['version'], 'publisher': 'local'}]
                with patch.object(app.catalog, 'get', return_value=package), patch.object(app.catalog, 'local', return_value=local), patch('gpt56_vnext.server.AsyncTransport', return_value=EchoModel()):
                    identity = app.call(start())
                report = app.store.report(identity)
                self.assertEqual((report['site_group'], report['version']), ('便宜组', __version__))
                self.assertEqual(next(r for r in app.store.session_summaries() if r['session_id'] == identity)['site_group'], '便宜组')
                self.assertEqual(app.store.report('old'), original)
                self.assertEqual(app.store.session('old')['config'], frozen)
            finally:
                app.close()

    def test_invalid_group_and_secret_are_not_saved(self):
        package = build_package(*fixture())
        with tempfile.TemporaryDirectory() as folder, SQLiteStateStore(Path(folder) / 'db') as store:
            for group in (SECRET, 'x' * 81, 'a\nb', '\x00', None, 7):
                with self.assertRaises((AppError, RequestError)):
                    DetectorSession(store, 'bad', package, {'base_url': 'https://fixture.invalid/v1',
                        'claimed_model': 'a', 'site_group': group}, SECRET, transport=EchoModel())
            self.assertEqual(store.session_summaries(), [])
