"""Real child-process startup/rollback using synthetic localhost-only applications."""
import json
from contextlib import closing
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

WORK=next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path.insert(0,str(WORK))
from gpt56_vnext import update_runtime
from gpt56_vnext.managed_launcher import migrate_data
from gpt56_vnext.updates import release_info
from gpt56_vnext.processes import AppProcess


def fixture_process(command, **kwargs):
    # Embedded Python ignores cwd for module lookup. Explicitly load our synthetic
    # application; real packaged-application handoff is tested separately.
    position=command.index('-m')
    assert command[position+1]=='gpt56_vnext'
    bootstrap="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('gpt56_vnext',run_name='__main__')"
    command=[*command[:position],'-c',bootstrap,str(kwargs['cwd']),*command[position+2:]]
    return AppProcess(command,**kwargs)


class UpdateHandoffTests(unittest.TestCase):
    def test_real_start_and_failed_start_roll_back(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory(prefix='meow update ') as tmp:
                root=Path(tmp);old=root/'old';new=root/'.meow-versions/new';data=root/'data';control=root/'control'
                for p in (old,new,data,control):p.mkdir(parents=True)
                for path,version in ((old,'4.5.3'),(new,'4.5.4')):
                    package=path/'gpt56_vnext';package.mkdir();(package/'__init__.py').write_text('')
                    code="""import argparse,json
from http.server import BaseHTTPRequestHandler,HTTPServer
p=argparse.ArgumentParser();p.add_argument('--port',type=int);p.add_argument('--data-root');p.add_argument('--locale');args=p.parse_args()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  body=json.dumps({'version':VERSION}).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
HTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
""".replace('VERSION',repr(version))
                    (package/'__main__.py').write_text('raise SystemExit(3)' if fail and path==new else code)
                with closing(sqlite3.connect(data/'state.sqlite3')) as db, db:
                    db.execute('CREATE TABLE reports(body TEXT)');db.execute("INSERT INTO reports VALUES ('historical fixture')")
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                job={'prepared':str(new),'previous':str(old),'previous_version':'4.5.3','version':'4.5.4',
                     'data':str(data),'launch_root':str(root),'kind':'source','locale':'en','port':port}
                path=control/'job.json';path.write_text(json.dumps(job))
                child=None
                try:
                    with patch.object(update_runtime,'interpreter',return_value=Path(sys.executable)), patch.object(update_runtime,'AppProcess',side_effect=fixture_process):
                        child=update_runtime.handoff(path,keep_process_handle=True)
                    status=json.loads((control/'status.json').read_text())
                    self.assertEqual(status['stage'],'failed' if fail else 'complete')
                    pointer=json.loads((root/'.meow-current.json').read_text())
                    self.assertEqual(pointer['path'],str(old if fail else new))
                    with closing(sqlite3.connect(data/'state.sqlite3')) as db:
                        self.assertEqual(db.execute('SELECT body FROM reports').fetchone()[0],'historical fixture')
                    self.assertTrue((control/'pre-update.sqlite3').exists())
                finally:
                    if child:
                        child.stop();child.detach()
                        self.assertIsNotNone(child.poll())
                        # Windows can briefly accept a connect after the owning
                        # process has exited. Check eventual closure, not one SYN.
                        deadline=time.monotonic()+2
                        while update_runtime.port_open(port) and time.monotonic()<deadline:
                            time.sleep(.01)
                        self.assertFalse(update_runtime.port_open(port))

    def test_migrate_keeps_old_database_and_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old';old.mkdir();new=root/'new'
            with closing(sqlite3.connect(old/'state.sqlite3')) as db, db:
                db.execute('CREATE TABLE fixture(ref TEXT)');db.execute("INSERT INTO fixture VALUES ('opaque-vault-reference')")
            before=(old/'state.sqlite3').read_bytes()
            migrate_data(old,new)
            self.assertEqual((old/'state.sqlite3').read_bytes(),before)
            with closing(sqlite3.connect(new/'state.sqlite3')) as db:self.assertEqual(db.execute('SELECT ref FROM fixture').fetchone()[0],'opaque-vault-reference')

    def test_correct_portable_and_source_asset(self):
        import hashlib
        release={'tag_name':'v4.6.0','assets':[]}
        for kind in ('','windows-x64-portable-'):
            name=f'meow-llm-detector-v4.6.0-{kind}en.zip'
            release['assets'].append({'name':name,'size':4,'digest':'sha256:'+hashlib.sha256(b'test').hexdigest(),
                'browser_download_url':'https://github.com/chen-006/meow-llm-detector/releases/download/v4.6.0/'+name})
        self.assertIn('portable',release_info(release,'en','windows-x64-portable')['download']['name'])
        self.assertNotIn('portable',release_info(release,'en','source')['download']['name'])


if __name__=='__main__':unittest.main()
