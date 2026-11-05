"""Merge fixed source/independent fixtures without consulting native outputs."""
from pathlib import Path
import base64
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SETTING_MAP={'displayMode':'display_mode','leqno':'leqno','fleqn':'fleqn','strict':'strict','trust':'trust',
 'throwOnError':'throw_on_error','errorColor':'error_color','colorIsTextColor':'color_is_text_color',
 'maxSize':'max_size','minRuleThickness':'min_rule_thickness','maxExpand':'max_expand','globalGroup':'global_group','macros':'macros'}
LOGO='.local/upstream-katex/website/static/img/khan-academy.png'


def normalize(item,kind,path):
    result=dict(item)
    native=dict(item.get('options',{}))
    source=dict(item.get('oracleOptions',item.get('settings',{})))
    if kind=='upstream':
        source=dict(item['options']);native={SETTING_MAP[k]:v for k,v in source.items() if k in SETTING_MAP}
    else:
        for key,value in source.items():
            if key in SETTING_MAP:native.setdefault(SETTING_MAP[key],value)
        native.setdefault('display_mode',item.get('display',True))
        if item.get('macros'):native['macros']=item['macros']
    native.setdefault('font_size',item.get('fontSize',28))
    for key,value in native.items():
        reverse=next((name for name,target in SETTING_MAP.items() if target==key),None)
        if reverse:source.setdefault(reverse,value)
    resources=item.get('resources',[])
    if isinstance(resources,dict):
        resources=[{'key':image.get('key',image.get('id')),'dataUri':'data:'+image['mime']+';base64,'+image['dataBase64']} for image in resources.get('images',[])]
    resources=list(resources)
    if 'khan-academy.png' in item['tex']:
        resources.append({'key':'../../website/static/img/khan-academy.png','path':LOGO})
    result.update(options=native,oracleOptions=source,resources=resources,kind=kind,sourceFixture=path,
                  requiredGlyphs=item.get('requiredGlyphs',item.get('glyphs','')))
    if 'html_styles' in native:result['htmlStyles']=dict(native['html_styles'])
    # Source display containers belong to the host. Provide a documented common
    # width for numbered equations rather than screenshot an intrinsic overlap.
    if source.get('displayMode') and (r'\tag' in item['tex'] or any(r'\begin{'+env+'}' in item['tex'] for env in ['align','gather','equation','alignat'])):
        native.setdefault('content_width',700)
    result['sourceInputSha256']=hashlib.sha256(item['tex'].encode()).hexdigest()
    return result


def main():
    files=[('upstream','tests/full-screenshotter-cases.json'),('alpha-regression','tests/cases.json'),
           ('layout','tests/full-layout-cases.json'),('resource','tests/full-resource-cases.json')]
    cases=[];inputs={}
    for kind,relative in files:
        file=ROOT/relative
        data=json.loads(file.read_text('utf-8'))
        inputs[relative]=hashlib.sha256(file.read_bytes()).hexdigest()
        cases.extend(normalize(item,kind,relative) for item in data['cases'])
    supplements=[
      {'id':'full-futurelet','tex':r'\def\foo#1{#1}\futurelet\bar\foo X\bar'},
      {'id':'full-braket-dynamic','tex':r'\Braket{\psi|A|\phi}+\braket{x|y}'},
      {'id':'full-set-dynamic','tex':r'\Set{x\in\mathbb{R}|x>0}'},
      {'id':'full-tag-star-left','tex':r'x+y=1\tag*{A}','options':{'leqno':True,'content_width':480}},
      {'id':'full-ams-numbering','tex':r'\begin{align}a&=1\\b&=2\nonumber\\c&=3\tag{C}\end{align}','options':{'content_width':600}},
      {'id':'full-cd-blank-slot','tex':r'\begin{CD} A @>>> B \\ @VVfV @. \\ C @= D \end{CD}'},
      {'id':'full-minimum-rule','tex':r'\boxed{\frac{1}{2}+\sqrt{x}}','options':{'min_rule_thickness':.12}},
      {'id':'full-size-cap','tex':r'x\rule{5em}{3em}y','options':{'max_size':1.5}},
      {'id':'full-color-compatibility','tex':r'\color{red}{x}+y','options':{'color_is_text_color':True}},
      {'id':'full-visible-rejection','tex':r'a+\unknown_{2}+b','options':{'throw_on_error':False}},
      {'id':'full-css-font-axes','tex':r'\htmlStyle{color:teal;font-size:1.5em;font-weight:bold}{\mathnormal{x}+\mathbf{y}+12}','options':{'trust':True,'strict':False}},
      {'id':'full-source-unicode-runs','tex':r'\text{私たちは नमस्ते БГД}+x','options':{'strict':False}},
      {'id':'full-overflow-container','tex':r'\mathllap{\frac{a+b}{c}}+\smash{\Huge X}+\sqrt{y}','options':{'content_width':25}},
      {'id':'full-emoji-source','tex':'\u270c','options':{'strict':'warn'},'source':'test/unicode-spec.ts: should allow emoji outside strict mode'},
      {'id':'full-emoji-text','tex':'\\text{\u270c}','options':{'strict':'warn'},'source':'test/unicode-spec.ts: text-mode emoji has real color glyphs despite an empty outline'},
    ]
    cases.extend(normalize(item,'full-contract','source functions/macros/settings') for item in supplements)
    ids=[case['id'] for case in cases]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate visual case IDs')
    data={'schema':'py-katex-full-visual-cases/v1','sourceVersion':'0.18.11','sourceCommit':'d5bed9f38a8d747b9c4a12e18897a514707e1c26',
          'inputs':inputs,'cases':cases,'counts':{kind:sum(c['kind']==kind for c in cases) for kind in dict.fromkeys(c['kind'] for c in cases)},
          'sourceHostPolicy':'Original host metadata retained. Core formulas sampled independently; numbered display cases use explicit shared native/source host width.'}
    (ROOT/'tests/full-visual-cases.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'cases':len(cases),'counts':data['counts']}))


if __name__=='__main__':main()
