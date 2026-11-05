"""Build the full static acceptance viewer from immutable saved evidence only."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import re
from datetime import datetime,timezone,timedelta

from joint_candidate import current
from run_support import ROOT,file_identity,verify_run,write_json


def read(path):return json.loads(path.read_text('utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['unit','visual','legacy','out']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--manual-receipt',type=Path,action='append',required=True)
    args=parser.parse_args();candidate=read(args.unit/'artifacts/joint-candidate.json')
    if current()!=candidate:raise ValueError('Current joint source differs from validated candidate')
    for run in [args.unit,args.visual,args.legacy]:
        manifest=read(run/'run.json')
        if manifest['status']!='SUCCESS' or not manifest['sourceUnchanged']:raise ValueError('Unstable or failed evidence '+str(run))
        if read(run/'artifacts/joint-candidate.json')!=candidate:raise ValueError('Different joint candidate '+str(run))
        if verify_run(run)['integrityStatus']!='PASS':raise ValueError('Evidence integrity failure '+str(run))
    manual=[]
    for path in args.manual_receipt:
        receipt=read(path)
        if receipt.get('status')!='PASS':raise ValueError('Manual review has unresolved findings '+str(path))
        reviewed=Path(receipt['candidateRun'])
        if not reviewed.is_absolute():reviewed=(ROOT/'test-runs'/reviewed) if reviewed.parent==Path('.') else ROOT/reviewed
        if read(reviewed/'artifacts/joint-candidate.json')!=candidate:raise ValueError('Manual review used a different candidate '+str(path))
        if verify_run(reviewed)['integrityStatus']!='PASS':raise ValueError('Manual candidate integrity failure '+str(path))
        manual.append({'receipt':str(path),'identity':file_identity(path),'candidateRun':str(reviewed)})
    units=read(args.unit/'run.json');counts={}
    for command in units['commands']:
        log=(args.unit/command['stderr']).read_text('utf-8')
        methods=re.findall(r'^Ran (\d+) tests? in ',log,re.M)
        if methods:
            if command['exitCode']!=0 or not re.search(r'^OK\s*$',log,re.M) or re.search(r'\bskipped=',log):raise ValueError('Unit group not fully passed '+command['name'])
            counts[command['name']]=int(methods[-1])
    corpus=read(args.unit/'artifacts/core-native/report.json')
    if corpus['status']!='PASS' or any(row['status']!='PASS' for row in corpus['cases']):raise ValueError('Full source corpus did not pass')
    if any(row['status']=='FAIL' for row in corpus['pairs']) or corpus['sourceCollectorCallbackExceptions']:raise ValueError('Incomplete source corpus/equivalence')
    registration=read(args.unit/'artifacts/full-parser-oracle.json')
    if registration['unexpectedFixtureAcceptance'] or len(registration['cases'])!=684:raise ValueError('Registration oracle denominator mismatch')
    profiles=['cpu','auto','gpu'];rows=[]
    def png(path):
        raw=path.read_bytes()
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid original PNG '+str(path))
        return {'url':'data:image/png;base64,'+base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'path':str(path)}
    fixture=read(ROOT/'tests/full-visual-cases.json');expected={case['id'] for case in fixture['cases']}
    official_manifest=read(args.visual/'artifacts/oracle/manifest.json')
    if official_manifest['inputSha']!=file_identity(ROOT/'tests/full-visual-cases.json')['sha256']:raise ValueError('Visual fixtures changed')
    native={profile:read(args.visual/'artifacts'/('standalone-'+profile)/'report.json') for profile in profiles}
    for profile,result in native.items():
        if result['functionalStatus']!='PASS' or {row['id'] for row in result['cases']}!=expected:raise ValueError('Visual denominator/status '+profile)
    for case in fixture['cases']:
        original=read(args.visual/'artifacts/oracle'/(case['id']+'.json'))
        official=png(args.visual/'artifacts/oracle'/(case['id']+'.png'))
        if original['status']!='PASS' or original['pngSha256']!=official['sha256']:raise ValueError('Official image changed')
        row={'id':case['id'],'kind':case['kind'],'source':case['tex'],'official':official,'profiles':{},
             'sourceFixture':case.get('sourceFixture'),'sourceHostProjection':case.get('hostProjection'),'host':case.get('host',{})}
        for profile in profiles:
            result=next(item for item in native[profile]['cases'] if item['id']==case['id'])
            image=png(args.visual/'artifacts'/('standalone-'+profile)/(case['id']+'.png'))
            if result['status']!='PASS' or image['sha256']!=result['pngSha256']:raise ValueError('Native image changed or failed')
            row['profiles'][profile]={key:result.get(key) for key in ['id','status','width','height','backend','logical','commandCounts','diagnostics']}
            row['profiles'][profile]['image']=image
        rows.append(row)
    diagrams=read(ROOT/'tests/integration-cases.json')['cases']
    graphs={profile:read(args.visual/'artifacts'/('integration-'+profile)/'report.json') for profile in profiles}
    for profile,result in graphs.items():
        if result['functionalStatus']!='PASS' or {row['id'] for row in result['cases']}!={case['id'] for case in diagrams}:raise ValueError('Integration denominator/status '+profile)
    for case in diagrams:
        row={'id':case['id'],'kind':'Mermaid integration','source':case['text'],'official':png(args.visual/'artifacts/integration-oracle'/(case['id']+'.png')),'profiles':{}}
        for profile in profiles:
            result=next(item for item in graphs[profile]['cases'] if item['id']==case['id'])
            image=png(args.visual/'artifacts'/('integration-'+profile)/(case['id']+'.png'))
            if image['sha256']!=result['sha256']:raise ValueError('Integration original PNG changed')
            row['profiles'][profile]={key:result.get(key) for key in ['id','status','width','height','backend']};row['profiles'][profile]['image']=image
        rows.append(row)
    legacy={}
    for name,count in [('f011',12),('f012',35),('f013',50),('f014',200)]:
        positive=read(args.legacy/'artifacts'/name/'cases.json')['cases']
        if len(positive)!=count:raise ValueError('Historical denominator changed '+name)
        for profile in profiles:
            result=read(args.legacy/'artifacts'/name/('compare-'+profile)/'report.json')
            if result['functionalStatus']!='PASS':raise ValueError('Historical validation failed '+name+'/'+profile)
        legacy[name]={'positiveCases':count,'profiles':3,'negativeSourceErrorAndExclusionCategoriesRetained':True}
    exports=[];export_dir=args.visual/'artifacts/exports'
    for sample in read(export_dir/'manifest.json')['samples']:
        raw=(export_dir/sample['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sample['sha256']:raise ValueError('Export bytes changed')
        exports.append({**sample,'url':'data:'+sample['mime']+';base64,'+base64.b64encode(raw).decode()})
    if {Path(item['file']).suffix for item in exports}!={'.png','.jpg','.webp','.svg','.pdf'}:raise ValueError('Five exports missing')
    differences={
      'math-flow-metadata':'固定 Mermaid 元数据预处理把反斜线 n 破坏为换行，A 显示损坏字面量；Python 保留 TeX 并绘制 ν<y。此项是明确修正源异常，不声明与异常 A 图等价。',
      'math-flow-group':'官方 MathML 宿主使用数学斜体 Unicode；原生 TeX 使用指定的粗体正体。数学内容与分组关系保留。',
      'math-flow-mixed':'官方 flex/MathML 宿主折叠公式边界空格，Python 保留文本边界空格；内容与公式一致。',
      'full-layout-tag-leqno-fleqn':'来源行为：在此 fleqn + leqno + tag* 输入中，官方 A 的两个数字坐标相同，原生 B 也保留重叠。已核实内容宽度、字体和编号投影，不是漏绘；人工原图/坐标证据见 math-full-layout-visual-qa-final.json。'}
    summary={'status':'PASS_FULL_CORE_STATIC_LOCAL','tests':{'total':sum(counts.values()),'groups':counts},
       'registry':{'functions':312,'environments':33,'registered':345,'sourceErrorOnly':1,'macros':339,'literalMacros':319,'dynamicMacros':20,'contexts':684},
       'coreCorpus':{'sourceClauses':corpus['sourceClauses'],'expressions':len(corpus['cases']),'expressionCounts':corpus['caseCounts'],'equivalencePairs':len(corpus['pairs']),'scope':corpus['scope']},
       'cases':len(rows),'standaloneCases':len(fixture['cases']),'integrationCases':len(diagrams),'profiles':profiles,'views':len(rows)*3,
       'source':candidate,'knownSourceDifferences':differences,'legacy':legacy,'installationValidation':'DEFERRED_NOT_EXECUTED',
       'manualQA':manual,
       'unitRun':str(args.unit),'visualRun':str(args.visual),'legacyRun':str(args.legacy),
       'scope':'Fixed KaTeX core static rendering; original Jest markup/snapshot predicates, arbitrary DOM/host CSS and standalone contrib plugins are separately classified, not claimed as native parity.',
       'generatedAt':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')}
    template=ROOT/'tools/full_report.html';data={'summary':summary,'rows':rows,'exports':exports}
    html=template.read_text('utf-8').replace('__REPORT_DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'index.html').write_text(html,'utf-8');write_json(args.out/'summary.json',summary)
    inputs=[args.unit/'run.json',args.visual/'run.json',args.legacy/'run.json',ROOT/'tests/full-visual-cases.json',export_dir/'manifest.json',template,Path(__file__),*args.manual_receipt]
    write_json(args.out/'manifest.json',{'html':file_identity(args.out/'index.html'),'candidate':candidate,'inputs':{str(file):file_identity(file) for file in inputs},'renderedDuringGeneration':False,'installationDuringGeneration':False})
    print(json.dumps({'report':str(args.out/'index.html'),'tests':summary['tests']['total'],'views':summary['views'],'sha256':file_identity(args.out/'index.html')['sha256']}))


if __name__=='__main__':main()
