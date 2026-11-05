"""Source array/AMS/CD parsing into pure native row and annotation values."""
import math
import re
from .macros import Macro, Token, lex
from .model import ParseError

AMS=frozenset(('align','align*','alignat','alignat*','split','gather','gather*','equation','equation*','CD'))


def environment(p,name,pos):
    from .parser import ENVIRONMENTS,dimension_value
    if name not in ENVIRONMENTS and name!='CD':raise ParseError('Unknown environment '+name,pos,'UNKNOWN_ENVIRONMENT')
    if name in AMS and not p.display_mode:raise ParseError('{'+name+'} can be used only in display mode',pos)
    if name=='CD':return parse_cd(p,pos)
    cols=();specs=();alignat_count=None;left='';right='';stretch=None
    small=name in ('smallmatrix','subarray');cases='cases' in name
    aligned=name in ('align','align*','aligned','split','alignat','alignat*','alignedat')
    gathered=name in ('gather','gather*','gathered');single=name in ('equation','equation*')
    cell_style='script' if small else 'display' if aligned or gathered or single or name.startswith('d') else 'text'
    add_jot=aligned or gathered;hskip=name in ('array','darray')
    separation='small' if name=='smallmatrix' else 'gather' if gathered else 'align' if aligned else None
    auto_tag=None if name in ('aligned','alignedat','split','gathered') or not (aligned or gathered or single) else not name.endswith('*')
    if name in ('array','darray','subarray'):
        pattern=p.string_argument();cols=tuple(c for c in pattern if c!=' ')
        allowed='lc' if name=='subarray' else 'lcr|:'
        if any(c not in allowed for c in cols):raise ParseError('Unknown column alignment',pos)
        if name=='subarray' and len(cols)>1:raise ParseError('subarray can contain only one column',pos)
        specs=tuple(('separator',c) if c in '|:' else ('align',c,None,None) for c in cols)
    elif name.endswith('*') and 'matrix' in name:
        alignment=p.optional_string()
        if alignment is None:alignment='c'
        if alignment not in ('l','c','r'):raise ParseError('Invalid matrix alignment',pos)
        cols=(alignment,)
    elif name in ('alignat','alignat*','alignedat'):
        value=p.string_argument()
        if not re.fullmatch('[0-9]+',value) or len(value)>9 or int(value)<1:raise ParseError('Number of columns should be a positive integer',pos)
        alignat_count=int(value)
        if alignat_count>p.max_nodes:raise ParseError('Column budget exceeded',pos,'MAX_NODES')
    if small:stretch=.5
    elif cases:stretch=1.2
    elif p.g.lookup('\\arraystretch') is not None:
        value=''.join(t.text for t in p.g.expand_tokens([Token('\\arraystretch',pos)]))
        match=re.match(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)',value)
        if not match or not math.isfinite(float(match[1])) or float(match[1])<=0:raise ParseError('Invalid arraystretch',pos)
        stretch=float(match[1])
    if cases:
        cols=('l','l');specs=(('align','l',(0.,'em'),(1.,'em')),('align','l',(0.,'em'),(0.,'em')))
        left,right=('.','}') if 'r' in name else ('{','.')
    else:
        left,right={'pmatrix':('(',')'),'bmatrix':('[',']'),'Bmatrix':('{','}'),'vmatrix':('|','|'),'Vmatrix':('‖','‖')}.get(name.rstrip('*'),('',''))
    rows=[];gaps=[];hlines=[];tags=[] if auto_tag is not None else None
    p.g.begin();p.depth+=1
    if p.depth>p.max_depth:raise ParseError('Depth budget exceeded',pos,'MAX_DEPTH')
    if not single:p.g.define('\\cr',Macro(tuple(lex(r'\\\relax'))))
    def begin_row():
        if auto_tag:p.g.define('\\@eqnsw',Macro(tuple(lex('1'))),True)
    def end_row():
        if tags is not None:
            manual=p.take_tag()
            number=bool(auto_tag and p.g.lookup('\\@eqnsw') and ''.join(t.text for t in p.g.expand_tokens([Token('\\@eqnsw',pos)]))=='1')
            tags.append(manual if manual is not None else number)
    def lines():
        p.skip()
        if p.peek().text=='\\relax':p.take();p.skip()
        while p.peek().text in ('\\hline','\\hdashline'):
            hlines.append((len(rows),p.take().text[1:]));p.skip()
    begin_row();lines();p.g.begin();cell_scope=True
    try:
        while True:
            cells=[]
            while True:
                stops={'&','\\end'} if single else {'&','\\end','\\\\'}
                body=p.expression(stops);p.g.end_group();p.g.begin()
                if aligned and len(cells)%2==1:body.insert(0,p.group())
                cells.append(p.group(body,pos))
                if p.peek().text=='&':
                    maximum=1 if single else 2 if name=='split' else len(cols) if name in ('array','darray') else None
                    if maximum and len(cells)==maximum:
                        if single or aligned:raise ParseError('Too many tab characters: &',p.peek().position)
                        p.handle_strict('textEnv','Too few columns specified in array',p.peek())
                    p.take();continue
                break
            if alignat_count is not None and len(cells)>2*alignat_count:raise ParseError('Too many math columns in alignedat row',pos)
            row=p.make('row',children=cells,position=pos);rows.append(row)
            next_=p.peek()
            if next_.text=='\\end':
                end_row()
                empty=len(cells)==1 and not cells[0].children
                keep_empty=aligned or gathered or single
                tagged=tags is not None and bool(tags[-1])
                if empty and (len(rows)>1 or not keep_empty) and not tagged:
                    rows.pop()
                    if tags is not None:tags.pop()
                p.take();closing=p.string_argument()
                if closing!=name:raise ParseError('Environment mismatch '+name+'/'+closing,next_.position)
                break
            if next_.text!='\\\\':raise ParseError('Expected row separator or end',next_.position)
            p.take()
            # Source optional size is accepted only if no intervening raw space.
            p.flush();gap=None
            if not p.g.tokens or p.g.tokens[0].text!=' ':gap=p.optional_string()
            gaps.append(dimension_value(gap,pos,False) if gap is not None else None)
            end_row();begin_row();lines()
        if name=='subarray' and rows and len(rows[0].children)>1:raise ParseError('subarray can contain only one column',pos)
    finally:
        if cell_scope:p.g.end_group()
        p.g.end_group();p.depth-=1
    if aligned:
        count=2*alignat_count if alignat_count else max((len(row.children) for row in rows),default=0)
        cols=tuple('r' if i%2==0 else 'l' for i in range(count));separation='alignat' if alignat_count else 'align'
        specs=tuple(('align',c,((1. if i>0 and i%2==0 and not alignat_count else 0.),'em'),(0.,'em')) for i,c in enumerate(cols))
    elif gathered:cols=('c',)
    if not cols and 'matrix' in name:cols=('c',)
    if not specs:specs=tuple(('align',c,None,None) for c in cols)
    return p.make('array',children=rows,position=pos,environment=name,cols=cols,col_specs=specs,left=left,right=right,row_gaps=tuple(gaps),hlines=tuple(hlines),tags=None if tags is None else tuple(tags),tag=None,arraystretch=stretch,add_jot=add_jot,hskip_before_after=hskip,col_separation=separation,cell_style=cell_style,leqno=p.leqno)


