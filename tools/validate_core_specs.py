"""Validate the independent source corpus against native public math entry points.

Source callbacks are replayed as explicit Python test adapters with recorded
decisions/actions. No JavaScript or source-code string is executed by Python.
"""
from pathlib import Path
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
from html.parser import HTMLParser
import json
import math
import re
import sys
import traceback
import warnings

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT.parent/'py-mermaid/src')]
from py_katex import Options,Token,Macro,ParseError,typeset,parse
from py_katex.canvas import render_box
from full_visual_support import options_for_case,pure

SETTINGS={'displayMode':'display_mode','leqno':'leqno','fleqn':'fleqn','strict':'strict','trust':'trust',
 'throwOnError':'throw_on_error','errorColor':'error_color','colorIsTextColor':'color_is_text_color',
 'maxSize':'max_size','minRuleThickness':'min_rule_thickness','maxExpand':'max_expand','globalGroup':'global_group','macros':'macros'}


def restore(value):
    if isinstance(value,list):return [restore(item) for item in value]
    if isinstance(value,dict):
        if value.get('__callback'):raise ValueError('Unadapted source callback')
        if 'text' in value and set(value)<= {'text','noexpand','treatAsRelax','loc','position','source_comment','end','treat_as_relax'}:
            return Token(value['text'],value.get('position',0),value.get('noexpand',False),value.get('treatAsRelax',value.get('treat_as_relax',False)))
        return {key:restore(item) for key,item in value.items()}
    return value


class CallbackReplay:
    def __init__(self,rows,kind):self.rows=rows;self.kind=kind;self.index=0
    def __call__(self,*args):
        if self.index>=len(self.rows):raise AssertionError('Unexpected '+self.kind+' callback')
        row=self.rows[self.index];self.index+=1
        expected=row['args']
        if self.kind=='strict':
            if args[0]!=expected[0]:raise AssertionError('Strict diagnostic code mismatch: '+str((args[0],expected[0])))
        else:
            if args[0]!=expected[0]:raise AssertionError('Trust context mismatch: '+str((args[0],expected[0])))
        if row.get('error'):raise RuntimeError(row['error'])
        return restore(row.get('result'))
    def complete(self):
        if self.index!=len(self.rows):raise AssertionError('Missing '+self.kind+' callbacks')


class MacroReplay:
    def __init__(self,calls):self.calls=calls;self.index=0
    def __call__(self,context):
        if self.index>=len(self.calls):raise AssertionError('Unexpected user macro callback')
        call=self.calls[self.index];self.index+=1
        for action in call['actions']:
            target=context
            components=action['method'].split('.')
            for name in components[:-1]:target=getattr(target,name)
            getattr(target,components[-1])(*restore(action['args']))
        if call.get('error'):raise RuntimeError(call['error'])
        return restore(call.get('result'))
    def complete(self):
        if self.index!=len(self.calls):raise AssertionError('Missing user macro callbacks')


def source_assets(value):
    found=set();pending=[value]
    class Images(HTMLParser):
        def handle_starttag(self,tag,attrs):
            if tag in ('img','mglyph'):
                src=dict(attrs).get('src')
                if src:found.add(src)
    while pending:
        item=pending.pop()
        if isinstance(item,dict):
            if isinstance(item.get('src'),str):found.add(item['src'])
            pending.extend(item.values())
        elif isinstance(item,list):pending.extend(item)
        elif isinstance(item,str) and ('<img' in item or '<mglyph' in item):Images(convert_charrefs=True).feed(item)
    return [{'key':key,'path':'.local/upstream-katex/website/static/img/khan-academy.png'} for key in sorted(found)]


def native_config(case):
    values={};replayers=[]
    for name,value in case['options'].items():
        if name not in SETTINGS:continue
        if name in ('strict','trust') and isinstance(value,dict) and value.get('__callback'):
            value=CallbackReplay(case[name+'Decisions'],name);replayers.append(value)
        elif name=='macros':
            macros={}
            for key,definition in value.items():
                if isinstance(definition,dict) and definition.get('__callback'):
                    callback=MacroReplay(case.get('macroCalls',{}).get(key,[]));replayers.append(callback);macros[key]=callback
                else:macros[key]=restore(definition)
            value=macros
        elif name in {'displayMode','leqno','fleqn','throwOnError','colorIsTextColor','globalGroup'}:
            # The source YAML screenshotter uses numeric 0/1; this explicit
            # source-to-Python adapter preserves JS boolean control semantics.
            value=not (value is None or value is False or isinstance(value,(int,float)) and (value==0 or math.isnan(value)) or value=='')
        elif name in {'maxSize','minRuleThickness','maxExpand'} and value in ('Infinity','-Infinity','NaN'):
            value={'Infinity':math.inf,'-Infinity':-math.inf,'NaN':math.nan}[value]
        else:value=restore(value)
        values[SETTINGS[name]]=value
    return options_for_case({'options':values,'resources':source_assets(case.get('result'))}),replayers


def parse_kwargs(config):
    return {name:getattr(config,name) for name in ['max_expand','max_depth','max_nodes','trust','display_mode','strict','color_is_text_color','global_group','error_color','macro_state','leqno','throw_on_error']}|{'macros':dict(config.macros)}


