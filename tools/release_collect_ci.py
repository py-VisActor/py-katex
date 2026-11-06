"""Archive and verify actual GitHub CI render files and published-release state."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import io
import json
import urllib.parse
import urllib.request
import zipfile

from release_github import API, credentials, request


class StripCrossHostAuthorization(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            redirected.remove_header('Authorization')
        return redirected


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workflow-run', type=int, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    args.out.mkdir(parents=True, exist_ok=False)
    base = API + '/actions/runs/' + str(args.workflow_run)
    run = request(base)
    jobs = request(base + '/jobs')
    artifacts = request(base + '/artifacts')
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    assert all(j['conclusion'] == 'success' for j in jobs['jobs'])
    assert {j['name'] for j in jobs['jobs']} == {
        'validate (windows-2025)', 'validate (ubuntu-24.04)', 'publish', 'verify-and-promote'}
    for name, data in [('workflow', run), ('jobs', jobs), ('artifacts', artifacts)]:
        (args.out / (name + '.json')).write_text(json.dumps(data, indent=2) + '\n', 'utf-8')
    receipts = {}
    expected = {'release-validation-windows-2025': 'release-validation',
                'release-validation-ubuntu-24.04': 'release-validation',
                'published-download-installation-evidence': 'pypi-validation'}
    for artifact in artifacts['artifacts']:
        name = artifact['name']
        if name not in expected:
            continue
        assert not artifact['expired'] and Path(name).name == name
        assert artifact['archive_download_url'].startswith(API + '/actions/artifacts/')
        req = urllib.request.Request(artifact['archive_download_url'], headers={
            'Authorization': 'Bearer ' + credentials(), 'User-Agent': 'py-katex-publication-audit'})
        with urllib.request.build_opener(StripCrossHostAuthorization).open(req, timeout=120) as response:
            raw = response.read()
        assert artifact['digest'] == 'sha256:' + digest(raw)
        (args.out / (name + '.zip')).write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            key = next(k for k in names if k.endswith(expected[name] + '/validation.json'))
            validation = json.loads(archive.read(key))
            assert validation['status'] == 'PASS'
            assert validation['artifacts'] == manifest['distributions']
            assert len(validation['installations']) == 2
            sample_count = 0
            for mode in ['wheel', 'sdist']:
                key = next(k for k in names if k.endswith('/' + mode + '/smoke-cpu/smoke.json'))
                smoke = json.loads(archive.read(key))
                assert smoke['status'] == 'PASS' and smoke['isolated'] and not smoke['nodeAvailable']
                assert smoke['project'] == manifest['project'] and smoke['version'] == manifest['version']
                assert smoke['bundledFonts'] == 20 and smoke['backend'] == 'cpu'
                assert len(smoke['samples']) == 13
                for sample in smoke['samples']:
                    path = str(PurePosixPath(key).parent / sample['file'])
                    payload = archive.read(path)
                    assert digest(payload) == sample['sha256'] and len(payload) == sample['bytes']
                    if path.endswith('.png'):
                        assert sample['paintedPixels'] > 4
                sample_count += len(smoke['samples'])
        receipts[name] = {'status': 'PASS', 'artifactId': artifact['id'],
                          'archiveSha256': digest(raw), 'archiveBytes': len(raw),
                          'externalInstallations': 2, 'actualVerifiedCpuSamples': sample_count}
    assert set(receipts) == set(expected)
    release = request(API + '/releases/tags/' + manifest['tag'])
    latest = request(API + '/releases/latest')
    assert not release['prerelease'] and not release['draft']
    assert latest['id'] == release['id']
    assets = {item['name']: item for item in release['assets']}
    for name, identity in manifest['distributions'].items():
        assert assets[name]['digest'] == 'sha256:' + identity['sha256']
    assert assets['release-manifest.json']['digest'] == 'sha256:' + digest(manifest_bytes)
    result = {'schema': 'py-katex-publication-ci/v1', 'status': 'PASS_PUBLISHED_DOWNLOAD_INSTALL_VERIFIED',
              'project': manifest['project'], 'version': manifest['version'],
              'sourceCommit': manifest['sourceCommit'], 'manifestSha256': digest(manifest_bytes),
              'workflowRun': args.workflow_run, 'workflowURL': run['html_url'],
              'githubReleaseURL': release['html_url'], 'githubPrerelease': False,
              'pypiURL': 'https://pypi.org/project/' + manifest['project'] + '/' + manifest['version'] + '/',
              'distributions': manifest['distributions'], 'artifacts': receipts}
    (args.out / 'publication-ci.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps({'status': result['status'], 'project': result['project'], 'ciArtifacts': len(receipts), 'release': release['html_url']}))


if __name__ == '__main__':
    main()