def parse_cd(p,pos):
    parsed=[];p.g.begin();p.g.define('\\cr',Macro(tuple(lex(r'\\\relax'))));p.g.begin()
    try:
        while True:
            body=p.expression({'\\\\','\\end','&'});parsed.append(body);p.g.end_group();p.g.begin();token=p.take()
            if token.text=='\\end':
                if not body:parsed.pop()
                if p.string_argument()!='CD':raise ParseError('Mismatched CD end',token.position)
                break
            if token.text not in ('&','\\\\'):raise ParseError('Expected CD row separator',token.position)
    finally:p.g.end_group();p.g.end_group()
    rows=[]
    for index,body in enumerate(parsed):
        cells=[];cell=[];i=0
        while i<len(body):
            node=body[i];i+=1
            if node.kind!='symbol' or node.value!='@':cell.append(node);continue
            cells.append(p.group(cell,pos));cell=[]
            if i==len(body):raise ParseError('Missing CD arrow',node.position)
            direction=body[i].get('original',body[i].value);i+=1
            if direction not in ('>','<','A','V','=','|','.'):raise ParseError('Invalid CD arrow '+direction,node.position)
            labels=[[],[]]
            if direction in ('>','<','A','V'):
                for side in range(2):
                    while i<len(body) and not (body[i].kind=='symbol' and body[i].get('original',body[i].value)==direction):
                        if body[i].kind=='symbol' and body[i].value=='@':raise ParseError('Missing CD label terminator '+direction,body[i].position)
                        labels[side].append(body[i]);i+=1
                    if i==len(body):raise ParseError('Missing CD label terminator '+direction,node.position)
                    i+=1
            arrow=p.make('cdarrow',direction,[p.group(labels[0],pos),p.group(labels[1],pos)],node.position)
            cells.append(p.group([arrow],pos))
        if index%2==0:cells.append(p.group(cell,pos))
        elif cells:cells.pop(0)
        rows.append(p.make('row',children=cells,position=pos))
    # Fixed CD source appends its next empty row unconditionally after each
    # parsed row; preserve that source body rather than normalizing it away.
    rows.append(p.make('row',children=(),position=pos))
    count=len(rows[0].children) if rows else 0
    specs=tuple(('align','c',(.25,'em'),(.25,'em')) for _ in range(count))
    return p.make('array',children=rows,position=pos,environment='CD',cols=tuple('c' for _ in range(count)),col_specs=specs,left='',right='',row_gaps=(None,),hlines=(),tags=None,col_separation='CD',cell_style='display',arraystretch=1.,add_jot=True,hskip_before_after=False,leqno=p.leqno)
