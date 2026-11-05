"""Reuse fixed A images only with exact fixtures, IDs and original byte hashes."""
from pathlib import Path
import argparse
import json
import shutil
from run_support import file_identity,write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--fixtures',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();manifest=json.loads((args.source/'manifest.json').read_text('utf-8'));fixtures=json.loads(args.fixtures.read_text('utf-8'))
    if manifest.get('version')!='0.18.11' or manifest.get('inputSha')!=file_identity(args.fixtures)['sha256']:raise ValueError('Fixed source/fixture identity mismatch')
    expected={item['id'] for item in fixtures['cases']}
    if {item['id'] for item in manifest['cases']}!=expected:raise ValueError('Oracle case denominator changed')
    for item in manifest['cases']:
        if item['status']!='PASS':raise ValueError('Cannot reuse a failed official capture')
        metadata=json.loads((args.source/(item['id']+'.json')).read_text('utf-8'))
        identity=file_identity(args.source/(item['id']+'.png'))
        if identity['sha256']!=metadata['pngSha256'] or identity['sha256']!=item['pngSha256']:raise ValueError('Original A PNG changed')
    shutil.copytree(args.source,args.out)
    identities={}
    for file in args.source.iterdir():
        if file.is_file():
            identity=file_identity(file)
            if file_identity(args.out/file.name)!=identity:raise ValueError('Copied A artifact changed')
            identities[file.name]=identity
    write_json(args.out.parent/'oracle-reuse.json',{'schema':'py-katex-fixed-oracle-reuse/v1','source':str(args.source.resolve()),'input':file_identity(args.fixtures),'files':identities,'renderedDuringReuse':False},exclusive=True)
    print(json.dumps({'status':'PASS','cases':len(expected),'files':len(identities),'rendered':False}))


if __name__=='__main__':main()
