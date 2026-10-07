"""Build Windows x64 portable ZIPs from an explicitly verified clean source commit."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

TOOLS_ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = '3.13.15'
PYTHON_URL = f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip'
PYTHON_SHA256 = 'd1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode('utf-8') if isinstance(value, str) else value)


def remove_build_directory(path, root):
    path,root=path.resolve(),root.resolve()
    if path==root or not path.is_relative_to(root):raise ValueError('Cleanup escaped the build directory')
    if path.exists():shutil.rmtree(path)


def build(source, output, source_commit):
    if os.name != 'nt' or sys.version_info[:2] != (3, 13):
        raise SystemExit('Build with 64-bit Python 3.13 on Windows')
    import struct
    assert struct.calcsize('P') == 8
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == source_commit
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
    builder = runpy.run_path(str(source / 'scripts/build_release.py'))
    source_files = builder['release_files'](source)
    version = source_files['VERSION'].decode('ascii').strip()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        runtime_zip = work / 'python.zip'
        urllib.request.urlretrieve(PYTHON_URL, runtime_zip)
        assert digest(runtime_zip) == PYTHON_SHA256, 'Official Python checksum mismatch'
        runtime = work / 'python'
        with zipfile.ZipFile(runtime_zip) as archive:
            archive.extractall(runtime)
        # Keep the embedded runtime isolated; explicitly add only its dependencies and app root.
        write(runtime / 'python313._pth', 'python313.zip\n.\nLib/site-packages\n..\nimport site\n')
        wheels = work / 'wheels'
        subprocess.run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:',
                        '--dest', str(wheels), '-r', str(source / 'requirements.txt')], check=True)
        report = work / 'install-report.json'
        site_packages = runtime / 'Lib/site-packages'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--find-links', str(wheels),
                        '--only-binary=:all:', '--no-compile', '--target', str(site_packages),
                        '--report', str(report), '-r', str(source / 'requirements.txt')], check=True)
        # Console entry points contain the CI interpreter path and are not used by the application.
        remove_build_directory(site_packages / 'bin',work)
        for cache in list(runtime.rglob('__pycache__')):
            remove_build_directory(cache,work)
        packages = sorted(({'name': d.metadata['Name'], 'version': d.version}
                           for d in importlib.metadata.distributions(path=[str(site_packages)])), key=lambda p: p['name'].lower())
        manifest = {'source_commit': source_commit, 'builder_commit': os.environ.get('GITHUB_SHA'),
                    'python_version': PYTHON_VERSION, 'python_url': PYTHON_URL,
                    'python_sha256': PYTHON_SHA256, 'platform': 'windows-x64',
                    'packages': packages, 'wheels': {p.name: digest(p) for p in sorted(wheels.glob('*.whl'))}}
        install_report = json.loads(report.read_text(encoding='utf-8'))
        # Strip temporary CI paths; retain the wheel hashes and dependency metadata.
        for item in install_report['install']:
            item['download_info']['url'] = Path(item['download_info']['url']).name
        manifest['installation'] = install_report
        checksums = []
        for locale, language in [('zh-CN', 'CN'), ('en', 'EN')]:
            name = f'meow-llm-detector-v{version}-windows-x64-portable-{locale}'
            folder = work / name
            folder.mkdir()
            for filename, raw in source_files.items():
                write(folder / filename, raw)
            for lang in ('CN', 'EN'):
                shutil.move(folder / f'README_{lang}.md', folder / f'README_SOURCE_{lang}.md')
                write(folder / f'README_{lang}.md', (TOOLS_ROOT / f'docs/WINDOWS_PORTABLE_{lang}.md').read_bytes())
            shutil.copyfile(folder / f'README_{language}.md', folder / 'README.md')
            shutil.copytree(runtime, folder / 'python')
            write(folder / 'locale.json', json.dumps({'locale': locale}) + '\n')
            write(folder / 'PORTABLE_BUILD.json', json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
            missing = ('Portable Python is missing. Extract the entire ZIP again.' if locale == 'en' else '便携 Python 缺失，请重新完整解压 ZIP。')
            start = ('@echo off\nsetlocal\nchcp 65001 >nul\ncd /d "%~dp0"\n'
                     'if not exist "%~dp0python\\python.exe" (\n'
                     f'  echo {missing}\n  pause\n  exit /b 1\n)\n'
                     '"%~dp0python\\python.exe" -I -B -X utf8 "%~dp0launch.py" %*\n'
                     'if errorlevel 1 (\n  pause\n  exit /b 1\n)\n')
            write(folder / 'start.bat', start.replace('\n', '\r\n'))
            content = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
            content = builder['installation_files'](content, version, locale, 'windows-x64-portable')
            target = output / (name + '.zip')
            builder['write_archive'](target, content)
            checksums.append(f'{digest(target)}  {target.name}\n')
            print(f'Built {target.name}: {target.stat().st_size} bytes', flush=True)
        write(output / 'PORTABLE_SHA256SUMS.txt', ''.join(checksums))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-commit', required=True, help='Expected full commit SHA; source tree must be clean')
    args = parser.parse_args()
    build(args.source.resolve(), args.output.resolve(), args.source_commit)
