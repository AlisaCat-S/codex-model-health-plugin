"""Source/portable launcher shared by official distributions."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser

from .installation import interpreter, metadata, prepare_environment, environment_ready
from .utils import strict_json_loads


def migrate_data(source, destination):
    import shutil
    import sqlite3
    from .directory_lock import exclusive_directory
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not (source/'state.sqlite3').is_file() and (source/'meow_runs/state.sqlite3').is_file():
        source=source/'meow_runs'
    if not (source/'state.sqlite3').is_file() or destination.exists():
        raise SystemExit('Migration requires an inactive meow data directory and a new destination')
    with exclusive_directory(source):
        destination.mkdir(parents=True)
        with closing(sqlite3.connect((source/'state.sqlite3').as_uri()+'?mode=ro',uri=True)) as old, closing(sqlite3.connect(destination/'state.sqlite3')) as new:
            old.backup(new)
        if (source/'benchmarks').is_dir():
            shutil.copytree(source/'benchmarks',destination/'benchmarks',symlinks=True)


def launch(root, argv=None):
    root=Path(root).resolve()
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-root',type=Path)
    parser.add_argument('--migrate-from',type=Path,help='Copy an inactive old installation/data directory; do not modify it')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args(argv)
    current=root
    pointer=root/'.meow-current.json'
    if pointer.exists():
        current=Path(strict_json_loads(pointer.read_bytes())['path']).resolve()
        if current != root and not current.is_relative_to(root/'.meow-versions'):
            raise SystemExit('Invalid application version directory')
    info=metadata(current) if (current/'MEOW_INSTALL.json').exists() else {'kind':'source','locale':'zh-CN'}
    python=interpreter(current,info['kind'])
    if not environment_ready(current,info['kind']):
        print('Preparing private dependencies / 正在准备本目录依赖…',flush=True)
        python=prepare_environment(current,info['kind'])
    locale=info['locale'];data=(args.data_root or root/'meow_runs').resolve()
    if args.migrate_from:migrate_data(args.migrate_from,data)
    env={**os.environ,'MEOW_LAUNCH_ROOT':str(root)}
    timer=None
    if not args.no_browser:
        timer=threading.Timer(2,webbrowser.open,args=(f'http://127.0.0.1:{args.port}/?lang={locale}',))
        timer.daemon=True;timer.start()
    try:
        return subprocess.call([str(python),'-X','utf8','-B','-m','gpt56_vnext','--port',str(args.port),
                                '--data-root',str(data),'--locale',locale],cwd=current,env=env)
    except KeyboardInterrupt:return 0
    finally:
        if timer:timer.cancel()
