"""Verify PyPI metadata and actual downloads against reviewed GitHub assets."""
from pathlib import Path
import argparse
import hashlib
import json
import tomllib
import urllib.request
import urllib.parse


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text('utf-8'))
    project = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text('utf-8'))['project']['name']
    assert manifest['project'] == project
    version = manifest['version']
    args.out.mkdir(parents=True, exist_ok=False)
    url = 'https://pypi.org/pypi/' + project + '/' + version + '/json'
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read()
    (args.out / 'index.json').write_bytes(raw)
    index = json.loads(raw)
    assert index['info']['name'] == project and index['info']['version'] == version
    assert index['info']['requires_dist'] == ['py-skia-canvas==0.1.0a18']
    assert f'pip install {project}=={version}' in index['info']['description']
    assert set(manifest['distributions']) == {item['filename'] for item in index['urls']}
    for item in index['urls']:
        name = item['filename']
        assert not item['yanked']
        assert urllib.parse.urlsplit(item['url']).hostname == 'files.pythonhosted.org'
        assert item['digests']['sha256'] == manifest['distributions'][name]['sha256']
        with urllib.request.urlopen(item['url'], timeout=120) as response:
            payload = response.read()
        assert hashlib.sha256(payload).hexdigest() == manifest['distributions'][name]['sha256']
        assert len(payload) == manifest['distributions'][name]['bytes']
        (args.out / name).write_bytes(payload)
    result = {'status': 'PUBLISHED_DOWNLOAD_VERIFIED', 'project': project, 'version': version,
              'url': 'https://pypi.org/project/' + project + '/' + version + '/', 'distributions': manifest['distributions']}
    (args.out / 'publication.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
