"""Import every locked source YAML case; never generate expectations from math."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    # This is a development data reader, not the math implementation under test.
    sys.path.insert(0,str(ROOT.parent/'py-mermaid/src'))
    from py_mermaid.parsing.yaml_json import load_yaml_json
    source=ROOT/'.local/upstream-katex/test/screenshotter/ss_data.yaml'
    text=source.read_text('utf-8')
    # The source file contains multiline *plain* root scalars (ColorImplicit,
    # Raisebox, Phantom...). Canonicalize that YAML feature explicitly before
    # using the existing development reader; never edit the locked input.
    lines=text.splitlines();normalized=[];rewrites=[];index=0
    while index<len(lines):
        match=re.match(r'^(\w+):\s*(.*)$',lines[index])
        if not match:
            normalized.append(lines[index]);index+=1;continue
        end=index+1
        while end<len(lines) and not re.match(r'^\w+:',lines[end]):end+=1
        value=match[2].strip();following=[line for line in lines[index+1:end] if line.strip() and not line.lstrip().startswith('#')]
        is_mapping=not value and following and re.match(r'^\s+\w+:',following[0])
        if following and not is_mapping and value not in ('|','>','|-','>-','|+','>+'):
            pieces=([value] if value else [])+[line.strip() for line in following]
            normalized.append(match[1]+": '"+' '.join(pieces).replace("'","''")+"'")
            rewrites.append({'name':match[1],'firstLine':index+1,'lastLine':end,'kind':'YAML_plain_scalar_line_folding'})
        else:normalized.extend(lines[index:end])
        index=end
    raw=load_yaml_json('\n'.join(normalized)+'\n')
    original_names=re.findall(r'^(\w+):',text,re.M)
    assert set(raw)==set(original_names) and len(raw)==len(original_names)==128
    source_items={};cases=[]
    for name,value in raw.items():
        item={'tex':value} if isinstance(value,str) else dict(value)
        assert isinstance(item.get('tex'),str),name
        source_items[name]=item
        options={'strict':False,'trust':True,'displayMode':bool(item.get('display',False)),
                 'throwOnError':not bool(item.get('noThrow',False))}
        if item.get('macros'):options['macros']=item['macros']
        if item.get('errorColor'):options['errorColor']=item['errorColor']
        cases.append({'id':'upstream-'+name,'name':name,'tex':item['tex'],'options':options,
                      'source':'test/screenshotter/ss_data.yaml','sourceLine':next(i+1 for i,line in enumerate(text.splitlines()) if line.startswith(name+':')),
                      'host':{key:item[key] for key in ['pre','post','styles','nolatex'] if key in item},
                      'sourceInputSha256':hashlib.sha256(item['tex'].encode()).hexdigest(),
                      'hostProjection':'Core math is compared independently; original pre/post and outer CSS remain inventoried host context, not silently applied to TeX inputs.'})
    data={'schema':'py-katex-upstream-screenshotter/v1','sourceVersion':'0.18.11','sourceCommit':'d5bed9f38a8d747b9c4a12e18897a514707e1c26',
          'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'count':128,'cases':cases,'sourceItems':source_items,'plainScalarRewrites':rewrites}
    (ROOT/'tests/full-screenshotter-cases.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'cases':len(cases),'sourceSha256':data['sourceSha256'],'hostContextCases':sum(bool(item['host']) for item in cases)}))


if __name__=='__main__':main()
