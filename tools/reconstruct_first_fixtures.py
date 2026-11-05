"""Recover corrected historical fixture bytes, proving original recorded SHA.

Writes a NEW evidence directory only; never changes the original closed run.
This closes the old logger's hash-only input limitation. New joint snapshots
also archive every test, fixture and development tool before execution.
"""
from pathlib import Path
import argparse
from copy import deepcopy
import hashlib
import json
from run_support import ROOT,file_identity,write_json


def encoded_match(data,expected):
    for ascii in [True,False]:
        text=json.dumps(data,ensure_ascii=ascii,indent=2)+'\n'
        for newline in ['\n','\r\n']:
            raw=text.replace('\n',newline).encode('utf-8')
            if hashlib.sha256(raw).hexdigest()==expected['sha256'] and len(raw)==expected['bytes']:return raw
    raise ValueError('Historical reconstruction did not match original bytes')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    old=ROOT/'test-runs/MATH-batch-20261105T155834Z-e542e4f2';manifest=json.loads((old/'run.json').read_text('utf-8'))
    args.out.mkdir(parents=True,exist_ok=False);proof=[]
    def expected(relative):return manifest['inputs'][str((ROOT/relative).resolve())]
    def save(name,raw,wanted,method):
        path=args.out/name;path.write_bytes(raw)
        if file_identity(path)!=wanted:raise ValueError('Historical SHA/length mismatch')
        proof.append({'file':name,'identity':wanted,'reconstruction':method})
    resource=json.loads((ROOT/'tests/full-resource-cases.json').read_text('utf-8'))
    next(case for case in resource['cases'] if case['id']=='html-paint')['glyphs']='xxx'
    resource_sha='5284bcba9dc58a45e22fb91b1adba32279c1e3d3ec3552c05d16f90aeb863218'
    raw=encoded_match(resource,{'sha256':resource_sha,'bytes':9080})
    save('full-resource-cases.json',raw,{'sha256':resource_sha,'bytes':9080},'Undo the single html-paint glyph probe correction; matches immutable P2 receipt SHA')
    registry=json.loads((ROOT/'tests/full-parser-cases.json').read_text('utf-8'))
    next(case for case in registry['cases'] if case['id']=='macro-277')['tex']=r'\bra@ket{\left\langle}{\middle|}{\middle\Vert}{\right\rangle}{x|y}'
    save('full-parser-cases.json',encoded_match(registry,expected('tests/full-parser-cases.json')),expected('tests/full-parser-cases.json'),'Undo source-proved active-bar context correction; original bad input also retained as a negative regression')
    visual=json.loads((ROOT/'tests/full-visual-cases.json').read_text('utf-8'))
    visual['inputs']['tests/full-resource-cases.json']=resource_sha
    case=next(case for case in visual['cases'] if case['id']=='html-paint');case['glyphs']='xxx';case['requiredGlyphs']='xxx'
    case=next(case for case in visual['cases'] if case['id']=='full-css-font-axes');case['tex']=case['tex'].replace('font-size:1.5em','font-size:150%');case['sourceInputSha256']=hashlib.sha256(case['tex'].encode()).hexdigest()
    save('full-visual-cases.json',encoded_match(visual,expected('tests/full-visual-cases.json')),expected('tests/full-visual-cases.json'),'Undo only source CSS-comment fixture correction and html-paint glyph probe/input-reference changes')
    for relative in ['tests/full-screenshotter-cases.json','tools/plans/full-first.json']:
        save(Path(relative).name,(ROOT/relative).read_bytes(),expected(relative),'Current bytes are unchanged and equal original recorded SHA')
    write_json(args.out/'reconstruction.json',{'schema':'py-katex-historical-input-reconstruction/v1','originalRun':str(old),'closedRunModified':False,'status':'PASS_EXACT_ORIGINAL_FINGERPRINTS','files':proof},exclusive=True)
    print(json.dumps({'status':'PASS','recoveredInputs':len(proof),'closedRunModified':False}))


if __name__=='__main__':main()
