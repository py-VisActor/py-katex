"""Verify package bytes, the accepted runtime delta and external installations."""
from pathlib import Path, PurePosixPath
import argparse
import email
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / 'pyproject.toml').read_text('utf-8'))['project']['name']
STEM = PROJECT.replace('-', '_')
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text('utf-8'))['project']['version']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def runtime_files():
    root = ROOT / 'src/py_katex'
    return {p.relative_to(ROOT / 'src').as_posix(): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def metadata(raw):
    item = email.message_from_bytes(raw)
    assert item['Name'] == PROJECT and item['Version'] == VERSION
    assert item['Requires-Python'] == '<3.14,>=3.13'
    assert item.get_all('Requires-Dist') == ['py-skia-canvas==0.1.0a18']
    assert item['License-Expression'] == 'MIT'
    assert len(item.get_all('License-File')) == 3
    description = item.get_payload()
    assert f'pip install {PROJECT}=={VERSION}' in description
    assert 'https://github.com/py-VisActor/py-katex/blob/main/docs/README.md' in description


def verify(wheel, sdist):
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text('utf-8'))['project']['version']
    assert version == VERSION
    files = runtime_files()
    accepted = json.loads((ROOT / 'references/full-verification-summary.json').read_text('utf-8'))['source']['math']['files']
    assert {'src/' + name for name in files} == {name for name in accepted if name.startswith('src/')}
    for name, raw in files.items():
        old = raw.replace(("__version__='" + VERSION + "'").encode(), b"__version__='0.1.0a0'") if name == 'py_katex/__init__.py' else raw
        assert sha(old) == accepted['src/' + name], 'Unexpected runtime change since accepted candidate: ' + name
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        actual = {name: z.read(name) for name in names if name.startswith('py_katex/')}
        assert actual == files, 'Wheel runtime payload differs from source'
        info = STEM + '-' + VERSION + '.dist-info/'
        metadata(z.read(info + 'METADATA'))
        assert 'py-katex = py_katex.__main__:main' in z.read(info + 'entry_points.txt').decode()
        assert 'Tag: py3-none-any' in z.read(info + 'WHEEL').decode()
        assert any(name.endswith('/licenses/references/licenses/katex-LICENSE') for name in names)
        assert not any(name.startswith(('tests/', 'tools/', '.local/')) for name in names)
    with tarfile.open(sdist, 'r:gz') as archive:
        members = archive.getmembers()
        assert all(not p.issym() and not p.islnk() and not PurePosixPath(p.name).is_absolute()
                   and '..' not in PurePosixPath(p.name).parts for p in members)
        top = PurePosixPath(members[0].name).parts[0]
        contents = {p.name[len(top) + 1:]: archive.extractfile(p).read() for p in members if p.isfile()}
        assert {name[4:]: raw for name, raw in contents.items() if name.startswith('src/py_katex/')} == files
        metadata(contents['PKG-INFO'])
        assert contents['README.md'] == (ROOT / 'README.md').read_bytes()
        assert 'references/licenses/katex-LICENSE' in contents
        assert not any(name.startswith(('.local/', 'test-runs/', 'dist/', 'reports/')) for name in contents)
    return {'status': 'PASS', 'runtimeFiles': len(files), 'bundledFonts': sum(name.endswith('.ttf') for name in files),
            'acceptedRuntimeDelta': 'Only __version__ 0.1.0a0 -> ' + VERSION + '; all other runtime bytes identical',
            'artifacts': {p.name: {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size} for p in [wheel, sdist]}}


def install(artifact, out, backends):
    # Preserve the external environment path as provenance; never import checkout src.
    home = Path(tempfile.mkdtemp(prefix='py-katex-' + VERSION + '-'))
    assert not home.resolve().is_relative_to(ROOT.parent.resolve())
    environment = home / 'venv'
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    work = home / 'work'
    work.mkdir()
    out.mkdir(parents=True, exist_ok=False)
    child_env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
    child_env.update(PYTHONIOENCODING='utf-8', PIP_DISABLE_PIP_VERSION_CHECK='1')
    commands = []

    def command(name, argv, *, no_path=False):
        env = {**child_env, **({'PATH': ''} if no_path else {})}
        result = subprocess.run([str(v) for v in argv], cwd=work, env=env, capture_output=True, timeout=600)
        (out / (name + '.stdout.log')).write_bytes(result.stdout)
        (out / (name + '.stderr.log')).write_bytes(result.stderr)
        commands.append({'name': name, 'argv': [str(v) for v in argv], 'cwd': str(work), 'exitCode': result.returncode, 'emptyPath': no_path})
        assert result.returncode == 0, 'External command failed: ' + name + '; see ' + str(out)

    command('install-native-dependency', [python, '-I', '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple/', '--no-cache-dir', '--only-binary=:all:', 'py-skia-canvas==0.1.0a18'])
    command('install-distribution', [python, '-I', '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple/', '--no-cache-dir', '--no-deps', artifact.resolve()])
    command('pip-check', [python, '-I', '-m', 'pip', 'check'])
    for backend in backends:
        command('smoke-' + backend, [python, '-I', ROOT / 'tools/release_smoke.py', '--out', out / ('smoke-' + backend), '--backend', backend, '--expected-version', VERSION], no_path=True)
    command('module-cli', [python, '-I', '-m', 'py_katex', 'x^2+y^2=z^2', '--backend', 'cpu', '-o', out / 'module-cli.png'], no_path=True)
    executable = environment / ('Scripts/py-katex.exe' if os.name == 'nt' else 'bin/py-katex')
    command('installed-console-cli', [executable, 'x^2+y^2=z^2', '--backend', 'cpu', '-o', out / 'console-cli.svg'], no_path=True)
    receipt = {'status': 'PASS', 'artifact': artifact.name, 'sha256': sha(artifact.read_bytes()), 'externalEnvironment': str(environment), 'commands': commands}
    (out / 'installation.json').write_text(json.dumps(receipt, indent=2) + '\n', 'utf-8')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wheel', type=Path, required=True)
    p.add_argument('--sdist', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--install', action='store_true')
    p.add_argument('--backend', choices=['cpu', 'auto', 'gpu'], action='append')
    args = p.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    result = verify(args.wheel, args.sdist)
    if args.install:
        result['installations'] = [install(path, args.out / kind, args.backend or ['cpu'])
                                   for kind, path in [('wheel', args.wheel), ('sdist', args.sdist)]]
    (args.out / 'validation.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps({'status': 'PASS', 'runtimeFiles': result['runtimeFiles'], 'installations': len(result.get('installations', []))}))


if __name__ == '__main__':
    main()
