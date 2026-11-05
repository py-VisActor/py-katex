"""Build a self-contained HTML viewer from saved, verified native/oracle PNGs."""
from pathlib import Path
import argparse,base64,hashlib,json
from datetime import datetime,timezone,timedelta
from run_support import ROOT,write_json,file_identity
from joint_candidate import current


def main():
    p=argparse.ArgumentParser();p.add_argument('--visual',type=Path,required=True);p.add_argument('--unit',type=Path,required=True);p.add_argument('--legacy',type=Path,required=True);p.add_argument('--exports',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    def read(path):return json.loads(path.read_text('utf-8'))
    candidate=read(args.visual/'artifacts/joint-candidate.json')
    if current()!=candidate:raise ValueError('Joint source changed before report')
    for run in [args.visual,args.unit,args.legacy]:
        manifest=read(run/'run.json')
        if manifest['status']!='SUCCESS' or not manifest['sourceUnchanged']:raise ValueError('Unstable/failed evidence '+str(run))
        if read(run/'artifacts/joint-candidate.json')!=candidate:raise ValueError('Different candidate '+str(run))
    units=read(args.unit/'run.json');import re
    counts={}
    for cmd in units['commands']:
        log=(args.unit/cmd['stderr']).read_text('utf-8')
        matches=re.findall(r'^Ran (\d+) tests? in ',log,re.M)
        if matches:
            if cmd.get('exitCode')!=0 or not re.search(r'^OK\s*$',log,re.M):raise ValueError('Unit group failed')
            counts[cmd['name']]=int(matches[-1])
    profiles=['cpu','auto','gpu'];rows=[]
    def png(path):
        raw=path.read_bytes()
        if raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Not PNG '+str(path))
        return {'url':'data:image/png;base64,'+base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'path':str(path)}
    for kind,name,oracle in [('standalone','cases.json','oracle'),('integration','integration-cases.json','integration-oracle')]:
        fixture=read(ROOT/'tests'/name)
        results={profile:read(args.visual/'artifacts'/(kind+'-'+profile)/'report.json') for profile in profiles}
        for profile,result in results.items():
            if result['functionalStatus']!='PASS' or {r['id'] for r in result['cases']}!={c['id'] for c in fixture['cases']}:raise ValueError('Visual denominator or status mismatch')
        for case in fixture['cases']:
            row={'id':case['id'],'kind':kind,'source':case.get('tex',case.get('text')),'official':png(args.visual/'artifacts'/oracle/(case['id']+'.png')),'profiles':{}}
            for profile in profiles:
                result=next(r for r in results[profile]['cases'] if r['id']==case['id']);image=png(args.visual/'artifacts'/(kind+'-'+profile)/(case['id']+'.png'))
                if image['sha256']!=result['sha256']:raise ValueError('Native image changed after comparison')
                row['profiles'][profile]={**result,'image':image}
            rows.append(row)
    exports=[]
    for sample in read(args.exports/'manifest.json')['samples']:
        raw=(args.exports/sample['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sample['sha256']:raise ValueError('Export bytes changed')
        exports.append({**sample,'url':'data:'+sample['mime']+';base64,'+base64.b64encode(raw).decode()})
    differences={
      'math-flow-metadata':'上游 Mermaid metadata 流程把反斜线 n 改为真实换行，官方图显示损坏的字面量。Python 保留 TeX 并绘制 ν<y；此项不声明上游画面等价。',
      'math-flow-group':'官方 MathML 宿主呈数学斜体 Unicode，Python 使用 TeX 指定的粗体直立字体；保留数学内容与分组关系。',
      'math-flow-mixed':'官方 flex/MathML 宿主折叠公式边界空格，Python 保留一处文本空格；内容与公式一致。'}
    summary={'status':'PASS_NATIVE_STATIC','tests':{'total':sum(counts.values()),'groups':counts},'cases':len(rows),'standaloneCases':61,'integrationCases':8,'profiles':profiles,'source':candidate,'knownSourceDifferences':differences,'installationValidation':'NOT_EXECUTED','legacyRun':str(args.legacy),'visualRun':str(args.visual),'unitRun':str(args.unit),'generatedAt':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')}
    data={'summary':summary,'rows':rows,'exports':exports}
    template=ROOT/'tools/math_report.html';html=template.read_text('utf-8').replace('__REPORT_DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'index.html').write_text(html,encoding='utf-8');write_json(args.out/'summary.json',summary)
    write_json(args.out/'manifest.json',{'html':file_identity(args.out/'index.html'),'candidate':candidate,'inputs':{str(p):file_identity(p) for p in [args.visual/'run.json',args.unit/'run.json',args.legacy/'run.json',args.exports/'manifest.json',template,Path(__file__)]},'renderedDuringGeneration':False,'installationDuringGeneration':False})
    print(json.dumps({'report':str(args.out/'index.html'),'tests':sum(counts.values()),'cases':len(rows),'sha256':file_identity(args.out/'index.html')['sha256']}))


if __name__=='__main__':main()
