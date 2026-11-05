"""Audit the documented full-core delivery; never install or render packages."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request
import zipfile

from joint_candidate import current
from run_support import ROOT, verify_run, write_json


def read(path):
    return json.loads(path.read_text('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    summary = read(ROOT / 'references/full-verification-summary.json')
    assert summary['status'] == 'PASS_FULL_CORE_STATIC_LOCAL'
    assert current() == summary['source'], 'Joint product source changed'
    assert sum(summary['tests']['groups'].values()) == summary['tests']['total']
    assert summary['registry']['registered'] == 345
    assert summary['registry']['contexts'] == 684
    assert summary['coreCorpus']['expressionCounts'] == {'PASS': summary['coreCorpus']['expressions']}
    assert summary['views'] == summary['cases'] * len(summary['profiles'])
    assert summary['standaloneCases'] == len(read(ROOT / 'tests/full-visual-cases.json')['cases'])
    assert summary['integrationCases'] == len(read(ROOT / 'tests/integration-cases.json')['cases'])
    verified = {}
    for name, relative in summary['runs'].items():
        run = ROOT / relative
        manifest = read(run / 'run.json')
        assert manifest['status'] == 'SUCCESS' and manifest['sourceUnchanged'], name
        result = verify_run(run)
        assert result['integrityStatus'] == 'PASS', (name, result)
        verified[name] = result
    html = ROOT.parent / summary['report']['path'] / 'index.html'
    with urllib.request.urlopen(summary['report']['url'], timeout=20) as response:
        assert response.status == 200
        served = response.read()
    assert served == html.read_bytes()
    assert hashlib.sha256(served).hexdigest() == summary['report']['html']['sha256']
    qa = read(ROOT / summary['runs']['htmlQa'] / 'artifacts/qa/report.json')
    assert qa['status'] == 'PASS' and len(qa['views']) == summary['views']
    assert qa['htmlSha256'] == summary['report']['html']['sha256']
    assert len(qa['downloads']) == 5 and not qa['externalRequests'] and not qa['errors']
    for repo in [ROOT, ROOT.parent / 'py-mermaid']:
        state = read(repo / 'docs/execution-state.json')
        assert state['phase'] == 'MATH-FULL-P5'
        assert state['currentScopeStatus'] == 'complete_local_core_static'
        assert not state['activeLeases']
        for file in (repo / 'references').glob('*.json'):
            read(file)
    args.out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.out / 'delivery-docs-tools-tests.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for repo in [ROOT, ROOT.parent / 'py-mermaid']:
            for directory in ['docs', 'references', 'tools', 'tests']:
                for file in sorted((repo / directory).rglob('*')):
                    if file.is_file() and not any(part in {'__pycache__', '.pytest_cache'} for part in file.parts):
                        archive.write(file, repo.name + '/' + file.relative_to(repo).as_posix())
            archive.write(repo / 'AGENTS.md', repo.name + '/AGENTS.md')
    write_json(args.out / 'audit.json', {
        'status': 'PASS', 'jointSourceSHA256': {name: value['sourceTreeSha256'] for name, value in summary['source'].items()},
        'verifiedRuns': verified, 'reportUrl': summary['report']['url'],
        'reportSha256': hashlib.sha256(served).hexdigest(),
        'installationValidation': 'deferred_not_executed',
        'archive': 'delivery-docs-tools-tests.zip',
    }, exclusive=True)
    print(json.dumps({'status': 'PASS', 'runs': len(verified), 'reportHttpMatches': True}))


if __name__ == '__main__':
    main()
