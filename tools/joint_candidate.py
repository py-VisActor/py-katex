"""Snapshot/check both source repositories without installing either package."""
from pathlib import Path
import argparse,importlib.util,json,zipfile
from run_support import ROOT,source_identity,write_json,file_identity


def current():
    target=ROOT.parent/'py-mermaid'
    spec=importlib.util.spec_from_file_location('mermaid_run_identity',target/'tools/run_support.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return {'math':source_identity(),'mermaid':module.source_identity(target)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--check',type=Path);args=p.parse_args();data=current()
    if args.check:
        if data!=json.loads(args.check.read_text('utf-8')):raise ValueError('Joint source candidate changed')
    if args.out:
        args.out.mkdir(parents=True,exist_ok=True);write_json(args.out/'joint-candidate.json',data,exclusive=True)
        with zipfile.ZipFile(args.out/'joint-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for name,root in [('math',ROOT),('mermaid',ROOT.parent/'py-mermaid')]:
                for file in data[name]['files']:archive.write(root/file,root.name+'/'+file)
        # Preserve the exact test/fixture/tool bytes as well as product source.
        # A hash pointing at a mutable working-tree fixture is insufficient to
        # reproduce an earlier failure after a legitimate fixture correction.
        verification={}
        with zipfile.ZipFile(args.out/'joint-verification-inputs.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for root in [ROOT,ROOT.parent/'py-mermaid']:
                for folder in ['tests','tools','references','docs']:
                    for file in sorted((root/folder).rglob('*')):
                        if not file.is_file() or any(part in {'__pycache__','.pytest_cache'} for part in file.parts):continue
                        relative=root.name+'/'+file.relative_to(root).as_posix()
                        archive.write(file,relative);verification[relative]=file_identity(file)
                if (root/'AGENTS.md').is_file():
                    file=root/'AGENTS.md';relative=root.name+'/AGENTS.md'
                    archive.write(file,relative);verification[relative]=file_identity(file)
        write_json(args.out/'verification-inputs.json',{'schema':'py-katex-joint-verification-inputs/v1','files':verification},exclusive=True)
    print(json.dumps({key:value['sourceTreeSha256'] for key,value in data.items()}))


if __name__=='__main__':main()
