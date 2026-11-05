"""Audit a documented joint delivery without installing or rendering packages."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request
import zipfile

from joint_candidate import current
from run_support import ROOT, verify_run, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    summary = json.loads((ROOT / 'references/verification-summary.json').read_text('utf-8'))
    expected = json.loads((ROOT / summary['jointCandidate']).read_text('utf-8'))
    assert current() == expected, 'Joint candidate changed after verification'
    assert sum(summary['unit']['groups'].values()) == summary['unit']['methods'] == 712
    assert summary['unit']['product'] + summary['unit']['tooling'] == 712
    assert summary['visual']['standaloneCases'] + summary['visual']['integrationCases'] == 69
    assert summary['visual']['views'] == 207
    assert sum(summary['legacy']['positiveBySlice'].values()) == 297
    verified = {}
    for name, relative in summary['runs'].items():
        path = ROOT / relative
        manifest = json.loads((path / 'run.json').read_text('utf-8'))
        assert manifest['status'] == 'SUCCESS', name
        assert manifest['sourceUnchanged'], name
        result = verify_run(path)
        assert result['integrityStatus'] == 'PASS', result
        verified[name] = result
    report = ROOT.parent / summary['report']['path'] / 'index.html'
    local_bytes = report.read_bytes()
    with urllib.request.urlopen(summary['report']['url'], timeout=15) as response:
        served_bytes = response.read()
    assert served_bytes == local_bytes
    assert hashlib.sha256(local_bytes).hexdigest() == summary['report']['html']['sha256']
    for repository in [ROOT, ROOT.parent / 'py-mermaid']:
        state = json.loads((repository / 'docs/execution-state.json').read_text('utf-8'))
        assert state['phase'].endswith('P5')
        assert state.get('status', state.get('currentScopeStatus')) == 'complete_local_native_static_alpha'
        for file in (repository / 'references').glob('*.json'):
            json.loads(file.read_text('utf-8'))
    args.out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out / 'delivery-docs-tools-tests.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for repository in [ROOT, ROOT.parent / 'py-mermaid']:
            for directory in ['docs', 'references', 'tools', 'tests']:
                for file in sorted((repository / directory).rglob('*')):
                    if file.is_file() and not any(part in {'__pycache__', '.pytest_cache'} for part in file.parts):
                        archive.write(file, repository.name + '/' + file.relative_to(repository).as_posix())
            archive.write(repository / 'AGENTS.md', repository.name + '/AGENTS.md')
    write_json(args.out / 'audit.json', {
        'status': 'PASS', 'jointSourceSHA256': summary['jointSourceSHA256'],
        'verifiedRuns': verified, 'reportUrl': summary['report']['url'],
        'reportSha256': hashlib.sha256(served_bytes).hexdigest(),
        'installationValidation': 'deferred_not_executed',
        'archive': 'delivery-docs-tools-tests.zip',
    }, exclusive=True)
    print(json.dumps({'status': 'PASS', 'runs': len(verified), 'reportHttpMatches': True}))


if __name__ == '__main__':
    main()
