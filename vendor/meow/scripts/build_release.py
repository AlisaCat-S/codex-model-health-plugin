"""Deterministic, source-only bilingual ZIP builder; no private-directory fallback."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ['README.md', 'README_CN.md', 'README_EN.md', 'TECHNICAL_REPORT_CN.md', 'TECHNICAL_REPORT_EN.md',
              'LICENSE', 'THIRD_PARTY_NOTICES.md', 'VERSION', 'requirements.txt', 'launch.py', 'start.bat', 'start.sh',
              '.gitignore', '.gitattributes', 'CONTRIBUTING.md', 'CONTRIBUTING_EN.md']


def package_info(root):
    tree = ast.parse((root / 'gpt56_vnext/__init__.py').read_text(encoding='utf-8'))
    values = {target.id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
              for target in node.targets if isinstance(target, ast.Name)}
    version, baseline = values['__version__'], values['BUNDLED_BASELINES']
    if (root / 'VERSION').read_text().strip() != version:
        raise ValueError('VERSION does not match the runtime')
    if Path(baseline).name != baseline:
        raise ValueError('Invalid bundled baseline directory')
    return version, baseline


def release_files(root=ROOT):
    _, baseline_version = package_info(root)
    paths = set(root / name for name in ROOT_FILES)
    paths.update((root / 'gpt56_vnext').glob('*.py'))
    for folder in ('web', 'assets', 'agent_kit'):
        paths.update(path for path in (root / 'gpt56_vnext' / folder).rglob('*') if path.is_file())
    baseline = root / 'gpt56_vnext/baselines' / baseline_version
    manifest = baseline / 'manifest.json'
    paths.add(manifest)
    for item in json.loads(manifest.read_text())['packages']:
        if Path(item['file']).name != item['file']:
            raise ValueError('Invalid bundle filename')
        paths.add(baseline / item['file'])
    for folder in ('docs', 'scripts', 'tests', 'benchmarks', '.github/workflows'):
        paths.update(path for path in (root / folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    result = {}
    for path in sorted(paths):
        name = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Files must stay inside the release tree')
        if path.suffix in {'.sqlite3', '.db', '.pyc', '.env'} or any(part in {'meow_runs', '.venv', '.git'} for part in path.parts):
            raise ValueError('Private runtime file in release')
        raw = path.read_bytes()
        if path.suffix in {'.py', '.js', '.css', '.html', '.json', '.md', '.sh', '.txt'} or path.name in {'LICENSE', 'VERSION', '.gitignore', '.gitattributes'}:
            raw = raw.replace(b'\r\n', b'\n')
        if path.suffix == '.bat':
            raw = raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        result[name] = raw
    return result


def installation_files(files, version, locale, kind='source'):
    content = dict(files)
    content.pop('MEOW_INSTALL.json', None)
    content.pop('SHA256SUMS.txt', None)
    content['locale.json'] = (json.dumps({'locale': locale}) + '\n').encode()
    manifest = {'schema': 1, 'version': version, 'kind': kind, 'locale': locale,
                'files': {p: hashlib.sha256(data).hexdigest() for p, data in sorted(content.items())}}
    content['MEOW_INSTALL.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    content['SHA256SUMS.txt'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {path}\n'
                                     for path, data in sorted(content.items())).encode()
    return content


def write_archive(target, content):
    if target.exists():
        raise FileExistsError(target)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, data in sorted(content.items()):
            info = zipfile.ZipInfo(target.stem + '/' + path, date_time=(2026, 9, 9, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if path.endswith('.sh') else 0o100644) << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def build(output, root=ROOT):
    version, _ = package_info(root)
    output.mkdir(parents=True, exist_ok=True)
    files = release_files(root)
    checksums = []
    for locale in ('zh-CN', 'en'):
        name = f'meow-llm-detector-v{version}-{locale}'
        content = dict(files)
        content['README.md'] = files['README_EN.md' if locale == 'en' else 'README_CN.md']
        content = installation_files(content, version, locale)
        target = output / (name + '.zip')
        write_archive(target, content)
        checksums.append(f'{hashlib.sha256(target.read_bytes()).hexdigest()}  {target.name}\n')
        print(target)
    (output / 'SHA256SUMS.txt').write_text(''.join(checksums), encoding='ascii')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    build(parser.parse_args().output)
