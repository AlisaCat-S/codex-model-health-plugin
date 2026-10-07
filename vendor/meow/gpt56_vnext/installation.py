"""Managed version directories and verified archives; never overwrite live code."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import zipfile

from .errors import AppError
from .utils import strict_json_loads
from .processes import run_application_command


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def metadata(root):
    path = root / 'MEOW_INSTALL.json'
    if not path.is_file():
        raise AppError('unmanaged_installation_use_separate_directory')
    value = strict_json_loads(path.read_bytes())
    if value.get('schema') != 1 or value.get('kind') not in ('source','windows-x64-portable'):
        raise AppError('unsupported_installation')
    return value


def verify(root):
    value = metadata(root)
    files = value.get('files')
    if not isinstance(files, dict) or not files:
        raise AppError('installation_manifest_missing')
    for name, expected in files.items():
        path = safe_path(root, name)
        if not path.is_file() or digest(path) != expected:
            raise AppError('modified_installation_use_separate_directory', field=name)
    # Newly added importable code can change behavior without modifying a listed
    # file. Ignore managed data/environments, not additions to application code.
    ignored = {'.venv', '.meow-versions', 'meow_runs', '.git', '__pycache__'}
    executable = {'.py', '.pyw', '.pyc', '.pyo', '.pth', '.pyd', '.so', '.dll'}
    for directory, folders, names in os.walk(root):
        folders[:] = [name for name in folders if name not in ignored]
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() in executable and relative not in files:
                raise AppError('modified_installation_use_separate_directory', field=relative)
    return value


def safe_path(root, name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or any(p in ('.','..') or ':' in p for p in parts):
        raise AppError('unsafe_release_path')
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise AppError('unsafe_release_path')
    return path


def unpack(archive, destination, version, kind):
    if destination.exists():
        raise AppError('update_stage_already_exists')
    with zipfile.ZipFile(archive) as package:
        members = [m for m in package.infolist() if not m.is_dir()]
        if len(members) > 20000 or sum(m.file_size for m in members) > 1024**3:
            raise AppError('release_size_mismatch')
        paths = [PurePosixPath(m.filename) for m in members]
        prefixes = {p.parts[0] for p in paths}
        strip = len(prefixes) == 1 and all(len(p.parts) > 1 for p in paths)
        seen = set()
        planned = []
        for entry in members:
            safe_path(destination, entry.filename)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode): raise AppError('unsafe_release_path')
            name = '/'.join(PurePosixPath(entry.filename).parts[1:]) if strip else entry.filename
            if name.casefold() in seen: raise AppError('duplicate_release_path')
            seen.add(name.casefold()); planned.append((entry, safe_path(destination, name)))
        destination.mkdir(parents=True)
        for entry,path in planned:
            path.parent.mkdir(parents=True,exist_ok=True)
            with package.open(entry) as source, path.open('xb') as target:
                import shutil
                shutil.copyfileobj(source,target)
    info = verify(destination)
    if info['version'] != version or info['kind'] != kind:
        raise AppError('release_installation_mismatch')
    return info


def interpreter(root, kind):
    if kind == 'windows-x64-portable':
        if os.name != 'nt': raise AppError('unsupported_platform')
        return root / 'python/python.exe'
    return root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def prepare_environment(root, kind):
    python = interpreter(root, kind)
    if kind == 'source':
        base_python = getattr(sys, '_base_executable', sys.executable)
        if not python.exists():
            run_application_command([base_python,'-m','venv',str(root/'.venv')],timeout=120)
        run_application_command([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],
                       timeout=600,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not python.is_file(): raise AppError('update_runtime_missing')
    run_application_command([str(python),'-B','-c','from gpt56_vnext.server import create_server'],
                   cwd=root,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if kind == 'source':
        (root/'.venv/meow-requirements.sha256').write_text(digest(root/'requirements.txt'),encoding='ascii')
    return python


def environment_ready(root, kind):
    if not interpreter(root,kind).is_file():return False
    if kind != 'source':return True
    stamp=root/'.venv/meow-requirements.sha256'
    return stamp.is_file() and stamp.read_text(encoding='ascii').strip()==digest(root/'requirements.txt')
