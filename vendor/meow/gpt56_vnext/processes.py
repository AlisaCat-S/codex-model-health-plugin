"""Own an application's process tree for update rollback (including Windows venv launchers)."""
import os
import signal
import subprocess
import sys
import time


class AppProcess:
    def __init__(self, command, **kwargs):
        self.job = None
        options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
        if os.name=='nt':
            # Gate the real command until the controller belongs to our job. A venv
            # launcher can otherwise spawn its child before AssignProcessToJobObject.
            controller="import subprocess,sys; signal=sys.stdin.buffer.read(1); raise SystemExit(subprocess.call(sys.argv[1:],stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW) if signal==b'1' else 1)"
            command=[getattr(sys,'_base_executable',sys.executable),'-B','-c',controller,*command]
            kwargs['stdin']=subprocess.PIPE
        self.process = subprocess.Popen(command, **kwargs, **options)
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL('kernel32',use_last_error=True)
            self.kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
            self.kernel.CreateJobObjectW.restype=wintypes.HANDLE
            self.kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
            self.kernel.AssignProcessToJobObject.restype=wintypes.BOOL
            self.kernel.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]
            self.kernel.TerminateJobObject.restype=wintypes.BOOL
            self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            self.kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
            self.kernel.QueryInformationJobObject.restype=wintypes.BOOL
            self.job=self.kernel.CreateJobObjectW(None,None)
            if not self.job or not self.kernel.AssignProcessToJobObject(self.job,int(self.process._handle)):
                self.process.terminate();self.process.wait(timeout=10)
                if self.job:self.kernel.CloseHandle(self.job)
                raise OSError('Cannot contain update process')
            try:
                self.process.stdin.write(b'1');self.process.stdin.close()
            except OSError:
                self.stop();self.detach();raise

    def poll(self):return self.process.poll()

    def _signal_posix(self, sig):
        deadline=time.monotonic()+2
        while True:
            try:
                os.killpg(self.process.pid,sig)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                # Darwin can report EPERM for a zombie-only group. Reap our
                # leader and retry briefly; a live leader's denial still fails.
                if self.process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.02)
                    continue
                if sys.platform == 'darwin':
                    # macOS may retain orphan zombies beyond the grace period.
                    # Check only group/state, never ignore denial for a live member.
                    rows = subprocess.check_output(['/bin/ps', '-axo', 'pgid=,stat='], text=True, timeout=2)
                    members = [row.split()[1] for row in rows.splitlines()
                               if len(row.split()) == 2 and row.split()[0] == str(self.process.pid)]
                    if all(state.startswith('Z') for state in members):
                        return False
                if time.monotonic()>=deadline:
                    raise
                time.sleep(.02)

    def stop(self):
        if self.job:
            import ctypes
            from ctypes import wintypes
            class Accounting(ctypes.Structure):
                _fields_=[('times',ctypes.c_longlong*4),('faults',wintypes.DWORD),('total',wintypes.DWORD),('active',wintypes.DWORD),('terminated',wintypes.DWORD)]
            if not self.kernel.TerminateJobObject(self.job,1):raise ctypes.WinError(ctypes.get_last_error())
            # Parent exit does not imply that a venv launcher's child released its files.
            accounting=Accounting();deadline=time.monotonic()+15
            while True:
                if not self.kernel.QueryInformationJobObject(self.job,1,ctypes.byref(accounting),ctypes.sizeof(accounting),None):raise ctypes.WinError(ctypes.get_last_error())
                if not accounting.active:break
                if time.monotonic()>=deadline:raise TimeoutError('Update process tree did not exit')
                time.sleep(.01)
        elif os.name != 'nt':
            # A leader may have exited while its owned descendants still run.
            if self._signal_posix(signal.SIGTERM):
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    self.process.poll()  # Reap our leader, if it exited.
                    if not self._signal_posix(0):break
                    time.sleep(.02)
                else:self._signal_posix(signal.SIGKILL)
        self.process.wait(timeout=15)
        if os.name=='nt':self.process._handle.Close()

    def detach(self):
        # No kill-on-close flag: a successful new application remains running.
        if self.job:
            self.kernel.CloseHandle(self.job);self.job=None


def run_application_command(command, *, timeout, **kwargs):
    child=AppProcess(command, **kwargs)
    try:
        code=child.process.wait(timeout=timeout)
        if code:raise subprocess.CalledProcessError(code,command)
    except BaseException:
        child.stop()
        raise
    finally:
        child.detach()
