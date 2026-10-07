"""Real owned-process tree cleanup, including a leader that already exited."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'gpt56_vnext').is_dir())
sys.path.insert(0,str(ROOT))
from gpt56_vnext.processes import AppProcess
from gpt56_vnext.update_runtime import port_open


def main():
    results=[]
    for ignore_term in (False,True):
        with tempfile.TemporaryDirectory(prefix='meow owned tree ') as tmp:
            root=Path(tmp)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            ready=root/'ready'
            server=root/'server.py'
            server.write_text('import socket,signal,time\nfrom pathlib import Path\n'
                +('signal.signal(signal.SIGTERM,signal.SIG_IGN)\n' if ignore_term and os.name!='nt' else '')
                +f's=socket.socket();s.bind(("127.0.0.1",{port}));s.listen()\n'
                +f'Path({str(ready)!r}).write_text("ready")\n'
                +'while True:time.sleep(.1)\n',encoding='utf-8')
            # The group leader intentionally exits, leaving its descendant alive.
            command=[sys.executable,'-B','-c',
                     'import subprocess,sys;subprocess.Popen([sys.executable,"-B",sys.argv[1]],stdin=subprocess.DEVNULL)',str(server)]
            child=AppProcess(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+10
                while not ready.exists() and time.monotonic()<deadline:time.sleep(.02)
                assert ready.exists() and port_open(port),'Descendant did not start'
                child.process.wait(timeout=10)
                assert child.poll() is not None and port_open(port),'Fixture must retain a live descendant'
                child.stop()
                deadline=time.monotonic()+3
                while port_open(port) and time.monotonic()<deadline:time.sleep(.02)
                assert not port_open(port),'Owned descendant still holds port'
                results.append({'ignore_term':ignore_term,'leader_exited':True,'descendant_port_closed':True})
            finally:
                child.stop();child.detach()
    print(json.dumps({'platform':sys.platform,'checks':results}))


if __name__=='__main__':main()