def normalized(value):
    if isinstance(value,float):return round(value,7)
    if isinstance(value,dict):return {key:normalized(item) for key,item in value.items() if key not in {'diagnostics'}}
    if isinstance(value,list):return [normalized(item) for item in value]
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();corpus=json.loads(args.corpus.read_text('utf-8'));args.out.mkdir(parents=True,exist_ok=False)
    results=[];by_id={case['id']:case for case in corpus['cases']};boxes={};counts=Counter()
    for case in corpus['cases']:
        row={'id':case['id'],'source':case['source'],'title':case['title'],'expected':case['status'],'status':'FAIL','errors':[]}
        try:
            config,replayers=native_config(case)
            with warnings.catch_warnings(record=True) as notes:
                warnings.simplefilter('always')
                try:
                    value=parse(case['tex'],**parse_kwargs(config)) if case['action']=='parse' else typeset(case['tex'],options=config)
                    row['nativeStatus']='ERROR_RENDERED' if getattr(value,'diagnostics',()) and any(d.severity=='error' for d in value.diagnostics) else 'ACCEPT'
                    if case['status'] in {'REJECT','REJECT_INVALID_INPUT','SOURCE_EXCEPTION'}:row['errors'].append('Source rejects input but native accepts')
                    if case['status']=='ERROR_RENDERED' and not getattr(value,'diagnostics',()):row['errors'].append('Visible error rendering lost diagnostic')
                    if case['action']=='build':boxes[case['id']]=value
                except Exception as error:
                    row['nativeStatus']='REJECT';row['nativeError']={'type':type(error).__name__,'code':getattr(error,'code',None),'message':str(error),'position':getattr(error,'position',None),'utf16Position':getattr(error,'utf16_position',None)}
                    if case['status'] in {'ACCEPT','ERROR_RENDERED'}:row['errors'].append('Native rejected source-accepted expression')
                    elif isinstance(error,(AssertionError,AttributeError,KeyError,IndexError,RecursionError)):row['errors'].append('Native/tool internal exception instead of source diagnostic')
                row['warnings']=[str(note.message) for note in notes]
                # Native wording/offset units are adapted, but each source
                # strict report must have a corresponding diagnostic event.
                source_codes=Counter(code for message in case['warnings'] for code in re.findall(r'\[([A-Za-z][\w-]*)\]',message))
                native_codes=Counter(code for note in notes for code in re.findall(r'\[([A-Za-z][\w-]*)\]',str(note.message)))
                if source_codes!=native_codes:row['errors'].append('Source/native strict warning codes differ: '+str((source_codes,native_codes)))
            for replay in replayers:replay.complete()
            row['status']='PASS' if not row['errors'] else 'FAIL'
        except Exception as error:
            row['status']='TOOL_ERROR';row['errors'].append(str(error));row['traceback']=traceback.format_exc()
        counts[row['status']]+=1;results.append(row)
    pair_results=[]
    for pair in corpus['pairs']:
        row={**pair,'status':'FAIL'}
        try:
            if not pair['expectedEquivalent']:
                row.update(status='SOURCE_INTERNAL_TREE_INEQUALITY',scope='Native AST is intentionally different; source negative tree-shape predicate is inventoried, not counted as visual equivalence')
            else:
                values=[]
                for key in ['left','right']:
                    case=by_id[pair[key]]
                    if pair[key] in boxes:values.append(boxes[pair[key]]);continue
                    config,_=native_config(case)
                    with warnings.catch_warnings():warnings.simplefilter('ignore');values.append(typeset(case['tex'],options=config))
                a,b=values;metrics_equal=all(abs(getattr(a,key)-getattr(b,key))<1e-6 for key in ('width','height','depth'))
                signature_equal=normalized(pure(a))==normalized(pure(b))
                if not signature_equal:
                    first=render_box(a,backend='cpu',background='white').data;second=render_box(b,backend='cpu',background='white').data
                    signature_equal=first==second
                    if not signature_equal:
                        (args.out/(pair['left']+'-pair-a.png')).write_bytes(first);(args.out/(pair['left']+'-pair-b.png')).write_bytes(second)
                row.update(status='PASS' if metrics_equal and signature_equal else 'FAIL',metricsEqual=metrics_equal,paintEqual=signature_equal)
        except Exception as error:row.update(status='FAIL',error=str(error),traceback=traceback.format_exc())
        pair_results.append(row)
    failures=[row for row in results if row['status']!='PASS'];pair_failures=[row for row in pair_results if row['status']=='FAIL']
    incomplete=corpus['summary']['callbackExceptions']
    report={'schema':'py-katex-core-corpus-validation/v1','status':'PASS' if not failures and not pair_failures and not incomplete else 'FAIL',
            'inputSha256':hashlib.sha256(args.corpus.read_bytes()).hexdigest(),'caseCounts':dict(counts),'cases':results,'pairs':pair_results,
            'sourceClauses':len(corpus['clauses']),'sourceCollectorCallbackExceptions':corpus['summary']['callbackExceptions'],
            'scope':'Native acceptance/rejection, diagnostics/decision callbacks and positive visual equivalence. Not original Jest assertion parity.',
            'resourceProjection':'Source structural image tests with placeholder URLs receive an explicitly injected fixed reference PNG; no production network or implicit file fallback.'}
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'status':report['status'],'cases':len(results),'caseCounts':dict(counts),'pairs':len(pair_results),'pairFailures':len(pair_failures)}))
    return 1 if failures or pair_failures or incomplete else 0


if __name__=='__main__':raise SystemExit(main())
