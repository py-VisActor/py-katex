"""GitHub release operations using existing credentials, never logging tokens."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'py-VisActor/py-katex'
API = 'https://api.github.com/repos/' + REPOSITORY


def credentials():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    process = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                             capture_output=True, text=True,
                             env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'})
    values = dict(line.split('=', 1) for line in process.stdout.splitlines() if '=' in line)
    if not values.get('password'):
        raise RuntimeError('No existing GitHub credential is available')
    return values['password']


def request(url, *, method='GET', data=None, content_type='application/json', missing=False):
    if urllib.parse.urlsplit(url).hostname not in {'api.github.com', 'uploads.github.com'}:
        raise ValueError('GitHub credentials must only be sent to GitHub API hosts')
    raw = json.dumps(data).encode() if isinstance(data, dict) else data
    req = urllib.request.Request(url, data=raw, method=method, headers={
        'Authorization': 'Bearer ' + credentials(), 'Accept': 'application/vnd.github+json',
        'Content-Type': content_type, 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'py-katex-release'})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        if missing and error.code == 404:
            return None
        # Responses do not include Authorization; never serialize request headers.
        raise RuntimeError(f'GitHub {method} failed ({error.code}): ' + error.read().decode()[:1500]) from None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(tag, out, metadata_out, expected_manifest):
    release = request(API + '/releases/tags/' + urllib.parse.quote(tag, safe=''))
    assets = {item['name']: item for item in release['assets']}
    manifest_asset = assets['release-manifest.json']
    with urllib.request.urlopen(manifest_asset['browser_download_url'], timeout=60) as response:
        raw = response.read()
    assert expected_manifest and hashlib.sha256(raw).hexdigest() == expected_manifest, 'Reviewed manifest fingerprint differs'
    manifest = json.loads(raw)
    assert manifest['project'] == 'py-katex' and manifest['version'] == '0.1.0'
    assert manifest['tag'] == tag and len(manifest['distributions']) == 2
    # Pin validation to the checked-out release commit, not the current main branch.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    assert manifest['sourceCommit'] == head, 'Checked-out source does not match reviewed release'
    out.mkdir(parents=True, exist_ok=False)
    metadata_out.mkdir(parents=True, exist_ok=False)
    (metadata_out / 'release-manifest.json').write_bytes(raw)
    for name, identity in manifest['distributions'].items():
        assert Path(name).name == name and name.endswith(('.whl', '.tar.gz'))
        with urllib.request.urlopen(assets[name]['browser_download_url'], timeout=120) as response:
            data = response.read()
        assert len(data) == identity['bytes'] and hashlib.sha256(data).hexdigest() == identity['sha256']
        (out / name).write_bytes(data)
    return {'status': 'PASS', 'release': release['html_url'], 'manifestSha256': hashlib.sha256(raw).hexdigest(), 'distributions': manifest['distributions']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['create', 'download', 'dispatch', 'promote', 'status'])
    p.add_argument('--tag', default='v0.1.0')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--dist', type=Path)
    p.add_argument('--notes', type=Path)
    p.add_argument('--manifest-sha256')
    args = p.parse_args()
    result = {}
    if args.action == 'download':
        result = download(args.tag, args.dist, args.out, args.manifest_sha256)
    else:
        args.out.mkdir(parents=True, exist_ok=False)
        if args.action == 'create':
            assert args.manifest and args.dist and args.notes
            manifest = json.loads(args.manifest.read_text('utf-8'))
            assert manifest['tag'] == args.tag
            for name, identity in manifest['distributions'].items():
                assert digest(args.dist / name) == identity['sha256']
            release = request(API + '/releases/tags/' + args.tag, missing=True)
            if release is None:
                release = request(API + '/releases', method='POST', data={
                    'tag_name': args.tag, 'target_commitish': manifest['sourceCommit'],
                    'name': 'py-katex 0.1.0', 'body': args.notes.read_text('utf-8'),
                    'draft': False, 'prerelease': True, 'make_latest': 'false'})
            assert release['tag_name'] == args.tag
            files = [args.dist / name for name in manifest['distributions']] + [args.manifest]
            sums = args.out / 'SHA256SUMS.txt'
            sums.write_text(''.join(digest(file) + '  ' + file.name + '\n' for file in files), 'utf-8')
            files.append(sums)
            for file in files:
                current = next((a for a in release['assets'] if a['name'] == file.name), None)
                if current:
                    assert current.get('digest') == 'sha256:' + digest(file), 'Existing release asset differs; never overwrite reviewed bytes'
                    continue
                asset = request(release['upload_url'].split('{', 1)[0] + '?name=' + urllib.parse.quote(file.name),
                                method='POST', data=file.read_bytes(), content_type='application/octet-stream')
                assert asset['size'] == file.stat().st_size
            result = request(API + '/releases/' + str(release['id']))
        elif args.action == 'dispatch':
            assert args.manifest_sha256 and len(args.manifest_sha256) == 64
            request(API + '/environments/pypi', method='PUT', data={})
            request(API + '/actions/workflows/publish-pypi.yml/dispatches', method='POST',
                    data={'ref': 'main', 'inputs': {'release_tag': args.tag, 'manifest_sha256': args.manifest_sha256}})
            result = {'status': 'DISPATCHED', 'tag': args.tag}
        elif args.action == 'promote':
            release = request(API + '/releases/tags/' + args.tag)
            notes = args.notes.read_text('utf-8') if args.notes else release['body']
            result = request(API + '/releases/' + str(release['id']), method='PATCH',
                             data={'prerelease': False, 'draft': False, 'make_latest': 'true', 'body': notes})
        else:
            result = request(API + '/actions/workflows/publish-pypi.yml/runs?per_page=5')
        (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps({'action': args.action, 'status': result.get('status', 'SUCCESS'), 'url': result.get('html_url')}))


if __name__ == '__main__':
    main()
