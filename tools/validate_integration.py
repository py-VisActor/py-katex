"""Real Mermaid public-API mathematical graph evidence, no temporary stubs."""
from dataclasses import asdict
from pathlib import Path
import argparse,io,json,math,hashlib
from PIL import Image
from run_support import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--oracle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--backend',required=True);args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    from py_mermaid import render
    from scene_codec import json_ready
    rows=[]
    for case in json.loads(args.fixtures.read_text('utf-8'))['cases']:
        row={'id':case['id'],'status':'FAIL','errors':[]}
        try:
            result=render(case['text'],config=case.get('config'),backend=args.backend)
            events=[e for e in result.trace if e.kind=='math'];glyphs=[e for e in result.trace if e.kind=='math-glyph'];image=Image.open(io.BytesIO(result.data)).convert('RGB')
            if sorted(e.text for e in events)!=sorted(case['maths']):row['errors'].append('mathematical expression denominator/content')
            if [n.id for n in result.diagram.nodes]!=case['nodeIds']:row['errors'].append('graph node identities')
            if [[e.source,e.target] for e in result.diagram.edges]!=case['edges']:row['errors'].append('graph edge relations')
            if case.get('literal') and case['literal'] not in ''.join(e.text or '' for e in result.trace if e.kind=='text'):row['errors'].append('literal SVG-label branch changed')
            for character in case.get('glyphs',''):
                if not any(character in (e.text or '') for e in glyphs):row['errors'].append('missing math glyph '+character)
            for event in events:
                b=event.box
                if b.x<0 or b.y<0 or b.x+b.width>result.width+.01 or b.y+b.height>result.height+.01:row['errors'].append('math clipped by output')
                pixels=image.crop((max(0,math.floor(b.x)),max(0,math.floor(b.y)),min(result.width,math.ceil(b.x+b.width)),min(result.height,math.ceil(b.y+b.height))))
                if sum(min(v)<180 for v in pixels.getdata())<2:row['errors'].append('no actual mathematical pixels')
            source=json.loads((args.oracle/(case['id']+'.json')).read_text('utf-8'));projection=source.get('sourceProjection',source)
            if [n['id'] for n in projection['nodes']]!=case['nodeIds']:row['errors'].append('official graph nodes')
            if [[e['source'],e['target']] for e in projection['edges']]!=case['edges']:row['errors'].append('official graph edges')
            (args.out/(case['id']+'.png')).write_bytes(result.data)
            scene=asdict(result);scene.pop('data')
            write_json(args.out/(case['id']+'.json'),json_ready(scene))
            row.update(width=result.width,height=result.height,backend=dict(result.backend),sha256=hashlib.sha256(result.data).hexdigest(),status='PASS' if not row['errors'] else 'FAIL')
        except Exception as error:row['errors'].append(type(error).__name__+': '+str(error))
        rows.append(row)
    passed=all(r['status']=='PASS' for r in rows);write_json(args.out/'report.json',{'functionalStatus':'PASS' if passed else 'FAIL','profile':args.backend,'cases':rows});print(json.dumps({'status':'PASS' if passed else 'FAIL','cases':len(rows),'bad':[r for r in rows if r['status']!='PASS']}));return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
