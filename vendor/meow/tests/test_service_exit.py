import asyncio
from pathlib import Path
import sys
import tempfile
import threading
import unittest

import httpx

WORK=next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path.insert(0,str(WORK))
from gpt56_vnext.server import AppState,create_server
from gpt56_vnext.errors import AppError


class ServiceExitTests(unittest.TestCase):
    def test_requires_idle_and_blocks_new_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=AppState(tmp,bundled=False)
            try:
                state.active['fixture']=None
                with self.assertRaisesRegex(AppError,'finish_work_before_exit'):state.call(state.prepare_exit())
                state.active.clear()
                state.store.put_document('schedule','active',{'enabled':True})
                with self.assertRaisesRegex(AppError,'finish_work_before_exit'):state.call(state.prepare_exit())
                state.store.delete_document('schedule','active')
                state.call(state.prepare_exit())
                with self.assertRaisesRegex(AppError,'backend_closing'):state.call(state.start_run('detection',{}))
            finally:state.close()

    def test_authenticated_confirmed_exit_preserves_saved_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            server=create_server(port=0,runs_root=tmp)
            def serve():
                try:server.serve_forever(poll_interval=.01)
                finally:server.server_close()
            thread=threading.Thread(target=serve);thread.start()
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}',trust_env=False,timeout=3) as client:
                    self.assertEqual(client.post('/api/program/exit',json={'confirmed':True}).status_code,403)
                    client.get('/api/bootstrap').raise_for_status()
                    self.assertEqual(client.post('/api/program/exit',json={}).status_code,400)
                    self.assertEqual(client.post('/api/program/exit',json={'confirmed':True}).status_code,200)
                thread.join(3);self.assertFalse(thread.is_alive())
                self.assertTrue((Path(tmp)/'state.sqlite3').is_file())
            finally:
                if thread.is_alive():server.shutdown();thread.join(3)


if __name__=='__main__':unittest.main()
