"""Short-lived update handoff; only starts/stops its own new child process."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
import urllib.request

from .installation import interpreter
from .processes import AppProcess
from .utils import atomic_write_json, strict_json_loads


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.3): return True
    except OSError: return False


def wait_health(port, version, child, timeout=60):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    end = time.monotonic()+timeout
    while time.monotonic()<end:
        if child.poll() is not None: return False
        try:
            with opener.open(f'http://127.0.0.1:{port}/api/bootstrap',timeout=1) as response:
                if json.load(response).get('version')==version:return True
        except (OSError,ValueError):pass
        time.sleep(.3)
    return False


def handoff(job_path, *, keep_process_handle=False):
    job = strict_json_loads(job_path.read_bytes())
    control = job_path.parent
    status_path = control/'status.json'
    stage = Path(job['prepared']); old = Path(job['previous']); data = Path(job['data'])
    launch_root = Path(job['launch_root'])
    pointer = launch_root/'.meow-current.json'
    previous_pointer = pointer.read_bytes() if pointer.exists() else None
    def status(phase, **extra): atomic_write_json(status_path, {'stage':phase,**extra})
    deadline=time.monotonic()+60
    while port_open(job['port']):
        if time.monotonic()>deadline:
            status('failed',message='Original process did not exit; no files switched.');return
        time.sleep(.3)
    database=data/'state.sqlite3';backup=control/'pre-update.sqlite3'
    if database.exists():
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(backup)) as target:source.backup(target)
    def spawn(root):
        python=interpreter(root,job['kind'])
        env={**os.environ,'MEOW_LAUNCH_ROOT':str(launch_root),'MEOW_UPDATE_CONTROL':str(control)}
        return AppProcess([str(python),'-X','utf8','-B','-m','gpt56_vnext','--port',str(job['port']),
                                 '--data-root',str(data),'--locale',job['locale']],cwd=root,env=env,
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    child=None
    try:
        status('starting')
        atomic_write_json(pointer, {'version':job['version'],'path':str(stage)})
        child=spawn(stage)
        if not wait_health(job['port'],job['version'],child):raise RuntimeError('New version failed health check')
        status('complete',version=job['version'],pid=child.process.pid)
    except Exception:
        if child:
            child.stop();child.detach()
        if backup.exists():
            with closing(sqlite3.connect(backup)) as source, closing(sqlite3.connect(database)) as target:source.backup(target)
        if previous_pointer is not None:
            # Atomic JSON replacement, never a shell-built filesystem operation.
            atomic_write_json(pointer,strict_json_loads(previous_pointer))
        else:
            atomic_write_json(pointer,{'version':job['previous_version'],'path':str(old)})
        child=spawn(old)
        restored=wait_health(job['port'],job['previous_version'],child)
        status('failed',message='New version failed; previous version restored.' if restored else 'Previous code restored, but application did not restart. Start the original launcher.',pid=child.process.pid)
    if child and not keep_process_handle:child.detach()
    return child


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True)
    handoff(parser.parse_args().job)
