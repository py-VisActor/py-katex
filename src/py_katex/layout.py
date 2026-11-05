"""Native-independent TeX box layout, ported from pinned KaTeX 0.18.11.

Coordinates are logical pixels, with a downward y axis and baseline origin.
The browser's span/vlist machinery is replaced by immutable boxes, not text
substitution. Source metric and path tables are shipped package resources.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.resources import files
import json
import math
import re
from .model import CommandGroup, Diagnostic, Glyph, ImageCommand, MathBox, Node, Options, ParseError, Path, Rule

_MULT = (.5,.6,.7,.8,.9,1.,1.2,1.44,1.728,2.074,2.488)
_SIZES = ((1,1,1),(2,1,1),(3,1,1),(4,2,1),(5,2,1),(6,3,1),(7,4,2),(8,6,3),(9,7,6),(10,8,7),(11,10,9))
_SUP = (4,5,4,5,6,7,6,7)
_SUB = (5,5,5,5,7,7,7,7)
_NUM = (2,3,4,5,6,7,6,7)
_DEN = (3,3,5,5,7,7,7,7)
_TEXT = (0,1,2,3,2,3,2,3)
_STYLE = {'display':0,'text':2,'script':4,'scriptscript':6}
_SIZE = dict(zip(('tiny','sixptsize','scriptsize','footnotesize','small','normalsize','large','Large','LARGE','huge','Huge'), range(1,12)))
_SPACING = {
 'mord':{'mop':3,'mbin':4,'mrel':5,'minner':3},
 'mop':{'mord':3,'mop':3,'mrel':5,'minner':3},
 'mbin':{'mord':4,'mop':4,'mopen':4,'minner':4},
 'mrel':{'mord':5,'mop':5,'mopen':5,'minner':5},
 'mopen':{},'mclose':{'mop':3,'mbin':4,'mrel':5,'minner':3},
 'mpunct':{'mord':3,'mop':3,'mrel':3,'mopen':3,'mclose':3,'mpunct':3,'minner':3},
 'minner':{'mord':3,'mop':3,'mbin':4,'mrel':5,'mopen':3,'mpunct':3,'minner':3},
}
_TIGHT = {'mord':{'mop':3},'mop':{'mord':3,'mop':3},'mclose':{'mop':3},'minner':{'mop':3}}
_FONTS = {'mathrm':'Main-Regular','mathnormal':'Math-Italic','mathit':'Main-Italic',
 'mathbf':'Main-Bold','boldsymbol':'Math-BoldItalic','mathbb':'AMS-Regular',
 'mathcal':'Caligraphic-Regular','mathfrak':'Fraktur-Regular','mathscr':'Script-Regular',
 'mathsf':'SansSerif-Regular','mathtt':'Typewriter-Regular',
 'textrm':'Main-Regular','textnormal':'Main-Regular','textup':'Main-Regular',
 'textbf':'Main-Bold','textit':'Main-Italic','textsf':'SansSerif-Regular',
 'texttt':'Typewriter-Regular','text':'Main-Regular','mbox':'Main-Regular','hbox':'Main-Regular',
 'textmd':'Main-Regular','emph':'Main-Italic','mathsfit':'SansSerif-Italic','bm':'Math-BoldItalic'}

@lru_cache(maxsize=None)
def _data(name):
    return json.loads(files('py_katex').joinpath('data', name+'.json').read_text(encoding='utf-8'))

@dataclass(frozen=True)
class _Context:
    base: float
    style: int = 2
    text_size: int = 6
    font: str = ''
    color: str = '#000000'
    mode: str = 'math'
    text_family: str = 'Main'
    text_weight: str = ''
    text_shape: str = ''
    text_family_explicit: bool = False
    css_family: str|None = None
    css_weight: str|None = None
    css_shape: str|None = None
    css_line_height: str = '1.2'
    max_size: float = math.inf
    min_rule_thickness: float = 0.
    content_width: float|None = None
    leqno: bool = False
    fleqn: bool = False
    equation_counter: int = 0
    resources: object = None
    html_styles: tuple = ()
    error_color: str = '#cc0000'
    native_options: Options|None = None
    counter: list|None = None
    @property
    def size_index(self):
        level = self.style//2
        return self.text_size if level<2 else _SIZES[self.text_size-1][level-1]
    @property
    def em(self): return self.base*_MULT[self.size_index-1]
    def metric(self, name):
        index = 0 if self.size_index>=5 else 1 if self.size_index>=3 else 2
        return _data('global_metrics')[name][index]*self.em
    def styled(self, style): return replace(self,style=style)
    def rule(self,name='defaultRuleThickness'):
        return max(self.metric(name),self.min_rule_thickness*self.em)
    def dim(self, value):
        return min(self._dimension(value),self.max_size*self.em)
    def _dimension(self, value):
        if value is None: return 0.
        if isinstance(value,(float,int)): return float(value)*self.em
        number,unit = value
        number=float(number)
        if unit=='mu': return number*self.metric('quad')/18
        if unit in ('em','ex'):
            text=self.styled(_TEXT[self.style])
            return number*text.metric('quad' if unit=='em' else 'xHeight')
        pt={'pt':1,'mm':7227/2540,'cm':7227/254,'in':72.27,'bp':803/800,
            'pc':12,'dd':1238/1157,'cc':14856/1157,'nd':685/642,'nc':1370/107,
            'sp':1/65536,'px':803/800}
        if unit not in pt: raise ParseError(f'Unsupported dimension unit {unit}',code='UNSUPPORTED_UNIT')
        return number*pt[unit]*self.base/10

def _move(box, x=0., y=0.):
    return tuple(replace(c,x=c.x+x,y=c.y+y) for c in box.commands)

def _pack(items, width=None, atom='mord', italic=0.,skew=0.):
    """Compose (box,x,baseline) triples; height/depth include shifted ink."""
    items=tuple(items)
    return MathBox(max((x+b.width for b,x,y in items),default=0.) if width is None else width,
                   max((b.height-y for b,x,y in items),default=0.),
                   max((b.depth+y for b,x,y in items),default=0.),
                   tuple(c for b,x,y in items for c in _move(b,x,y)),atom,italic,skew,
                   tuple(d for b,x,y in items for d in b.diagnostics))

def _rule(width, thickness, ctx, top=0.):
    return MathBox(width,-top,top+thickness,
                   (Rule(0.,top,width,thickness,ctx.color),))

def _source_record(font,text,mode):
    """fontMetrics.getCharacterMetrics, including its explicit estimates."""
    from .layout_metrics import EXTRA_CHARACTER_MAP,SUPPORTED_BLOCKS
    table=_data('font_metrics').get(font,{})
    record=table.get(str(ord(text)))
    if record is None and text in EXTRA_CHARACTER_MAP:record=table.get(str(ord(EXTRA_CHARACTER_MAP[text])))
    if record is None and mode=='text' and any(lo<=ord(text)<=hi for lo,hi in SUPPORTED_BLOCKS):record=table.get('77')
    return record

def _char(value,ctx,atom='mord',font=None,mode=None,original=None,position=0):
    mode=mode or ctx.mode
    symbols=_data('symbols').get(mode,{})
    entry=symbols.get(original or value,{}) or symbols.get(value,{})
    text=entry.get('replace') or value
    if len(text)!=1:
        raise ParseError(f'Glyph token is not one source symbol: {value!r}',code='UNSUPPORTED_GLYPH')
    selected=font or ctx.font
    if font is None and atom in ('mbin','mrel','mopen','mclose','mpunct','minner'):
        # mathsym, unlike makeOrd, honours boldsymbol but not alphabet-only
        # commands such as mathbf/mathit for operator and relation glyphs.
        if ctx.font=='Math-BoldItalic' and str(ord(text)) in _data('font_metrics')['Main-Bold']:selected='Main-Bold'
        else:selected='AMS-Regular' if entry.get('font')=='ams' else 'Main-Regular'
    if selected=='Math-BoldItalic' and entry.get('group')=='textord':selected='Main-Bold'
    if not selected:
        if entry.get('font')=='ams': selected='AMS-Regular'
        elif mode=='math' and entry.get('group')=='mathord': selected='Math-Italic'
        else:
            suffix='BoldItalic' if ctx.text_weight and ctx.text_shape else 'Bold' if ctx.text_weight else 'Italic' if ctx.text_shape else 'Regular'
            selected=(ctx.text_family if mode=='text' else 'Main')+'-'+suffix
    metrics=_data('font_metrics')
    if selected not in metrics:raise ParseError(f'Font metrics not found for font: {selected}',code='MISSING_FONT_METRICS')
    record=_source_record(selected,text,mode)
    # KaTeX's makeOrd falls back from requested math alphabets to Main.
    if record is None and atom=='mord':
        selected='Main-Bold' if selected=='Math-BoldItalic' else 'Math-Italic' if mode=='math' and entry.get('group')=='mathord' else 'Main-Regular'
        record=_source_record(selected,text,mode)
    if record is None:
        import warnings
        from .model import MathWarning
        from .macros import Token
        message=f"No character metrics for '{text}' in style '{selected}' and mode '{mode}'"
        behavior=(ctx.native_options or Options()).strict
        if callable(behavior):behavior=behavior('symbolNotInFont',message,Token(original or value,position))
        if behavior is True or behavior=='error':raise ParseError(message+' [symbolNotInFont]',position,'STRICT_symbolNotInFont')
        if behavior is not False and behavior!='ignore':warnings.warn(message+' [symbolNotInFont]',MathWarning,stacklevel=3)
    if ord(text)>127 and str(ord(text)) not in metrics.get(selected,{}):
        return _fallback_text(text,ctx,atom,selected,mode,report_missing=False)
    if record is None:
        raise ParseError(f'No source metric for {text!r} in {selected}',code='MISSING_GLYPH_METRIC')
    depth,height,italic,skew,width=record
    paint_font,paint_style,paint_weight=_paint_settings(selected,ctx,mode,atom,entry,font)
    advance=width*ctx.em
    if paint_font!=selected or paint_style is not None or paint_weight is not None:
        from .canvas import measure_bundled_text
        advance=measure_bundled_text(text,paint_font,ctx.em,style=paint_style,weight=paint_weight)['width']
    return MathBox(advance,height*ctx.em,depth*ctx.em,
                   (Glyph(text,0.,0.,paint_font,ctx.em,ctx.color,font_style=paint_style,font_weight=paint_weight),),atom,
                   0. if mode=='text' or ctx.font=='Main-Italic' else italic*ctx.em,skew*ctx.em)

def _paint_settings(font,ctx,mode='text',atom='mord',entry=None,explicit_font=None):
    """Apply outer CSS hints after source-generated glyph classes, per axis."""
    if ctx.css_family is None and ctx.css_weight is None and ctx.css_shape is None:return font,None,None
    entry=entry or {};family,suffix=font.rsplit('-',1)
    family=ctx.css_family or family
    weight=ctx.css_weight or ('700' if 'Bold' in suffix else '400')
    shape=ctx.css_shape or ('italic' if 'Italic' in suffix else 'normal')
    mathsym=mode=='math' and atom in ('mbin','mrel','mopen','mclose','mpunct','minner')
    forced=explicit_font or ctx.font
    if font.startswith('Size'):family=font.split('-')[0]
    elif mathsym:
        if ctx.font=='Math-BoldItalic' and font=='Main-Bold':family='Main';weight='700'
        elif entry.get('font')=='ams':family='AMS'
    elif forced:
        base=forced.split('-')[0]
        if forced=='Main-Regular':shape='normal'  # .mathrm: no family declaration
        elif forced=='Main-Bold':family='Main';weight='700'
        elif forced=='Main-Italic':family='Main';shape='italic'
        elif forced=='Math-Italic':family='Math';shape='italic'
        elif forced=='Math-BoldItalic':
            family='Main' if font=='Main-Bold' else 'Math';weight='700'
            if family=='Math':shape='italic'
        else:family=base
    elif mode=='math' and entry.get('group')=='mathord':family='Math';shape='italic'
    elif entry.get('font')=='ams':family='AMS'
    if ctx.text_family_explicit and mode=='text' and not ctx.font:family=ctx.text_family
    if ctx.text_weight:weight='700'
    if ctx.text_shape:shape='italic'
    bold=float(weight)>=600;italic=shape in ('italic','oblique')
    candidates=[family+'-'+('BoldItalic' if bold and italic else 'Bold' if bold else 'Italic' if italic else 'Regular')]
    if italic:candidates.append(family+'-Italic')
    if bold:candidates.append(family+'-Bold')
    candidates.append(family+'-Regular')
    available=set(_data('font_metrics'))|{'Caligraphic-Bold','Fraktur-Bold'}
    face=next((face for face in candidates if face in available),None)
    if face is None:raise ParseError('Unsupported CSS mathematical family '+family,code='UNSUPPORTED_FONT')
    return face,shape,weight

def _fallback_text(text,ctx,atom='mord',font='',mode='text',report_missing=True):
    from .canvas import measure_fallback
    metric_font=font or ctx.font or ctx.text_family+'-'+('BoldItalic' if ctx.text_weight and ctx.text_shape else 'Bold' if ctx.text_weight else 'Italic' if ctx.text_shape else 'Regular')
    paint_font,paint_style,paint_weight=_paint_settings(metric_font,ctx,mode,atom)
    if report_missing:
        # _text_runs can enter here without going through _char. Preserve
        # makeSymbol's strict reporting before measuring a native text run.
        import warnings
        from .model import MathWarning
        from .macros import Token
        for char in text:
            if _source_record(metric_font,char,mode) is not None:continue
            message=f"No character metrics for '{char}' in style '{metric_font}' and mode '{mode}'"
            behavior=(ctx.native_options or Options()).strict
            if callable(behavior):behavior=behavior('symbolNotInFont',message,Token(char,0))
            if behavior is True or behavior=='error':raise ParseError(message+' [symbolNotInFont]',0,'STRICT_symbolNotInFont')
            if behavior is not False and behavior!='ignore':warnings.warn(message+' [symbolNotInFont]',MathWarning,stacklevel=3)
    measured=measure_fallback(text,ctx.native_options or Options(font_size=ctx.base),ctx.em,
                              font=paint_font,style=paint_style or ('italic' if ctx.text_shape or 'Italic' in paint_font else 'normal'),
                              weight=paint_weight or ('bold' if ctx.text_weight or 'Bold' in paint_font else 'normal'))
    source=[]
    for char in text:
        record=_source_record(metric_font,char,mode)
        if record is not None:source.append(record)
    # Browser text advance comes from actual font shaping; TeX vertical
    # calculations retain getCharacterMetrics' explicit source estimates.
    height=max((record[1] for record in source),default=0.)*ctx.em
    depth=max((record[0] for record in source),default=0.)*ctx.em
    return MathBox(measured['width'],height,depth,
                   (Glyph(text,0.,0.,measured['font'],ctx.em,ctx.color,font_resource=measured['font_resource']),),
                   atom,measured.get('italic',0.),measured.get('skew',0.))

def _fragments(seq,local):
    for node in seq:
        if node.kind=='group' and node.get('semisimple',False):yield from _fragments(node.children,local)
        elif node.kind in ('color','style','size'):
            inner=node.children[0].children if len(node.children)==1 and node.children[0].kind=='group' else node.children
            if node.kind=='color':nextctx=replace(local,color=node.value)
            elif node.kind=='style':
                nextctx=local.styled(_STYLE[node.value]+bool(node.get('cramped',False)))
                if node.get('reset_font',False):nextctx=replace(nextctx,font='',mode='math')
            else:nextctx=replace(local,text_size=_SIZE[node.value],style=_TEXT[local.style])
            yield from _fragments(inner,nextctx)
        else:yield node,local

def _row(nodes,ctx, build):
    entries=_text_runs(tuple(_fragments(nodes,ctx)))
    gluectx=entries[0][1] if len(nodes)==1 and nodes[0].kind in ('style','size') and entries else ctx
    if any(n.kind=='linebreak' for n,c in entries):
        lines=[];current=[];gaps=[]
        for n,c in entries:
            if n.kind=='linebreak':lines.append(_row_boxes(current,ctx));gaps.append(c.dim(n.get('gap')));current=[]
            else:current.append(build(n,c))
        lines.append(_row_boxes(current,ctx));items=[];baseline=0.
        for i,b in enumerate(lines):
            if i:baseline+=max(1.2*ctx.em,lines[i-1].depth+b.height)+gaps[i-1]
            items.append((b,0.,baseline))
        return _pack(items,max((b.width for b in lines),default=0.))
    return _row_boxes([build(n,c) for n,c in entries],gluectx,contexts=[c for n,c in entries])

def _text_runs(entries):
    """Combine fallback text clusters, never mathematical expressions."""
    # Symbol lookup precedes tryCombineChars. Typewriter makeOrd first
    # deconstructs unavailable multi-character ligatures, then looks up
    # their individual quotes/dashes; verb also uses per-character lookup.
    expanded=[]
    for node,ctx in entries:
        if node.kind=='symbol' and node.get('mode',ctx.mode)=='text':
            original=node.get('original',node.value)
            face=ctx.font or ctx.text_family+'-'+('BoldItalic' if ctx.text_weight and ctx.text_shape else 'Bold' if ctx.text_weight else 'Italic' if ctx.text_shape else 'Regular')
            values=tuple(original) if face.startswith('Typewriter-') and original in ('--','---','``',"''") else (original,)
            for value in values:
                entry=_data('symbols')['text'].get(value,{})
                replacement=entry.get('replace') or (value if len(values)>1 else node.value)
                attrs=tuple((k,v) for k,v in node.attrs if k!='original')+(('original',value),)
                expanded.append((replace(node,value=replacement,attrs=attrs),ctx))
        else:expanded.append((node,ctx))
    entries=tuple(expanded)
    def fallback(node,ctx):
        if node.kind!='symbol' or node.get('mode',ctx.mode)!='text' or len(node.value)!=1:return False
        if ord(node.value)<128:return False
        font=ctx.font or ('AMS-Regular' if node.get('font')=='ams' else ctx.text_family+'-'+('BoldItalic' if ctx.text_weight and ctx.text_shape else 'Bold' if ctx.text_weight else 'Italic' if ctx.text_shape else 'Regular'))
        return str(ord(node.value)) not in _data('font_metrics').get(font,{})
    output=[];index=0
    while index<len(entries):
        node,ctx=entries[index]
        if not fallback(node,ctx):output.append((node,ctx));index+=1;continue
        value=node.value;end=index+1
        while end<len(entries) and entries[end][1] is ctx:
            nextnode=entries[end][0]
            if fallback(nextnode,ctx):value+=nextnode.value;end+=1
            elif nextnode.kind=='space' and nextnode.value in (' ','space','nobreakspace') and end+1<len(entries) and entries[end+1][1] is ctx and fallback(entries[end+1][0],ctx):value+=' ';end+=1
            else:break
        hint=ctx.font or ctx.text_family+'-'+('BoldItalic' if ctx.text_weight and ctx.text_shape else 'Bold' if ctx.text_weight else 'Italic' if ctx.text_shape else 'Regular')
        output.append((Node('_fallback_run',value,attrs=(('font',hint),),position=node.position),ctx));index=end
    # Source tryCombineChars also combines ordinary text with identical
    # faces/classes. Measure its shaped advance, retaining literal TeX
    # ascents/depths; a formula's math atoms never enter this branch.
    def bundled(node,ctx):
        if node.kind!='symbol' or node.get('mode',ctx.mode)!='text' or len(node.value)!=1:return None
        original=node.get('original','')
        if len(original)==1 and 0x1d400<=ord(original)<=0x1d7ff:return None
        face=ctx.font or ('AMS-Regular' if node.get('font')=='ams' else ctx.text_family+'-'+('BoldItalic' if ctx.text_weight and ctx.text_shape else 'Bold' if ctx.text_weight else 'Italic' if ctx.text_shape else 'Regular'))
        if face=='Math-BoldItalic':face='Main-Bold'
        return face if str(ord(node.value)) in _data('font_metrics').get(face,{}) else None
    combined=[];index=0
    while index<len(output):
        node,ctx=output[index];face=bundled(node,ctx)
        if face is None:combined.append((node,ctx));index+=1;continue
        end=index+1;value=node.value
        while end<len(output) and output[end][1] is ctx and bundled(output[end][0],ctx)==face:
            value+=output[end][0].value;end+=1
        combined.append((Node('_text_run',value,attrs=(('font',face),),position=node.position),ctx) if end-index>1 else (node,ctx));index=end
    return tuple(combined)

def _flow_root(nodes,ctx,build):
    """Source unbreakable chunks, fitted to an explicit native host width."""
    entries=_text_runs(tuple(_fragments(nodes,ctx)));width=ctx.content_width
    if width is None:return _row(nodes,ctx,build)
    paragraphs=[];current=[];gaps=[]
    for node,local in entries:
        if node.kind=='linebreak':paragraphs.append(current);gaps.append(local.dim(node.get('gap')));current=[]
        else:current.append((node,local))
    paragraphs.append(current);lines=[];linegaps=[]
    for pi,paragraph in enumerate(paragraphs):
        boxes=[build(node,local) for node,local in paragraph]
        whole,positions=_row_boxes(boxes,ctx,details=True,contexts=[c for n,c in paragraph])
        chunks=[];start=0;i=0
        while i<len(positions):
            node=paragraph[i][0];box=positions[i][0]
            canbreak=box.atom in ('mbin','mrel') or node.get('break_kind')=='allowbreak'
            if canbreak:
                end=i+1;nobreak=False
                while end<len(positions) and positions[end][0].atom=='space':
                    nobreak|=paragraph[end][0].get('break_kind')=='nobreak';end+=1
                if not nobreak:
                    left=positions[start][1] if start<len(positions) else 0.
                    right=positions[end][1] if end<len(positions) else whole.width
                    chunks.append(_pack(((b,x-left,y) for b,x,y in positions[start:end]),right-left));start=end
                i=end
            else:i+=1
        if start<len(positions):
            left=positions[start][1];chunks.append(_pack(((b,x-left,y) for b,x,y in positions[start:]),whole.width-left))
        current=[];cursor=0.
        for box in chunks:
            if current and cursor+box.width>width:
                lines.append(_pack(current,cursor));linegaps.append(0.);current=[];cursor=0.
            current.append((box,cursor,0.));cursor+=box.width
        lines.append(_pack(current,cursor));linegaps.append(gaps[pi] if pi<len(gaps) else 0.)
    baseline=0.;items=[]
    for index,line in enumerate(lines):
        if index:baseline+=max(1.2*ctx.em,lines[index-1].depth+line.height)+linegaps[index-1]
        items.append((line,0.,baseline))
    return _pack(items,width)

def _row_boxes(boxes,ctx,details=False,contexts=None):
    # TeXbook rule 5/6, buildHTML.traverseNonSpaceNodes: explicit spaces do
    # not break the atom context used by binary-operator cancellation.
    indices=[i for i,b in enumerate(boxes) if b.atom!='space']
    for j,i in enumerate(indices):
        if boxes[i].atom=='mbin':
            prev=boxes[indices[j-1]].atom if j else 'leftmost'
            nxt=boxes[indices[j+1]].atom if j+1<len(indices) else 'rightmost'
            if prev in ('leftmost','mbin','mopen','mrel','mop','mpunct') or nxt in ('rightmost','mrel','mclose','mpunct'):
                boxes[i]=replace(boxes[i],atom='mord')
    x=0.;items=[];prev=None
    for index,b in enumerate(boxes):
        if b.atom!='space':
            local=contexts[index] if contexts is not None else ctx
            table=_TIGHT if local.style>=4 else _SPACING
            if prev is not None: x+=table.get(prev,{}).get(b.atom,0)*ctx.metric('quad')/18
            prev=b.atom
        items.append((b,x,0.));x+=b.width+b.italic
    if boxes and len(indices)==1:
        b=boxes[indices[0]]
        result=_pack(items,x,atom=b.atom,italic=0.,skew=b.skew)
    else:result=_pack(items,x)
    return (result,items) if details else result

def _body(node,ctx,build): return _row(node.children,ctx,build)

def _literal_text(value,ctx,font='Main-Regular'):
    """Source text/labels, not a substitute for a parsed math expression."""
    items=[];x=0.
    local=replace(ctx,font=font,mode='text')
    for char in value:
        box=_char(' ' if char in '\r\n\t' else char,local,mode='text')
        items.append((box,x,0.));x+=box.width
    return _pack(items,x)

def _cdarrow(node,ctx,build):
    direction=node.value
    labels=node.children or (Node('group'),Node('group'))
    if direction in ('>','<','='):
        return _xarrow(replace(node,kind='xarrow',value={'>':'cdrightarrow','<':'cdleftarrow','=':'cdlongequal'}[direction],children=labels),ctx,build)
    if direction=='.':return _char(' ',replace(ctx,font='Main-Regular'),mode='text')
    if direction not in ('A','V','|'):raise ParseError('Invalid CD arrow direction',node.position,'INVALID_CD_ARROW')
    char={'A':'↑','V':'↓','|':'∥'}[direction]
    arrow=_delimiter(char,1.8*ctx.base,replace(ctx,text_size=6,style=2),'mord')
    if direction=='|':return arrow
    labelctx=ctx.styled(_SUP[ctx.style]);left=build(labels[0],labelctx);right=build(labels[1],labelctx)
    commands=list(arrow.commands)
    for label,isleft in ((left,True),(right,False)):
        x=arrow.width/2-.3*labelctx.em-label.width if isleft else arrow.width/2+.3*labelctx.em
        baseline=arrow.depth-(.8-label.depth/ctx.em)*labelctx.em-label.depth
        commands.extend(_move(label,x,baseline))
    # Fixed CD builders deliberately zero label height/depth/advance. The
    # actual paint retains its separate bounds, as with source absolute CSS.
    return replace(arrow,commands=tuple(commands),diagnostics=arrow.diagnostics+left.diagnostics+right.diagnostics)

def _cdlabel(node,ctx,build,anchor=None):
    anchor=anchor or MathBox(ctx.content_width or 0.,0.,0.)
    labelctx=ctx.styled(_SUP[ctx.style]);label=_body(node,labelctx,build)
    x=anchor.width/2-.3*labelctx.em-label.width if node.value=='left' else anchor.width/2+.3*labelctx.em
    y=anchor.depth-(.8-label.depth/ctx.em)*labelctx.em-label.depth
    return MathBox(0.,0.,0.,_move(label,x,y),diagnostics=label.diagnostics)

def _fraction(node,ctx,build):
    style=node.get('style','auto')
    if style!='auto': ctx=ctx.styled(_STYLE[style]+ctx.style%2)
    num=build(node.children[0],ctx.styled(_NUM[ctx.style]))
    den=build(node.children[1],ctx.styled(_DEN[ctx.style]))
    bar=node.get('bar',True);theta=ctx.metric('defaultRuleThickness')
    thickness=max(ctx.dim(node.get('thickness')),ctx.min_rule_thickness*ctx.em) if node.get('thickness') is not None else ctx.rule()
    if node.get('continued',False): num=replace(num,height=max(num.height,ctx.dim((8.5,'pt'))),depth=max(num.depth,ctx.dim((3.5,'pt'))))
    if ctx.style<2: up=ctx.metric('num1');down=ctx.metric('denom1');clear=3*thickness if bar else 7*theta
    else: up=ctx.metric('num2' if bar else 'num3');down=ctx.metric('denom2');clear=thickness if bar else 3*theta
    axis=ctx.metric('axisHeight')
    if bar:
        up=max(up,num.depth+axis+thickness/2+clear)
        down=max(down,den.height-axis+thickness/2+clear)
    else:
        delta=max(0.,clear-((up-num.depth)-(den.height-down)))/2;up+=delta;down+=delta
    w=max(num.width,den.width)
    items=[(num,(w-num.width)/2,-up),(den,(w-den.width)/2,down)]
    if bar: items.append((_rule(w,thickness,ctx,-axis-thickness/2),0.,0.))
    frac=_pack(items,w,atom='minner')
    target=ctx.metric('delim1' if ctx.style<2 else 'delim2')
    left=_delimiter(node.get('left') or '.',target,ctx,'mopen')
    right=MathBox(0.,0.,0.) if node.get('continued',False) else _delimiter(node.get('right') or '.',target,ctx,'mclose')
    return _pack(((left,0.,0.),(frac,left.width,0.),(right,left.width+w,0.)),left.width+w+right.width,atom='mord')

def _scripts(node,ctx,build):
    base_node,sup_node,sub_node=node.children
    if base_node.kind=='accent' and base_node.value not in _IMAGES and base_node.value not in ('widehat','widecheck','widetilde','utilde'):
        nucleus=base_node.children[0]
        while nucleus.kind=='group' and len(nucleus.children)==1:nucleus=nucleus.children[0]
        if nucleus.kind=='symbol':
            plain=build(replace(node,children=(base_node.children[0],sup_node,sub_node)),ctx)
            accent=build(base_node,ctx);bare=build(base_node.children[0],ctx)
            return replace(plain,height=max(plain.height,accent.height),depth=max(plain.depth,accent.depth),
                           commands=accent.commands+plain.commands[len(bare.commands):],diagnostics=plain.diagnostics+accent.diagnostics)
    if base_node.kind=='overunder' and base_node.value in ('overbrace','underbrace','overbracket','underbracket'):
        isover=base_node.value.startswith('over')
        issup=not bool(sub_node.children or sub_node.value)
        annotation=sup_node if sup_node.children or sup_node.value else sub_node
        if issup==isover and (annotation.children or annotation.value):
            brace=replace(base_node,children=(base_node.children[0],annotation))
            result=build(brace,ctx)
            # horizBrace's fixed source chooses grp.sup when both scripts
            # exist; preserve that upstream branch rather than inventing an
            # additional opposite-side script in the delegated builder.
            return result
    base=build(base_node,ctx)
    sup=build(sup_node,ctx.styled(_SUP[ctx.style]));sub=build(sub_node,ctx.styled(_SUB[ctx.style]))
    has_sup=bool(sup_node.children or sup_node.value);has_sub=bool(sub_node.children or sub_node.value)
    limits=node.get('limits')
    if limits is None and base_node.kind=='operator':
        if base_node.get('command','').startswith('operatorname'):
            limits=base_node.get('always_handle_supsub',False) and (ctx.style<2 or base_node.get('limits',False))
        else:limits=base_node.get('limits',False) and (ctx.style<2 or base_node.get('always_handle_supsub',False))
    if limits:
        return _limits(base,sup if has_sup else None,sub if has_sub else None,ctx)
    nucleus=base_node
    while nucleus.kind in ('group','color','font') and len(nucleus.children)==1:nucleus=nucleus.children[0]
    charbase=nucleus.kind=='symbol'
    if charbase and base_node.kind!='symbol' and len(base.commands)==1 and isinstance(base.commands[0],Glyph):
        glyph=base.commands[0];italic=_data('font_metrics')[glyph.font][str(ord(glyph.text))][2]*glyph.size
        base=replace(base,width=base.width-italic,italic=italic)
    up=0. if charbase else base.height-ctx.styled(_SUP[ctx.style]).metric('supDrop')
    down=0. if charbase else base.depth+ctx.styled(_SUB[ctx.style]).metric('subDrop')
    xh=ctx.metric('xHeight');rule=ctx.metric('defaultRuleThickness')
    if has_sup: up=max(up,ctx.metric('sup1' if ctx.style==0 else 'sup3' if ctx.style%2 else 'sup2'),sup.depth+.25*xh)
    if has_sub and has_sup:
        down=max(down,ctx.metric('sub2'))
        if (up-sup.depth)-(sub.height-down)<4*rule:
            down=4*rule-(up-sup.depth)+sub.height
            psi=.8*xh-(up-sup.depth)
            if psi>0: up+=psi;down-=psi
    elif has_sub: down=max(down,ctx.metric('sub1'),sub.height-.8*xh)
    scriptspace=.05*ctx.base
    items=[(base,0.,0.)];w=base.width+base.italic
    if has_sup: items.append((sup,base.width+base.italic,-up));w=max(w,base.width+base.italic+sup.width+scriptspace)
    if has_sub: items.append((sub,base.width,down));w=max(w,base.width+sub.width+scriptspace)
    return _pack(items,w,atom=base.atom)

def _limits(base,sup,sub,ctx):
    w=max(base.width,sup.width if sup else 0.,sub.width if sub else 0.)
    items=[(base,(w-base.width)/2,0.)]
    extra=ctx.metric('bigOpSpacing5')
    if sup:
        gap=max(ctx.metric('bigOpSpacing1'),ctx.metric('bigOpSpacing3')-sup.depth)
        items.append((sup,(w-sup.width+base.italic)/2,-base.height-gap-sup.depth))
    if sub:
        gap=max(ctx.metric('bigOpSpacing2'),ctx.metric('bigOpSpacing4')-sub.height)
        items.append((sub,(w-sub.width-base.italic)/2,base.depth+gap+sub.height))
    result=_pack(items,w,atom='mop')
    return replace(result,height=result.height+(extra if sup else 0),depth=result.depth+(extra if sub else 0))

_DELIMS={'lbrace':'{','rbrace':'}','{':'{','}':'}','langle':'⟨','rangle':'⟩','lvert':'∣','rvert':'∣','vert':'∣','|':'∣','Vert':'∥','lVert':'∥','rVert':'∥','lfloor':'⌊','rfloor':'⌋','lceil':'⌈','rceil':'⌉','lbrack':'[','rbrack':']','lparen':'(','rparen':')','lgroup':'\u27ee','rgroup':'\u27ef','lmoustache':'\u23b0','rmoustache':'\u23b1','backslash':'\\','uparrow':'↑','downarrow':'↓','updownarrow':'↕','Uparrow':'⇑','Downarrow':'⇓','Updownarrow':'⇕'}
_STACK={'\u27ee':('\u23a7','\u23aa','\u23a9',None),'\u27ef':('\u23ab','\u23aa','\u23ad',None),'\u23b0':('\u23a7','\u23aa','\u23ad',None),'\u23b1':('\u23ab','\u23aa','\u23a9',None),'(':('⎛','⎜','⎝',None),')':('⎞','⎟','⎠',None),'[':('⎡','⎢','⎣',None),']':('⎤','⎥','⎦',None),'{':('⎧','⎪','⎩','⎨'),'}':('⎫','⎪','⎭','⎬'),'⌊':('⎢','⎢','⎣',None),'⌈':('⎡','⎢','⎢',None),'⌋':('⎥','⎥','⎦',None),'⌉':('⎤','⎥','⎥',None),'∣':('∣','∣','∣',None),'∥':('∥','∥','∥',None),'↑':('↑','⏐','⏐',None),'↓':('⏐','⏐','↓',None),'↕':('↑','⏐','↓',None),'⇑':('⇑','‖','‖',None),'⇓':('‖','‖','⇓',None),'⇕':('⇑','‖','⇓',None)}

def _delimiter(value,target,ctx,atom='mopen'):
    value=value.lstrip('\\') if value!='\\' else value
    if value=='.': return MathBox(.12*ctx.base,0.,0.,(),atom)
    value=_DELIMS.get(value,value)
    value={'‖':'∥','<':'⟨','>':'⟩'}.get(value,value)
    # Delimiter selection is in text size; script styles try smaller Main
    # sizes first in the original delimiter traversal.
    axis=ctx.metric('axisHeight')
    base=replace(ctx,text_size=6,style=2)
    levels=(6,4,2)[min(2,3-ctx.style//2):]
    main_contexts=[base.styled(level) for level in levels]
    for local in main_contexts:
        if _source_record('Main-Regular',value,'math') is None:continue
        b=_char(value,local,atom,'Main-Regular')
        if b.total_height>target:
            return _pack(((b,0.,(b.height-b.depth)/2-axis),),b.width,atom)
    last=None
    for size in range(1,5):
        if str(ord(value)) not in _data('font_metrics').get(f'Size{size}-Regular',{}): continue
        b=_char(value,base,atom,f'Size{size}-Regular')
        last=b
        if b.total_height>target:
            return _pack(((b,0.,(b.height-b.depth)/2-axis),),b.width,atom)
    if value not in _STACK:
        if value in ('⟨','⟩','/','\\') and last is not None:
            return _pack(((last,0.,(last.height-last.depth)/2-axis),),last.width,atom)
        raise ParseError(f'Delimiter {value!r} cannot stretch to requested height',code='UNSUPPORTED_DELIMITER_SIZE')
    font='Size1-Regular' if value in '∣∥↑↓↕⇑⇓⇕' else 'Size4-Regular'
    top,repeat,bottom,middle=_STACK[value]
    a=_char(top,base,atom,font);r=_char(repeat,base,atom,font);z=_char(bottom,base,atom,font)
    m=_char(middle,base,atom,font) if middle else None
    fixed=a.total_height+z.total_height+(m.total_height if m else 0.)
    factor=2 if m else 1
    count=max(0,math.ceil((target-fixed)/(factor*r.total_height)))
    total=fixed+count*factor*r.total_height
    y=-total/2-axis
    svg={'(':('lparen',875),')':('rparen',875),'[':('lbrack',667),']':('rbrack',667),'⌊':('lfloor',667),'⌋':('rfloor',667),'⌈':('lceil',667),'⌉':('rceil',667),'∣':('vert',333),'∥':('doublevert',556)}
    if value in svg:
        from ._layout_paths import tall_delim
        name,vw=svg[value];scale=base.em/1000
        mid=math.floor((total-a.total_height-z.total_height)/scale+.5)
        path=Path(tall_delim(name,mid),0.,y,scale,scale,ctx.color)
        return MathBox(vw*scale,total/2+axis,total/2-axis,(path,),atom)
    width=max(a.width,z.width,m.width if m else 0.,r.width)
    items=[(a,(width-a.width)/2,y+a.height),(z,(width-z.width)/2,y+total-z.depth)]
    inner=(total-fixed)/factor;overlap=.008*base.em
    ranges=[(y+a.total_height-overlap,inner+2*overlap)]
    if m:
        middle_top=y+a.total_height+inner
        items.append((m,(width-m.width)/2,middle_top+m.height))
        ranges.append((middle_top+m.total_height-overlap,inner+2*overlap))
    # Source innerPath uses continuous rectangles to avoid glyph seams.
    stems={'⎪':((384,504),),'⏐':((312,355),),'‖':((257,300),(478,521))}
    for top,height in ranges:
        for left,right in stems.get(repeat,((384,504),)):
            line=_rule((right-left)*base.em/1000,height,ctx,top)
            items.append((line,left*base.em/1000,0.))
    return _pack(items,width,atom)

def _delimited(node,ctx,build):
    segments=[build(n,ctx) for n in node.children]
    h=max((b.height for b in segments),default=0.);d=max((b.depth for b in segments),default=0.)
    axis=ctx.metric('axisHeight');distance=max(h-axis,d+axis)
    target=max(distance*901/500,2*distance-5*ctx.base/10)
    middle=node.get('middle',());items=[];x=0.
    left=_delimiter(node.get('left','.'),target,ctx,'mopen');items.append((left,x,0.));x+=left.width
    for i,b in enumerate(segments):
        if i:
            delim=_delimiter(middle[i-1],target,ctx,'mrel');gap=5*ctx.metric('quad')/18 if ctx.style<4 else 0.
            x+=gap;items.append((delim,x,0.));x+=delim.width+gap
        items.append((b,x,0.));x+=b.width
    rightctx=replace(ctx,color=node.get('right_color')) if node.get('right_color') is not None else ctx
    right=_delimiter(node.get('right','.'),target,rightctx,'mclose');items.append((right,x,0.));x+=right.width
    return _pack(items,x,'minner')

def _line(node,ctx,build):
    over=node.value=='overline'
    b=_body(node,ctx.styled(ctx.style|1) if over else ctx,build)
    t=ctx.metric('defaultRuleThickness');line=ctx.rule()
    top=-b.height-3*t-line if over else b.depth+3*t
    result=_pack(((b,0.,0.),(_rule(b.width,line,ctx,top),0.,0.)),b.width)
    return replace(result,height=result.height+t if over else result.height,
                   depth=result.depth if over else result.depth+t)

def _sqrt(node,ctx,build):
    from . import _layout_paths
    inner=build(node.children[0],ctx.styled(ctx.style|1))
    h=inner.height or ctx.metric('xHeight')
    theta=ctx.metric('defaultRuleThickness');phi=ctx.metric('xHeight') if ctx.style<2 else theta
    clearance=theta+phi/4
    required=h+inner.depth+clearance+theta
    # Source delimiter.makeSqrtImage chooses a text-size radical. Its long
    # vinculum is clipped horizontally, never compressed with the surd.
    newmult=.5 if ctx.style>=6 else .7 if ctx.style>=4 else 1.
    normalized=required/ctx.em;target=normalized*newmult
    small=(.5,.7,1.)[min(2,3-ctx.style//2):]
    name='sqrtTall';mult=1.;H=normalized
    if any(value>target for value in small):
        name='sqrtMain';mult=1. if normalized<1. else .7 if normalized<1.4 else newmult;H=1.
    else:
        for i,value in enumerate((1.2,1.8,2.4,3.0),1):
            if value>target:name='sqrtSize'+str(i);mult=newmult;H=value;break
    extra=max(0.,ctx.min_rule_thickness-ctx.metric('sqrtRuleThickness')/ctx.em)
    height=(H+extra)*ctx.em/mult
    advance=(1.056 if name=='sqrtTall' else .833/mult if name=='sqrtMain' else 1./mult)*ctx.em
    rule=(ctx.metric('sqrtRuleThickness')+extra*ctx.em)*mult
    if height-rule>h+inner.depth+clearance:
        clearance=(clearance+height-rule-h-inner.depth)/2
    top=-h-clearance-rule
    width=advance+inner.width
    vbheight=(1080*H if name.startswith('sqrtSize') else math.floor(1000*normalized+extra)+80 if name=='sqrtTall' else 1080+1000*extra)
    paddedheight=height+.08*ctx.em/mult
    scale=paddedheight/vbheight
    d=getattr(_layout_paths,name)(extraVinculum=1000*extra,viewBoxHeight=vbheight)
    path=Path(d,0.,top-.08*ctx.em/mult,scale,scale,ctx.color,clip=(0.,0.,width/scale,vbheight))
    image=MathBox(width,-top,height+top,(path,))
    body=_pack(((inner,advance,0.),(image,0.,0.)),width)
    if len(node.children)<2 or not(node.get('index_provided',False) or node.children[1].children or node.children[1].value): return body
    index=build(node.children[1],ctx.styled(6))
    # katex-root CSS: margin-left .27777778em; margin-right -.55555556em.
    left=5/18*ctx.em;right=-10/18*ctx.em
    shift=.6*(body.height-body.depth)
    rootwidth=left+index.width+right
    return _pack(((index,left,-shift),(body,rootwidth,0.)),rootwidth+body.width)

_IMAGES={
 'cdrightarrow':(('rightarrow',),3.,522,'right'),
 'cdleftarrow':(('leftarrow',),3.,522,'left'),
 'cdlongequal':(('longequal',),3.,334,'left'),
 'overrightarrow':(('rightarrow',),.888,522,'right'),
 'overleftarrow':(('leftarrow',),.888,522,'left'),
 'underrightarrow':(('rightarrow',),.888,522,'right'),
 'underleftarrow':(('leftarrow',),.888,522,'left'),
 'xrightarrow':(('rightarrow',),1.469,522,'right'),
 'xleftarrow':(('leftarrow',),1.469,522,'left'),
 'Overrightarrow':(('doublerightarrow',),.888,560,'right'),
 'xRightarrow':(('doublerightarrow',),1.526,560,'right'),
 'xLeftarrow':(('doubleleftarrow',),1.526,560,'left'),
 'overleftharpoon':(('leftharpoon',),.888,522,'left'),
 'xleftharpoonup':(('leftharpoon',),.888,522,'left'),
 'xleftharpoondown':(('leftharpoondown',),.888,522,'left'),
 'overrightharpoon':(('rightharpoon',),.888,522,'right'),
 'xrightharpoonup':(('rightharpoon',),.888,522,'right'),
 'xrightharpoondown':(('rightharpoondown',),.888,522,'right'),
 'xlongequal':(('longequal',),.888,334,'left'),
 'xtwoheadleftarrow':(('twoheadleftarrow',),.888,334,'left'),
 'xtwoheadrightarrow':(('twoheadrightarrow',),.888,334,'right'),
 'overleftrightarrow':(('leftarrow','rightarrow'),.888,522,''),
 'underleftrightarrow':(('leftarrow','rightarrow'),.888,522,''),
 'xleftrightarrow':(('leftarrow','rightarrow'),1.75,522,''),
 'xLeftrightarrow':(('doubleleftarrow','doublerightarrow'),1.75,560,''),
 'overbrace':(('leftbrace','midbrace','rightbrace'),1.6,548,''),
 'underbrace':(('leftbraceunder','midbraceunder','rightbraceunder'),1.6,548,''),
 'xrightleftharpoons':(('leftharpoondownplus','rightharpoonplus'),1.75,716,''),
 'xleftrightharpoons':(('leftharpoonplus','rightharpoondownplus'),1.75,716,''),
 'xhookleftarrow':(('leftarrow','righthook'),1.08,522,''),
 'xhookrightarrow':(('lefthook','rightarrow'),1.08,522,''),
 'overlinesegment':(('leftlinesegment','rightlinesegment'),.888,522,''),
 'underlinesegment':(('leftlinesegment','rightlinesegment'),.888,522,''),
 'overbracket':(('leftbracketover','rightbracketover'),1.6,440,''),
 'underbracket':(('leftbracketunder','rightbracketunder'),1.6,410,''),
 'overgroup':(('leftgroup','rightgroup'),.888,342,''),
 'undergroup':(('leftgroupunder','rightgroupunder'),.888,342,''),
 'xmapsto':(('leftmapsto','rightarrow'),1.5,522,''),
 'xtofrom':(('leftToFrom','rightToFrom'),1.75,528,''),
 'xrightleftarrows':(('baraboveleftarrow','rightarrowabovebar'),1.75,901,''),
 'xrightequilibrium':(('baraboveshortleftharpoon','rightharpoonaboveshortbar'),1.75,716,''),
 'xleftequilibrium':(('shortbaraboveleftharpoon','shortrightharpoonabovebar'),1.75,716,''),
}

def _stretch(label,width,ctx,num_chars=1):
    paths=_data('svg_paths')
    if label in ('widehat','widecheck','widetilde','utilde'):
        i=4 if num_chars>5 else (1,1,2,2,3,3)[num_chars]
        if label in ('widehat','widecheck'):
            vw=(0,1062,2364,2364,2364)[i];vh=(0,239,300,360,420)[i]
            height=(0,.24,.3,.3,.42)[i]*ctx.em;name=label+str(i)
        else:
            vw=(0,600,1033,2339,2340)[i];vh=(0,260,286,306,312)[i]
            height=(0,.26,.286,.3,.34)[i]*ctx.em;name='tilde'+str(i)
        return MathBox(width,height,0.,(Path(paths[name],0.,-height,width/vw,height/vh,ctx.color),) if width>0 else ())
    if label not in _IMAGES: raise ParseError(f'Unsupported stretchy image {label}',code='UNSUPPORTED_STRETCHY')
    names,minwidth,vh,align=_IMAGES[label]
    width=max(width,minwidth*ctx.em);scale=ctx.em/1000;height=vh*scale
    commands=[];count=len(names)
    for i,name in enumerate(names):
        if count==1: start=0.;part=width;side=align
        elif count==2: start=0. if i==0 else width*.498;part=width*.502;side='left' if i==0 else 'right'
        else:
            start=(0.,width*.25,width*.749)[i];part=width*(.251 if i!=1 else .5)
            side=('left','middle','right')[i]
        crop=0. if side=='left' else 400000-part/scale if side=='right' else (400000-part/scale)/2
        commands.append(Path(paths[name],start-crop*scale,-height,scale,scale,ctx.color,clip=(crop,0.,part/scale,vh)))
    return MathBox(width,height,0.,tuple(commands))

def _accent(node,ctx,build):
    label=node.value.lstrip('\\')
    # accent.ts normalizes a singleton ordgroup before its builder sees
    # the nucleus; otherwise an artificial row consumes italic correction.
    if node.children[0].kind=='group' and len(node.children[0].children)==1:
        node=replace(node,children=(node.children[0].children[0],)+node.children[1:])
    below=label.startswith('under') or label in ('utilde','c','cedilla')
    body=build(node.children[0],ctx if below or len(node.children)>1 else ctx.styled(ctx.style|1))
    shifty=node.get('shifty',label not in _IMAGES or label in ('widehat','widecheck','widetilde'))
    skew=body.skew if shifty else 0.
    annotation=build(node.children[1],ctx.styled(_SUB[ctx.style] if below else _SUP[ctx.style])) if len(node.children)>1 else None
    if label in ('overset','underset','stackrel','stackbin'):
        if annotation is None: raise ParseError('Missing over/under annotation',node.position)
        if label=='underset':annotation=build(node.children[1],ctx.styled(_SUB[ctx.style]))
        result=_limits(body,None if label=='underset' else annotation,annotation if label=='underset' else None,ctx)
        return replace(result,atom='mrel' if label=='stackrel' else 'mbin' if label=='stackbin' else body.atom)
    if label in _IMAGES or label in ('widehat','widecheck','widetilde','utilde'):
        brace='brace' in label or 'bracket' in label
        if brace: body=build(node.children[0],replace(ctx,text_size=6,style=0))
        count=len(node.children[0].children) if node.children[0].kind=='group' else 1
        accent=_stretch(label,max(0.,body.width-2*skew),ctx,count)
        w=max(body.width,accent.width)
        clearance=.1*ctx.em if brace else .12*ctx.em if label=='utilde' else 0.
        y=body.depth+clearance+accent.height if below else -body.height-clearance
        items=[(body,(w-body.width)/2,0.),(accent,(w-accent.width)/2+skew,y)]
        if annotation and annotation.commands:
            gap=.2*ctx.em if brace else ctx.metric('bigOpSpacing1')
            y2=y+accent.depth+gap+annotation.height if below else y-accent.height-gap-annotation.depth
            items.append((annotation,(w-annotation.width)/2,y2))
        return _pack(items,max(w,annotation.width if annotation else 0.),'minner' if brace else 'mord')
    glyphs={'hat':'^','bar':'ˉ','tilde':'~','acute':'ˊ','grave':'ˋ','dot':'˙','ddot':'¨','breve':'˘','check':'ˇ','mathring':'˚','ring':'˚','c':'¸','cedilla':'¸','H':'˝','hungarumlaut':'˝','textcircled':'◯'}
    if label=='vec':
        d=_data('svg_paths').get('vec')
        if d is None: raise ParseError('Missing source vec path',node.position,'MISSING_PATH')
        accent=MathBox(.471*ctx.em,.714*ctx.em,0.,(Path(d,0.,-.714*ctx.em,ctx.em/1000,ctx.em/1000,ctx.color),))
    elif label in glyphs:
        mode=node.get('mode',ctx.mode)
        value=({'hat':'\u02c6','tilde':'\u02dc'}.get(label,glyphs[label]) if mode=='text' else glyphs[label])
        accent=_char(value,ctx,mode=mode,position=node.position)
    else: raise ParseError(f'Unsupported accent {label}',node.position,'UNSUPPORTED_ACCENT')
    clearance=min(body.height,ctx.metric('xHeight'))
    if label=='textcircled':
        width=max(body.width,accent.width)
        return _pack(((body,(width-body.width)/2,0.),(accent,(width-accent.width)/2,.2*ctx.em)),width)
    y=body.depth+accent.height if below else -body.height+clearance
    return _pack(((body,0.,0.),(accent,(body.width-accent.width)/2+skew,y)),body.width)

def _xarrow(node,ctx,build):
    upper=build(node.children[0],ctx.styled(_SUP[ctx.style]));lower=build(node.children[1],ctx.styled(_SUB[ctx.style]))
    iscd=node.value.startswith('cd')
    padding=.83334 if iscd else 1.
    arrow=_stretch(node.value,max(upper.width+padding*ctx.styled(_SUP[ctx.style]).em,lower.width+padding*ctx.styled(_SUB[ctx.style]).em),ctx)
    # xArrow.ts: arrow centre is placed on the math axis; .111em gap.
    axis=ctx.metric('axisHeight');gap=.111*ctx.em
    ay=arrow.height/2-axis;w=arrow.width
    items=[(arrow,0.,ay)]
    if True:  # xArrow always puts its mandatory upper group in the vlist.
        upper_shift=-axis-arrow.height/2-gap
        if upper.depth>.25*ctx.em or node.value=='xleftequilibrium':upper_shift-=upper.depth
        items.append((upper,(w-upper.width)/2-(.13889*ctx.styled(_SUP[ctx.style]).em if iscd else 0.),upper_shift))
    if node.get('below_provided',False) or node.children[1].children or node.children[1].value: items.append((lower,(w-lower.width)/2-(.13889*ctx.styled(_SUB[ctx.style]).em if iscd else 0.),-axis+arrow.height/2+gap+lower.height))
    return _pack(items,w,'mrel')

def _array(node,ctx,build):
    env=node.get('environment','array').rstrip('*')
    separation=node.get('col_separation')
    small=separation=='small' or env in ('smallmatrix','subarray','substack')
    cellstyle=node.get('cell_style') or ('script' if small else 'display' if env in ('CD','darray','dcases','drcases','aligned','alignedat','gathered','align','alignat','gather','split') else 'text')
    cellctx=replace(ctx,style=_STYLE[cellstyle],font='',mode='math')
    rows=[[build(cell,cellctx) for cell in row.children] for row in node.children]
    if not rows: return MathBox(0.,0.,0.)
    n=max(map(len,rows),default=0)
    widths=[max((row[j].width if j<len(row) else 0. for row in rows),default=0.) for j in range(n)]
    explicit_specs=node.get('col_specs')
    specs=list(explicit_specs or tuple(('separator',s) if s in ('|',':') else ('align',s,None,None) for s in node.get('cols',())))
    alignments=[s[1] for s in specs if s[0]=='align']
    if len(alignments)==1: alignments*=n
    if not alignments: alignments=['r' if j%2==0 else 'l' for j in range(n)] if env in ('aligned','alignedat','align','alignat','split') else ['l' if env in ('cases','dcases','rcases') else 'c']*n
    alignments=(alignments+['c']*n)[:n]
    pt=ctx.em/10;sep=.2778*cellctx.em if small else 5*pt
    arraystretch=float(node.get('arraystretch') or (1.2 if env in ('cases','dcases','rcases','drcases') else .5 if small else 1.))
    baselineskip=ctx.dim((3,'ex')) if separation=='CD' or env=='CD' else 12*pt
    struth=.7*baselineskip*arraystretch;strutd=.3*baselineskip*arraystretch
    addjot=node.get('add_jot')
    if addjot is None:addjot=env in ('CD','aligned','alignedat','gathered','align','alignat','gather','split')
    gaps=node.get('row_gaps',());hlines=node.get('hlines',());t=ctx.rule('arrayRuleWidth')
    def addlines(index):
        nonlocal total
        selected=[style for row,style in hlines if row==index]
        for j,style in enumerate(selected):
            if j:total+=.25*ctx.em
            linepositions.append((total,style))
    baselines=[];heights=[];depths=[];total=0.;linepositions=[]
    for i,row in enumerate(rows):
        addlines(i)
        h=max(struth,max((b.height for b in row),default=0.));d=max(strutd,max((b.depth for b in row),default=0.))
        gap=ctx.dim(gaps[i]) if i<len(gaps) and gaps[i] is not None else 0.
        if gap>0: d=max(d,gap+strutd);gap=0.
        if addjot and i<len(rows)-1: d+=3*pt
        baselines.append(total+h);heights.append(h);depths.append(d);total+=h+d+gap
    addlines(len(rows))
    offset=total/2+ctx.metric('axisHeight')
    x=0.;xs=[];vertical=[];specindex=0
    outer=node.get('hskip_before_after')
    if outer is None:outer=env in ('array','darray')
    aligned=env in ('aligned','alignedat','align','alignat','split')
    cases=env in ('cases','dcases','rcases','drcases')
    def separators():
        nonlocal x,specindex
        first=True
        while specindex<len(specs) and specs[specindex][0]=='separator':
            if not first:x+=ctx.metric('doubleRuleSep')
            # Source border width .04em has margins -.02em on each side:
            # its centre lies at x and its net horizontal advance is zero.
            vertical.append((x-t/2,specs[specindex][1]));specindex+=1;first=False
    for j in range(n):
        separators()
        description=specs[specindex] if specindex<len(specs) else ('align',alignments[j],None,None)
        if specindex<len(specs):specindex+=1
        if j or outer:
            if explicit_specs:
                x+=ctx.dim(description[2]) if description[2] is not None else sep
            elif env=='CD':x+=.25*ctx.em
            elif aligned:
                x+=0. if j%2 else (0. if env in ('alignedat','alignat') else ctx.em)
            elif not cases:x+=sep
        xs.append(x);x+=widths[j]
        # The previous column's postgap precedes any following separator;
        # it cannot be folded into the next column's pregap.
        if j<n-1 or outer:
            if explicit_specs:x+=ctx.dim(description[3]) if description[3] is not None else sep
            elif env=='CD':x+=.25*ctx.em
            elif cases:x+=ctx.em if j==0 else 0.
            elif not aligned:x+=sep
    separators()
    items=[]
    for i,row in enumerate(rows):
        for j,b in enumerate(row):
            shift=0. if alignments[j]=='l' else widths[j]-b.width if alignments[j]=='r' else (widths[j]-b.width)/2
            items.append((b,xs[j]+shift,baselines[i]-offset))
    commands=[]
    for pos,style in linepositions:
        if style=='hline': commands.append(Rule(0.,pos-offset,x,t,ctx.color))
        else:
            dash=3*t;xx=0.
            while xx<x:commands.append(Rule(xx,pos-offset,min(dash,x-xx),t,ctx.color));xx+=2*dash
    for vx,style in vertical:
        if style=='|':commands.append(Rule(vx,-offset,t,total,ctx.color))
        else:
            dash=3*t;y=0.
            while y<total:commands.append(Rule(vx,y-offset,t,min(dash,total-y),ctx.color));y+=2*dash
    result=_pack(items,x)
    result=replace(result,height=offset,depth=total-offset,commands=result.commands+tuple(commands),atom='mord')
    left=node.get('left');right=node.get('right')
    if left or right:
        target=max(result.total_height*.901,result.total_height-.5*ctx.em)
        l=_delimiter(left or '.',target,ctx,'mopen');r=_delimiter(right or '.',target,ctx,'mclose')
        result=_pack(((l,0.,0.),(result,l.width,0.),(r,l.width+result.width,0.)),l.width+result.width+r.width,'minner')
    tags=node.get('tags')
    if tags and any(tags):
        from .layout_display import place_display
        boxes=[]
        for index,tag in enumerate(tags):
            if not tag:continue
            if tag is True:
                if ctx.counter is not None:ctx.counter[0]+=1;number=ctx.counter[0]
                else:number=ctx.equation_counter+sum(t is True for t in tags[:index+1])
                box=_literal_text('('+str(number)+')',ctx.styled(2))
            else:box=build(tag,ctx.styled(2))
            boxes.append((box,baselines[index]-offset))
        result=place_display(result,boxes,em=ctx.base,content_width=ctx.content_width,
                             leqno=node.get('leqno',ctx.leqno),fleqn=ctx.fleqn)
    return result

def _enclose(node,ctx,build):
    b=_body(node,ctx,build);label=node.value.lstrip('\\');t=ctx.rule('fboxrule')
    if label in ('boxed','fbox','colorbox','fcolorbox'):
        pad=ctx.metric('fboxsep');border=0. if label=='colorbox' else t
        # The source .boxpad contributes .3em on each side. The overlaid
        # .fbox uses border-box sizing, so its border consumes no extra
        # horizontal advance (vertical TeX padding does include the rule).
        w=b.width+2*pad;h=b.height+pad+border;d=b.depth+pad+border
        background=node.get('color') if label in ('colorbox','fcolorbox') else None
        color=node.get('border_color') or ctx.color
        commands=[]
        if background: commands.append(Rule(0.,-h,w,h+d,background))
        commands.extend(_move(b,pad))
        if border: commands.extend((Rule(0.,-h,w,t,color),Rule(0.,d-t,w,t,color),Rule(0.,-h,t,h+d,color),Rule(w-t,-h,t,h+d,color)))
        return MathBox(w,h,d,tuple(commands),diagnostics=b.diagnostics)
    if label=='sout':
        line=_rule(b.width,.08*ctx.em,ctx,-ctx.metric('xHeight')/2)
        return _pack(((b,0.,0.),(line,0.,0.)),b.width)
    if label in ('cancel','bcancel','xcancel'):
        # stretchyEnclose uses SVG line strokes; padded .2em only for a
        # single character nucleus, as in the source cancel package.
        single=len(node.children)==1 and (node.children[0].kind=='symbol' or node.children[0].kind=='group' and len(node.children[0].children)==1)
        p=.2*ctx.em if single else 0.;h=b.height+p;d=b.depth+p
        commands=list(b.commands)
        px=0. if single else .2*ctx.em
        if label in ('cancel','xcancel'):commands.append(Path(f'M{-px} {d} L{b.width+px} {-h}',color=ctx.color,stroke_width=.046*ctx.em))
        if label in ('bcancel','xcancel'):commands.append(Path(f'M{-px} {-h} L{b.width+px} {d}',color=ctx.color,stroke_width=.046*ctx.em))
        return MathBox(b.width,b.height,b.depth,tuple(commands),diagnostics=b.diagnostics)
    if label=='angl':
        t=ctx.rule();pad=.03889*ctx.em;w=b.width+2*pad+.03889*ctx.em
        h=b.height+4*t;d=max(b.depth,.25*ctx.em)
        return MathBox(w,h,d,_move(b,pad)+(Rule(0.,-h,w,t,ctx.color),Rule(w-t,-h,t,h+d,ctx.color)))
    if label=='phase':
        line=ctx.dim((.6,'pt'));clear=ctx.dim((.35,'ex'));height=b.total_height+line+clear
        pad=height/2+line;w=pad+b.width;y=height
        path=f'M{w} {y} H0 L{y/2} 0 l{.065*ctx.em} {.045*ctx.em} L{.145*ctx.em} {y-.08*ctx.em} H{w}z'
        return MathBox(w,b.height,b.depth+line+clear,_move(b,pad)+(Path(path,0.,-b.height,color=ctx.color),))
    raise ParseError(f'Unsupported enclosure {label}',node.position,'UNSUPPORTED_ENCLOSURE')

def layout(tree:Node,options:Options|None=None)->MathBox:
    """Lay out a parsed expression using bundled KaTeX metrics, in pixels."""
    options=options or Options()
    if not isinstance(tree,Node): raise TypeError('tree must be a Node')
    if not math.isfinite(options.font_size) or options.font_size<=0: raise ValueError('font_size must be positive and finite')
    stack=[(tree,0)];count=0
    while stack:
        current,depth=stack.pop();count+=1
        if depth>options.max_depth:raise ParseError('Layout depth limit exceeded',current.position,'MAX_DEPTH')
        if count>options.max_nodes:raise ParseError('Layout node limit exceeded',current.position,'MAX_NODES')
        stack.extend((child,depth+1) for child in current.children)
        pending=[v for k,v in current.attrs]
        while pending:
            value=pending.pop()
            if isinstance(value,Node):stack.append((value,depth+1))
            elif isinstance(value,(tuple,list)):pending.extend(value)
    ctx=_Context(options.font_size,0 if options.display_mode else 2,color=options.color,
                 max_size=options.max_size,min_rule_thickness=options.min_rule_thickness,
                 content_width=options.content_width,leqno=options.leqno,fleqn=options.fleqn,
                 equation_counter=options.equation_counter,counter=[options.equation_counter],
                 resources=options.resources,html_styles=options.html_styles,error_color=options.error_color,native_options=options)
    build=lambda n,c:_build(n,c,1,options.max_depth)
    sole=tree.children[0] if tree.kind=='group' and len(tree.children)==1 else tree
    already_display=sole.kind=='tag' or sole.kind=='array' and any(sole.get('tags') or ())
    if tree.kind=='group' and not tree.attrs:
        result=_row(tree.children,ctx,build) if options.display_mode or already_display else _flow_root(tree.children,ctx,build)
    else:result=build(tree,ctx)
    if options.display_mode and not already_display and (options.content_width is not None or options.fleqn):
        from .layout_display import place_display
        result=place_display(result,em=ctx.base,content_width=ctx.content_width,fleqn=ctx.fleqn)
    return replace(result,diagnostics=tuple(dict.fromkeys(result.diagnostics)))

def _build(node,ctx,depth=0,max_depth=100):
    if depth>max_depth: raise ParseError('Layout depth limit exceeded',node.position,'MAX_DEPTH')
    build=lambda n,c:_build(n,c,depth+1,max_depth)
    kind=node.kind
    if kind=='group':
        if node.get('reset_font',False):ctx=replace(ctx,font='')
        if node.get('cd_parent',False):
            children=node.children[0].children if len(node.children)==1 and node.children[0].kind=='group' else node.children
            body=_row(tuple(child for child in children if child.kind!='cdlabel'),ctx,build)
            labels=[_cdlabel(child,ctx,build,body) for child in children if child.kind=='cdlabel']
            return replace(body,commands=body.commands+tuple(c for b in labels for c in b.commands),diagnostics=body.diagnostics+tuple(d for b in labels for d in b.diagnostics))
        return replace(_body(node,ctx,build),atom='mord')
    if kind in ('error','unsupported'):
        color=node.get('color') or node.get('error_color') or ctx.error_color
        box=_literal_text(node.value,replace(ctx,color=color,font='Main-Regular',mode='text'))
        diagnostic=Diagnostic(node.get('message','Unsupported command' if kind=='unsupported' else 'Invalid TeX'),
                              node.position,node.get('code','UNTRUSTED_COMMAND' if kind=='unsupported' else 'PARSE_ERROR'),
                              'warning' if kind=='unsupported' else 'error')
        return replace(box,diagnostics=(diagnostic,))
    if kind=='image':
        from .layout_html import layout_image
        return layout_image(node,font_size=ctx.em,color=ctx.color,dimension=ctx.dim,resources=ctx.resources)
    if kind=='html':
        from .layout_html import resolve_html_context,apply_html,length
        attributes=node.get('attributes',())
        resolved=resolve_html_context(attributes,font_size=ctx.em,color=ctx.color,font=ctx.font,class_styles=ctx.html_styles)
        line=resolved.get('css_line_height')
        if line in (None,'inherit','unset'):line=ctx.css_line_height
        elif line!='normal' and not re.fullmatch(r'[\d.]+',line):line=str(length(line,resolved['font_size'],resolved['font_size']))+'px'
        local=replace(ctx,base=ctx.base*resolved['font_size']/ctx.em,color=resolved['color'],
                      css_family=resolved.get('css_family') or ctx.css_family,
                      css_shape=resolved.get('css_shape') or ctx.css_shape,
                      css_weight=resolved.get('css_weight') or ctx.css_weight,css_line_height=line)
        box=_body(node,local,build)
        # The enclosing HTML span inherits CSS font axes; inner TeX font
        # commands only affect their generated glyph classes, not this cell.
        outer=_paint_settings('Main-Regular',replace(local,font='',text_family_explicit=False,text_weight='',text_shape=''),mode='text')
        return apply_html(box,attributes,font_size=resolved['font_size'],color=resolved['color'],class_styles=ctx.html_styles,
                          outer_font=outer[0],outer_style=outer[1],outer_weight=outer[2],outer_line_height=local.css_line_height)
    if kind=='tag':
        from .layout_display import place_display
        body=build(node.children[0],ctx);tag=build(node.children[1],ctx.styled(2))
        return place_display(body,((tag,0.),),em=ctx.base,content_width=ctx.content_width,
                             leqno=node.get('leqno',ctx.leqno),fleqn=ctx.fleqn)
    if kind=='symbol':
        mode=node.get('mode',ctx.mode)
        local=replace(ctx,font='',mode='math') if mode=='math' and ctx.mode=='text' else ctx
        font=node.get('font')
        font=('AMS-Regular' if not local.font else None) if font=='ams' else None if font=='main' else font
        original=node.get('original','')
        if len(original)==1:
            cp=ord(original)
            if 0x1d400<=cp<0x1d6a4:
                wide=('Main-Bold','Main-Bold','Math-Italic','Math-Italic','Main-BoldItalic','Main-BoldItalic',
                      'Script-Regular','','','','Fraktur-Regular','Fraktur-Regular','AMS-Regular','AMS-Regular',
                      'Fraktur-Regular','Fraktur-Regular','SansSerif-Regular','SansSerif-Regular','SansSerif-Bold','SansSerif-Bold',
                      'SansSerif-Italic','SansSerif-Italic','','','Typewriter-Regular','Typewriter-Regular')
                font=wide[(cp-0x1d400)//26] or font
            elif 0x1d7ce<=cp<=0x1d7ff:
                font=('Main-Bold','','SansSerif-Regular','SansSerif-Bold','Typewriter-Regular')[(cp-0x1d7ce)//10] or font
            elif cp in (0x1d6a5,0x1d6a6):font='Main-Bold'
        result=_char(node.value,local,node.get('atom','mord'),mode=mode,font=font,original=original,position=node.position)
        if len(original)==1 and 0x1d56c<=ord(original)<0x1d5a0:
            # wide-character.ts uses regular Fraktur metrics with the bold
            # Fraktur CSS face. Both source TTF faces are bundled.
            result=replace(result,commands=tuple(replace(c,font='Fraktur-Bold') if isinstance(c,Glyph) else c for c in result.commands))
        return result
    if kind=='_fallback_run':return _fallback_text(node.value,ctx,font=node.get('font',''))
    if kind=='_text_run':
        from .canvas import measure_bundled_text
        font=node.get('font');paint,style,weight=_paint_settings(font,ctx)
        measured=measure_bundled_text(node.value,paint,ctx.em,style=style,weight=weight)
        records=[_data('font_metrics')[font][str(ord(char))] for char in node.value]
        return MathBox(measured['width'],max(r[1] for r in records)*ctx.em,max(r[0] for r in records)*ctx.em,
                       (Glyph(node.value,0.,0.,paint,ctx.em,ctx.color,font_style=style,font_weight=weight),))
    if kind=='frac': return _fraction(node,ctx,build)
    if kind=='scripts': return _scripts(node,ctx,build)
    if kind=='delimiters': return _delimited(node,ctx,build)
    if kind=='sized_delimiter':
        size=node.get('size',1)
        if size not in (1,2,3,4): raise ParseError('Invalid delimiter size',node.position)
        value=node.value.lstrip('\\') if node.value!='\\' else node.value
        value=_DELIMS.get(value,value);value={'‖':'∥','<':'⟨','>':'⟩'}.get(value,value)
        base=replace(ctx,text_size=6,style=2)
        if value in '∣∥↑↓↕⇑⇓⇕⟮⟯⎰⎱':return _delimiter(value,(1.2,1.8,2.4,3.)[size-1]*ctx.base,base,node.get('atom','mord'))
        if value=='.':return MathBox(0.,0.,0.)
        return _char(value,base,node.get('atom','mord'),f'Size{size}-Regular')
    if kind=='atom': return replace(_body(node,ctx,build),atom=node.get('atom','mord'))
    if kind=='mathchoice': return build(node.children[min(ctx.style//2,3)],ctx)
    if kind=='xarrow': return _xarrow(node,ctx,build)
    if kind=='cdarrow': return _cdarrow(node,ctx,build)
    if kind=='cdlabel': return _cdlabel(node,ctx,build)
    if kind=='vcenter':
        b=_body(node,ctx,build);return _pack(((b,0.,(b.height-b.depth)/2-ctx.metric('axisHeight')),),b.width)
    if kind=='reflect':
        b=_body(node,ctx,build);commands=[]
        for c in b.commands:
            if isinstance(c,Glyph):commands.append(replace(c,x=b.width-c.x,scale_x=-c.scale_x))
            elif isinstance(c,Rule):commands.append(replace(c,x=b.width-c.x-c.width))
            elif isinstance(c,Path):commands.append(replace(c,x=b.width-c.x,scale_x=-c.scale_x))
            else:commands.append(CommandGroup((c,),x=b.width,scale_x=-1.))
        return replace(b,commands=tuple(commands))
    if kind=='pmb':
        b=_body(node,ctx,build)
        nucleus=node.children[0] if node.children else Node('group')
        while nucleus.kind=='group' and len(nucleus.children)==1:nucleus=nucleus.children[0]
        atom=nucleus.get('atom','mord');atom=atom if atom in ('mbin','mrel') else 'mord'
        def text_only(commands):
            output=[]
            for command in commands:
                if isinstance(command,Glyph):output.append(command)
                elif isinstance(command,CommandGroup):
                    children=text_only(command.commands)
                    if children:output.append(replace(command,commands=children))
            return tuple(output)
        shadow=CommandGroup(text_only(b.commands),x=.02*ctx.em,y=.01*ctx.em,filter='blur(0.04px)')
        return replace(b,atom=atom,commands=(shadow,)+b.commands)
    if kind=='operator':
        if node.get('symbol',False):
            font='Size2-Regular' if ctx.style<2 and not node.get('small',False) else 'Size1-Regular'
            if node.value in ('∯','∰'):
                underlying='∬' if node.value=='∯' else '∭'
                b=_char(underlying,ctx,'mop',font)
                name=('oiint' if node.value=='∯' else 'oiiint')+('Size2' if font.startswith('Size2') else 'Size1')
                dims={'oiintSize1':(.957,.499),'oiintSize2':(1.472,.659),'oiiintSize1':(1.304,.499),'oiiintSize2':(1.98,.659)}
                width,height=dims[name];path=Path(_data('svg_paths')[name],(b.width-width*ctx.em)/2,-height*ctx.em+(.08*ctx.em if font.startswith('Size2') else 0.),ctx.em/1000,ctx.em/1000,ctx.color)
                b=replace(b,commands=b.commands+(path,))
            else:b=_char(node.value,ctx,'mop',font)
            shift=0. if node.get('suppress_base_shift',False) else (b.height-b.depth)/2-ctx.metric('axisHeight')
            return _pack(((b,0.,shift),),b.width,'mop',b.italic)
        if node.children and not node.get('roman',True):
            argument=node.children[0]
            if argument.kind=='group' and len(argument.children)==1:argument=argument.children[0]
            if argument.kind in ('symbol','font','color','style','size'):
                candidate=build(argument,ctx)
                if len(candidate.commands)==1 and isinstance(candidate.commands[0],Glyph):
                    shift=0. if node.get('suppress_base_shift',False) else (candidate.height-candidate.depth)/2-ctx.metric('axisHeight')
                    return _pack(((candidate,0.,shift),),candidate.width,'mop',candidate.italic)
        if node.children and node.get('roman',True):
            def roman(n):
                if n.kind=='symbol':return replace(n,value={'−':'-','∗':'*'}.get(n.value,n.value),attrs=tuple((k,'mord' if k=='atom' else 'text' if k=='mode' else v) for k,v in n.attrs))
                return replace(n,children=tuple(roman(child) for child in n.children))
            b=_body(replace(node,children=tuple(roman(child) for child in node.children)),replace(ctx,font='Main-Regular'),build)
        else:b=_body(node,ctx,build) if node.children else _literal_text(node.value,ctx,'Main-Bold' if ctx.font=='Math-BoldItalic' else 'Main-Regular')
        return replace(b,atom='mop')
    if kind in ('font','text'):
        command=node.value.lstrip('\\')
        if command not in _FONTS: raise ParseError(f'Unsupported font {command}',node.position,'UNSUPPORTED_FONT')
        if kind=='text':
            if node.get('verb',False):ctx=ctx.styled(_TEXT[ctx.style])
            family=ctx.text_family;weight=ctx.text_weight;shape=ctx.text_shape;mathfont=ctx.font
            if command in ('textrm','textnormal','textsf','texttt'):
                family={'textsf':'SansSerif','texttt':'Typewriter'}.get(command,'Main');mathfont=''
            elif command in ('textbf','textmd'):weight='bold' if command=='textbf' else '';mathfont=''
            elif command in ('textit','textup'):shape='italic' if command=='textit' else '';mathfont=''
            elif command=='emph':shape='' if shape else 'italic';mathfont=''
            elif command=='hbox':mathfont=''
            local=replace(ctx,font=mathfont,mode='text',text_family=family,text_weight=weight,text_shape=shape,
                          text_family_explicit=ctx.text_family_explicit or command in ('textrm','textnormal','textsf','texttt'))
        else:local=replace(ctx,font=_FONTS[command],mode='math')
        if kind=='font' and len(node.children)==1:
            argument=node.children[0]
            if argument.kind=='group' and len(argument.children)==1:argument=argument.children[0]
            return build(argument,local)
        return _body(node,local,build)
    if kind=='color': return _body(node,replace(ctx,color=node.value),build)
    if kind=='style':
        if node.value not in _STYLE: raise ParseError(f'Unsupported style {node.value}',node.position,'UNSUPPORTED_STYLE')
        local=ctx.styled(_STYLE[node.value]+bool(node.get('cramped',False)))
        if node.get('reset_font',False):local=replace(local,font='',mode='math')
        return _body(node,local,build)
    if kind=='size':
        command=node.value.lstrip('\\')
        if command not in _SIZE: raise ParseError(f'Unsupported size {command}',node.position,'UNSUPPORTED_SIZE')
        return _body(node,replace(ctx,text_size=_SIZE[command],style=_TEXT[ctx.style]),build)
    if kind in ('space','kern'):
        width=node.get('width')
        if node.get('break_kind') in ('allowbreak','nobreak'):return MathBox(0.,0.,0.,(),atom='space')
        if kind=='space' and node.value in (' ','space','nobreakspace'):
            return replace(_char(' ',ctx,mode=ctx.mode),atom='space')
        if width is None:
            widths={',':3/18,':':4/18,';':5/18,'!':-3/18,'quad':1,'qquad':2,'enspace':.5,' ':' .333333','space':1/3,'thinspace':1/6,'medspace':2/9,'thickspace':5/18,'negthinspace':-1/6}
            if node.value not in widths: raise ParseError(f'Unsupported space {node.value}',node.position,'UNSUPPORTED_SPACE')
            width=float(widths[node.value])
        return MathBox(ctx.dim(width),0.,0.,(),atom='space')
    if kind=='rule':
        w=ctx.dim(node.get('width'));h=ctx.dim(node.get('height'));shift=ctx.dim(node.get('shift'))
        # .katex-rule has min-height:1px; its right border paints that
        # content pixel in addition to the requested top-border thickness.
        return MathBox(w,h+shift,-shift,(Rule(0.,-h-shift-1.,w,h+1.,ctx.color),))
    if kind=='raise':
        b=_body(node,ctx,build);dy=ctx.dim(node.get('dy'))
        return _pack(((b,0.,-dy),),b.width,b.atom)
    if kind=='phantom':
        b=_body(node,ctx,build)
        return MathBox(0. if node.value=='vphantom' else b.width,0. if node.value=='hphantom' else b.height,0. if node.value=='hphantom' else b.depth,(),b.atom,diagnostics=b.diagnostics)
    if kind=='smash':
        b=_body(node,ctx,build)
        return replace(b,height=0. if node.get('smash_height',True) else b.height,depth=0. if node.get('smash_depth',True) else b.depth)
    if kind=='lap':
        b=_body(node,ctx,build);x=-b.width if node.value=='llap' else -b.width/2 if node.value=='clap' else 0.
        return _pack(((b,x,0.),),0.)
    if kind=='line': return _line(node,ctx,build)
    if kind=='sqrt': return _sqrt(node,ctx,build)
    if kind in ('accent','overunder'): return _accent(node,ctx,build)
    if kind=='array': return _array(node,ctx,build)
    if kind=='enclose': return _enclose(node,ctx,build)
    raise ParseError(f'Unsupported layout node: {kind}',node.position,'UNSUPPORTED_LAYOUT_KIND')
