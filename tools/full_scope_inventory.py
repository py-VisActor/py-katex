"""Inventory locked upstream inputs; this is not a behavioral coverage claim."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / '.local/upstream-katex'


def main():
    expected = json.loads((ROOT / 'references/upstream.lock.json').read_text('utf-8'))
    actual = subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip()
    # The source lock owns the commit spelling; do not replace it with latest.
    locked = expected.get('commit', expected.get('sourceCommit', expected.get('gitCommit')))
    if locked is None:
        locked = 'd5bed9f38a8d747b9c4a12e18897a514707e1c26'
    if actual != locked:
        raise ValueError('Locked upstream commit changed')
    dirty = subprocess.check_output(['git', '-C', str(UPSTREAM), 'status', '--porcelain'], text=True)
    if dirty:
        raise ValueError('Upstream checkout has modifications')
    inventory = json.loads((ROOT / 'references/function-inventory.json').read_text('utf-8'))
    files = {}
    for folder in ['src', 'test', 'docs', 'contrib']:
        for file in sorted((UPSTREAM / folder).rglob('*')):
            if file.is_file() and file.suffix in {'.ts', '.js', '.md', '.yaml', '.scss', '.snap'}:
                files[file.relative_to(UPSTREAM).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    schema = (UPSTREAM / 'src/Settings.ts').read_text('utf-8').split('export const SETTINGS_SCHEMA: Schema = {', 1)[1].split('\n};', 1)[0]
    settings = re.findall(r'^    (\w+): \{', schema, re.M)
    registrations = []
    function_macros = []
    for item in inventory['functions']:
        for name in item['names']:
            registrations.append({'name': name, 'source': item['source'], 'category': item['category']})
        for name in item['macroNames']:
            function_macros.append({'name': name, 'source': item['source']})
    static_count=len({r['name'] for r in registrations})
    runtime=json.loads((ROOT/'references/full-runtime-registry.json').read_text('utf-8'))
    known={r['name'] for r in registrations}
    for category in ('functions','environments'):
        for name in runtime[category]:
            if name not in known:
                if runtime[category][name].get('type')!='sizing':
                    raise ValueError('Unmapped dynamic registry entry: '+name)
                registrations.append({'name':name,'source':'src/functions/sizing.ts','category':category,'discovery':'runtime_source_registry_dynamic_names'})
                known.add(name)
    if known!=set(runtime['functions'])|set(runtime['environments']):
        raise ValueError('Static and actual source registry disagree')
    classification = {
        'output': 'excluded_markup_backend_use_native_formats',
        'displayMode': 'retained_static_with_explicit_content_width',
        'globalGroup': 'retained_with_explicit_MacroState',
        'trust': 'retained_boolean_or_python_callback_offline_resources_only',
    }
    data = {
        'schema': 'py-katex-full-core-scope/v1', 'phase': 'P1',
        'status': 'inventory_only_not_behavior_verified', 'version': '0.18.11',
        'upstreamCommit': actual, 'upstreamFiles': files,
        'registrations': registrations, 'uniqueRegistrationNames': len({r['name'] for r in registrations}),
        'historicalStaticScannerNames':static_count,
        'runtimeRegistry':'references/full-runtime-registry.json',
        'runtimeMacros':{'total':len(runtime['macros']),'literal':sum(x['kind']=='literal' for x in runtime['macros'].values()),'dynamic':sum(x['kind']=='function' for x in runtime['macros'].values())},
        'functionLocalMacroRegistrations': function_macros,
        'mainLiteralMacros': len(json.loads((ROOT / 'src/py_katex/data/macros.json').read_text('utf-8'))),
        'mainDynamicMacros': inventory['dynamicMacros'],
        'settings': [{'name': name, 'scope': classification.get(name, 'retained_static')} for name in settings],
        'sourceSpecs': [name for name in files if name.startswith('test/') and name.endswith('-spec.ts')],
        'screenshotter': 'test/screenshotter/ss_data.yaml',
        'contribClassification': {
            'auto-render': 'DOM_host_integration_outside_native_core',
            'copy-tex': 'clipboard_interaction_excluded_by_user',
            'mathtex-script-type': 'DOM_host_integration_outside_native_core',
            'render-a11y-string': 'accessibility_outside_requested_static_rendering',
            'mhchem': 'separate_optional_extension_not_in_original_core_registration_scope',
        },
        'claim': 'All input files and denominators retained. Neither registration linkage nor this inventory is proof of compatibility.',
    }
    out = ROOT / 'references/full-core-inventory.json'
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({'files': len(files), 'registrations': len(registrations), 'unique': data['uniqueRegistrationNames'], 'settings': settings, 'specs': len(data['sourceSpecs'])}))


if __name__ == '__main__':
    main()
