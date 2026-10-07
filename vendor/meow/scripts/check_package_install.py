"""Real packaged application startup, independent environments and rollback.

Only the download transport is excluded. No provider calls, real credentials,
or user installation/data directories are used. Keep logs for inspection.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path.insert(0, str(ROOT))
from gpt56_vnext.installation import unpack, prepare_environment, verify
from gpt56_vnext.processes import AppProcess
from gpt56_vnext.update_runtime import handoff, wait_health, port_open
from gpt56_vnext.store import SQLiteStateStore


def stop(child, port):
    child.stop()
    child.detach()
    deadline = time.monotonic() + 3
    while port_open(port) and time.monotonic() < deadline:
        time.sleep(.02)
    assert not port_open(port)


def records(data):
    with closing(sqlite3.connect(data / 'state.sqlite3')) as db:
        return db.execute('SELECT session_id,report_json FROM sessions ORDER BY session_id').fetchall()


def fixture_version(root, version, fail=False):
    init = root / 'gpt56_vnext/__init__.py'
    init.write_text(init.read_text(encoding='utf-8').replace('__version__ = "4.5.4"',
                    '__version__ = ' + json.dumps(version)), encoding='utf-8')
    (root / 'VERSION').write_text(version + '\n', encoding='ascii')
    if fail:
        (root / 'gpt56_vnext/__main__.py').write_text('raise SystemExit(78)\n', encoding='ascii')
    path = root / 'MEOW_INSTALL.json'
    metadata = json.loads(path.read_text())
    metadata['version'] = version
    metadata['files'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in metadata['files']}
    path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    verify(root)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--kind', choices=['source', 'windows-x64-portable'], default='source')
    parser.add_argument('--output', type=Path, default=ROOT/'acceptance-results')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    test = Path(tempfile.mkdtemp(prefix='发行验收 with spaces-', dir=output)).resolve()
    original, data = test / 'original', test / 'data'
    info = unpack(args.archive.resolve(), original, '4.5.4', args.kind)
    print('Preparing real independent environment:', original, flush=True)
    python = prepare_environment(original, args.kind)
    verify(original)
    data.mkdir()
    store = SQLiteStateStore(data / 'state.sqlite3')
    store.create_session(session_id='historical-fixture', kind='detection', status='complete', config={},
                         config_hash='synthetic', official=False)
    store.save_report('historical-fixture', {'historical': 'byte-preserved', 'version': '4.5.2'})
    store.put_document('fixture', 'vault-reference', {'reference': 'opaque-synthetic-reference'})
    store.close()
    before = records(data)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    report = {'kind': args.kind, 'root': str(test), 'archive_sha256': hashlib.sha256(args.archive.read_bytes()).hexdigest(),
              'platform': sys.platform, 'locale': info['locale'], 'provider_calls': 0, 'checks': []}
    child = None
    with (test / 'launcher.log').open('wb') as log:
        try:
            command = [str(python), '-X', 'utf8', '-B', str(original / 'launch.py'), '--no-browser',
                       '--port', str(port), '--data-root', str(data)]
            child = AppProcess(command, cwd=test, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            assert wait_health(port, '4.5.4', child, timeout=90), 'Packaged launcher failed; inspect launcher.log'
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for path in ('/', '/assets/ui.js', '/api/bootstrap'):
                with opener.open(f'http://127.0.0.1:{port}' + path, timeout=5) as response:
                    assert response.status == 200
            report['checks'].append('actual_launcher_unicode_space_path_and_resources')
        finally:
            if child:
                stop(child, port)
                child = None
    assert records(data) == before
    for fail in (False, True):
        version = '99.0.2' if fail else '99.0.1'  # Synthetic upgrade versions, never published.
        stage = original / '.meow-versions' / version
        unpack(args.archive.resolve(), stage, '4.5.4', args.kind)
        fixture_version(stage, version, fail)
        print('Preparing', 'rollback failure fixture' if fail else 'real-code upgrade fixture', flush=True)
        prepare_environment(stage, args.kind)
        control = test / ('rollback' if fail else 'upgrade')
        control.mkdir()
        job = {'prepared': str(stage), 'previous': str(original), 'previous_version': '4.5.4',
               'version': version, 'data': str(data), 'launch_root': str(original), 'kind': args.kind,
               'locale': info['locale'], 'port': port}
        # Start each check from the original package; preserve the first result separately.
        pointer = original / '.meow-current.json'
        pointer.write_text(json.dumps({'version': '4.5.4', 'path': str(original)}), encoding='utf-8')
        job_path = control / 'job.json'
        job_path.write_text(json.dumps(job), encoding='utf-8')
        try:
            child = handoff(job_path, keep_process_handle=True)
            status = json.loads((control / 'status.json').read_text())
            assert status['stage'] == ('failed' if fail else 'complete'), status
            assert wait_health(port, '4.5.4' if fail else version, child)
            assert records(data) == before
            with closing(sqlite3.connect(data / 'state.sqlite3')) as db:
                ref = db.execute("SELECT body_json FROM documents WHERE kind='fixture' AND id='vault-reference'").fetchone()
                assert json.loads(ref[0])['reference'] == 'opaque-synthetic-reference'
            report['checks'].append('real_failed_start_backup_restore_restart' if fail else 'real_code_version_handoff')
        finally:
            if child:
                stop(child, port)
                child = None
    report['checks'].extend(['historical_report_bytes_preserved', 'opaque_credential_reference_preserved', 'owned_ports_closed'])
    (test / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
