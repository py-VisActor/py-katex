"""Render retained TeX cases and preserve original native PNG/box evidence."""
from dataclasses import asdict
from pathlib import Path
import argparse,hashlib,json,sys
from collections import Counter
from run_support import write_json
from math_scene_checks import check


def main():
    p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--oracle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--backend',required=True);args=p.parse_args()
    from py_katex import render,ParseError
    fixtures=json.loads(args.fixtures.read_text('utf-8'));args.out.mkdir(parents=True,exist_ok=False);rows=[]
    for case in fixtures['cases']:
        row={'id':case['id'],'status':'FAIL','errors':[]}
        try:
            result=render(case['tex'],font_size=28,display_mode=case.get('display',True),macros=case.get('macros'),backend=args.backend,padding=10,background='white')
            scene=asdict(result.box)
            for command,value in zip(result.box.commands,scene['commands']):value['type']=type(command).__name__
            row['errors']=check(scene,result.data,case)
            (args.out/(case['id']+'.png')).write_bytes(result.data);write_json(args.out/(case['id']+'.json'),scene)
            official=json.loads((args.oracle/(case['id']+'.json')).read_text('utf-8'))
            if official.get('error'):row['errors'].append('official case rejected: '+official['error'])
            row.update(width=result.width,height=result.height,backend=dict(result.backend),sha256=hashlib.sha256(result.data).hexdigest(),status='PASS' if not row['errors'] else 'FAIL')
        except Exception as error:row['errors'].append(type(error).__name__+': '+str(error))
        rows.append(row)
    negatives=[]
    for case in fixtures.get('negativeCases',[]):
        try:render(case['tex'],backend=args.backend);negatives.append({'id':case['id'],'status':'FAIL','error':'invalid TeX accepted'})
        except (ParseError,ValueError) as error:negatives.append({'id':case['id'],'status':'PASS','error':str(error),'code':getattr(error,'code',None)})
    passed=all(x['status']=='PASS' for x in rows+negatives);write_json(args.out/'report.json',{'functionalStatus':'PASS' if passed else 'FAIL','profile':args.backend,'cases':rows,'negativeCases':negatives})
    print(json.dumps({'functionalStatus':'PASS' if passed else 'FAIL','cases':len(rows),'passed':sum(x['status']=='PASS' for x in rows),'failures':[x for x in rows+negatives if x['status']!='PASS']}));return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
