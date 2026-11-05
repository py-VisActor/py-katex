"""Save five real public-API exports; does not install or publish packages."""
from pathlib import Path
import argparse,hashlib,json
from py_katex import render
from run_support import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    tex=r'x=\frac{-b\pm\sqrt{b^2-4ac}}{2a}'
    samples=[]
    for fmt,header in [('png',b'\x89PNG'),('jpg',b'\xff\xd8'),('webp',b'RIFF'),('svg',b'<'),('pdf',b'%PDF')]:
        result=render(tex,font_size=36,display_mode=True,backend='cpu',format=fmt,background='white',padding=12)
        if not result.data.lstrip().startswith(header):raise ValueError('Invalid native export signature '+fmt)
        file='formula.'+fmt;(args.out/file).write_bytes(result.data);samples.append({'file':file,'mime':result.mime,'width':result.width,'height':result.height,'bytes':len(result.data),'sha256':hashlib.sha256(result.data).hexdigest()})
    (args.out/'formula.tex').write_text(tex+'\n',encoding='utf-8');write_json(args.out/'manifest.json',{'tex':tex,'samples':samples});print(json.dumps({'status':'PASS','exports':samples}))


if __name__=='__main__':main()
