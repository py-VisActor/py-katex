"""Pure static adaptation of KaTeX html/includegraphics source nodes.

HTML ids/data and unknown classes remain parser metadata. Arbitrary host CSS is
not silently accepted: the visible property inventory below is explicit.
"""
from __future__ import annotations
from dataclasses import replace
from functools import lru_cache
from importlib.resources import files
import math,re,struct
from .model import MathBox,Glyph,Rule,Path,ImageCommand,CommandGroup,ParseError
from .resources import resolve_image

FONT_CLASSES={'mathrm':'Main-Regular','mathnormal':'Math-Italic','mathit':'Main-Italic','mathbf':'Main-Bold','boldsymbol':'Math-BoldItalic','mathbb':'AMS-Regular','amsrm':'AMS-Regular','mathcal':'Caligraphic-Regular','mathfrak':'Fraktur-Regular','mathscr':'Script-Regular','mathsf':'SansSerif-Regular','mathsfit':'SansSerif-Italic','mathtt':'Typewriter-Regular'}
SUPPORTED=frozenset(('color font font-size font-family font-weight font-style opacity display visibility background background-color border border-width border-style border-color border-radius padding margin width height min-width max-width min-height max-height vertical-align transform transform-origin position left right top bottom overflow overflow-x overflow-y clip clip-path text-decoration text-decoration-line text-decoration-color text-decoration-thickness text-shadow letter-spacing word-spacing filter box-sizing line-height white-space text-align cursor pointer-events user-select').split())
DOM_ONLY=frozenset(('cursor pointer-events user-select').split())

def error(message,code='UNSUPPORTED_HTML_STYLE'):raise ParseError(message,code=code)

def declarations(text):
    if re.search(r'url\s*\(|expression\s*\(|@import|javascript:',text,re.I):error('External or executable CSS is forbidden','UNSAFE_HTML_STYLE')
    # Values here cannot contain semicolons in strings/functions; diagnose rather
    # than silently parsing a different declaration list.
    out=[]
    for item in text.split(';'):
        if not item.strip():continue
        if ':' not in item:error('Invalid CSS declaration')
        name,value=item.split(':',1);name=name.strip().lower();value=value.strip()
        important=bool(re.search(r'\s*!important\s*$',value,re.I));value=re.sub(r'\s*!important\s*$','',value,flags=re.I).strip()
        if name not in SUPPORTED:error('Unsupported visible HTML style property: '+name)
        out.append((name,value,important))
    return out

def styles(attributes,class_styles=()):
    # Source domTree.toMarkup rejects invalid names at build time, not parse.
    for name,value in attributes:
        if not isinstance(name,str) or re.search(r'[\s\"\'>/=\x00-\x1f]',name):error('Invalid HTML attribute name: '+str(name),'INVALID_HTML_ATTRIBUTE')
    attrs=dict(attributes);entries=[];classes=attrs.get('class','').split()
    for name,body in class_styles:
        if name.lstrip('.') in classes:entries.extend(declarations(body))
    entries.extend(declarations(attrs.get('style','')))
    values={};locked=set()
    for key,value,important in entries:
        if key not in locked or important:values[key]=value
        if important:locked.add(key)
    return values

def length(value,size,percent=None):
    if value in {'0','normal'}:return 0.
    m=re.fullmatch(r'\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))(px|em|ex|pt|pc|in|cm|mm|%)?\s*',value)
    if not m:error('Unsupported static CSS length: '+str(value))
    unit=m[2] or 'px';number=float(m[1])
    multiplier={'px':1,'em':size,'ex':size*.431,'pt':96/72,'pc':16,'in':96,'cm':96/2.54,'mm':96/25.4,'%':(percent if percent is not None else size)/100}[unit]
    result=number*multiplier
    if not math.isfinite(result) or abs(result)>1_000_000:error('CSS length budget exceeded')
    return result

def color(value,current):
    if value in {'currentColor','currentcolor','inherit'}:return current
    if re.fullmatch(r'#[0-9a-fA-F]{3,8}|[a-zA-Z]+|(?:rgb|hsl)a?\([^;{}]+\)',value):return value
    error('Invalid static CSS color')

def resolve_html_context(attributes,*,font_size,color: str,font='',class_styles=()):
    values=styles(attributes,class_styles)
    # Only axes actually declared by the enclosing span are supplied. The
    # generated inner KaTeX symbol classes decide which axes inherit them.
    family=shape=weight=None
    class_axes={
        'textbf':(None,None,'700'),'textit':(None,'italic',None),
        'textrm':('Main',None,None),'textsf':('SansSerif',None,None),'texttt':('Typewriter',None,None),
        'mathnormal':('Math','italic',None),'mathit':('Main','italic',None),
        'mathrm':(None,'normal',None),'mathbf':('Main',None,'700'),
        'boldsymbol':('Math','italic','700'),'amsrm':('AMS',None,None),
        'mathbb':('AMS',None,None),'textbb':('AMS',None,None),
        'mathcal':('Caligraphic',None,None),'mathfrak':('Fraktur',None,None),'textfrak':('Fraktur',None,None),
        'mathboldfrak':('Fraktur',None,'700'),'textboldfrak':('Fraktur',None,'700'),
        'mathtt':('Typewriter',None,None),'mathscr':('Script',None,None),'textscr':('Script',None,None),
        'mathsf':('SansSerif',None,None),'mathboldsf':('SansSerif',None,'700'),'textboldsf':('SansSerif',None,'700'),
        'mathsfit':('SansSerif','italic',None),'mathitsf':('SansSerif','italic',None),'textitsf':('SansSerif','italic',None),
        'mainrm':('Main','normal',None)}
    for cls in dict(attributes).get('class','').split():
        axes=class_axes.get(cls)
        if axes:
            if axes[0] is not None:family=axes[0]
            if axes[1] is not None:shape=axes[1]
            if axes[2] is not None:weight=axes[2]
    if 'font' in values:
        match=re.fullmatch(r'(?:(italic|normal)\s+)?(?:(bold|normal|[1-9]00)\s+)?([\d.]+(?:px|em|pt|%))(?:/[^\s]+)?\s+(.+)',values['font'])
        if not match:error('Unsupported CSS font shorthand')
        values.update({'font-style':match[1] or 'normal','font-weight':match[2] or 'normal','font-size':match[3],'font-family':match[4]})
        line=re.search(r'[\d.]+(?:px|em|pt|%)/([^\s]+)',values['font'])
        values['line-height']=line[1] if line else 'normal'
    size=font_size
    if values.get('font-size') not in (None,'inherit','unset'):
        value=values['font-size'];size=font_size*{'smaller':.833333,'larger':1.2}[value] if value in {'smaller','larger'} else length(value,font_size,font_size)
    if not 0<size<=16384:error('CSS font size exceeds budget')
    if values.get('font-family') not in (None,'inherit','unset'):
        names=[name.strip(' \"\'') for name in values['font-family'].split(',')]
        families={'serif':'Main','math':'Math','monospace':'Typewriter','sans-serif':'SansSerif','KaTeX_Main':'Main','KaTeX_Math':'Math','KaTeX_AMS':'AMS','KaTeX_Caligraphic':'Caligraphic','KaTeX_Fraktur':'Fraktur','KaTeX_Script':'Script','KaTeX_SansSerif':'SansSerif','KaTeX_Typewriter':'Typewriter'}
        family=next((families[name] for name in names if name in families),None)
        if family is None:error('HTML font family requires an available bundled KaTeX face','UNSUPPORTED_FONT')
    if values.get('font-weight') not in (None,'inherit','unset'):
        value=values['font-weight'];weight={'normal':'400','bold':'700','bolder':'900' if 'Bold' in font else '700','lighter':'400' if 'Bold' in font else '100'}.get(value,value)
        if not weight.isdigit() or not 1<=int(weight)<=1000:error('Unsupported CSS font weight')
    if values.get('font-style') not in (None,'inherit','unset'):
        shape=values['font-style']
        if shape not in {'normal','italic','oblique'}:error('Unsupported CSS font style')
    old_font=font
    if any(axis is not None for axis in (family,shape,weight)):
        selected_family=family or (font.split('-')[0] if font else 'Math')
        selected_shape=shape or ('italic' if 'Italic' in font or not font else 'normal')
        selected_weight=weight or ('700' if 'Bold' in font else '400')
        suffix=('BoldItalic' if int(selected_weight)>=600 and selected_shape!='normal' else 'Bold' if int(selected_weight)>=600 else 'Italic' if selected_shape!='normal' else 'Regular')
        candidate=selected_family+'-'+suffix
        from .canvas import _FONT_KEYS
        old_font=candidate if candidate in _FONT_KEYS else next((name for name in (selected_family+'-Regular',selected_family+'-Italic',selected_family+'-Bold') if name in _FONT_KEYS),font)
    return {'font_size':size,'color':globals()['color'](values.get('color','inherit'),color),'font':old_font,
            'css_line_height':values.get('line-height'),
            'css_family':family,'css_shape':shape,'css_weight':weight,
            'font_family':family,'font_style':shape,'font_weight':weight}


def _sides(value,size,percent):
    tokens=value.split()
    if not 1<=len(tokens)<=4:error('Expected CSS 1-4 side lengths')
    v=[length(token,size,percent) for token in tokens]
    return (v*4)[:4] if len(v)==1 else [v[0],v[1],v[0],v[1]] if len(v)==2 else [v[0],v[1],v[2],v[1]] if len(v)==3 else v

def _multiply(a,b):
    A,B,C,D,E,F=a;g,h,i,j,k,l=b
    return (A*g+C*h,B*g+D*h,A*i+C*j,B*i+D*j,A*k+C*l+E,B*k+D*l+F)

def _transform(value,size,width,height):
    if value in {'none',''}:return (1.,0.,0.,1.,0.,0.)
    matrix=(1.,0.,0.,1.,0.,0.);last=0
    for m in re.finditer(r'([a-zA-Z]+)\(([^()]*)\)',value):
        if value[last:m.start()].strip():error('Invalid static transform')
        last=m.end();name=m[1];parts=re.split(r'\s*,\s*|\s+',m[2].strip())
        def angle(v):
            if v.endswith('deg'):return float(v[:-3])*math.pi/180
            if v.endswith('rad'):return float(v[:-3])
            if v.endswith('turn'):return float(v[:-4])*2*math.pi
            if v=='0':return 0.
            error('Invalid transform angle')
        if name=='matrix' and len(parts)==6:t=tuple(float(p) for p in parts)
        elif name in {'translate','translateX','translateY'}:
            x=length(parts[0],size,height if name=='translateY' else width);y=length(parts[1],size,height) if len(parts)>1 else 0.
            if name=='translateY':x,y=0.,x
            t=(1,0,0,1,x,y)
        elif name in {'scale','scaleX','scaleY'}:
            x=float(parts[0]);y=float(parts[1]) if len(parts)>1 else x
            if name=='scaleX':y=1
            if name=='scaleY':x,y=1,x
            t=(x,0,0,y,0,0)
        elif name=='rotate':a=angle(parts[0]);t=(math.cos(a),math.sin(a),-math.sin(a),math.cos(a),0,0)
        elif name in {'skewX','skewY'}:a=math.tan(angle(parts[0]));t=(1,0,a,1,0,0) if name=='skewX' else (1,a,0,1,0,0)
        else:error('Unsupported static transform '+name)
        if not all(math.isfinite(v) for v in t):error('Invalid transform matrix')
        matrix=_multiply(matrix,t)
    if value[last:].strip():error('Invalid static transform')
    return matrix

def _recolor(commands,paint):
    out=[]
    for command in commands:
        if isinstance(command,CommandGroup):out.append(replace(command,commands=_recolor(command.commands,paint)))
        elif isinstance(command,(Glyph,Rule,Path)):out.append(replace(command,color=paint))
    return tuple(out)

@lru_cache(maxsize=128)
def _font_cell(font,size):
    """Pinned browser inline font cell, from the bundled face's hhea.

    CSS inline background/border uses the outer span font, not the ink of
    an inner mathnormal glyph. Chrome rounds each ascent/descent to CSS px.
    Native TextMetrics fontBoundingBox includes different line-gap treatment
    and is deliberately not substituted for these locked font metrics.
    """
    data=files('py_katex').joinpath('data','fonts','KaTeX_'+font+'.ttf').read_bytes()
    count=struct.unpack_from('>H',data,4)[0];tables={}
    for i in range(count):
        tag,checksum,offset,length_=struct.unpack_from('>4sIII',data,12+16*i)
        tables[tag]=offset
    units=struct.unpack_from('>H',data,tables[b'head']+18)[0]
    ascent,descent,gap=struct.unpack_from('>hhh',data,tables[b'hhea']+4)
    return math.floor(ascent*size/units+.5),math.floor(-descent*size/units+.5),(ascent-descent+gap)*size/units


def apply_html(box,attributes,*,font_size,color,class_styles=(),outer_font='Main-Regular',outer_style=None,outer_weight=None,outer_line_height='1.2'):
    values=styles(attributes,class_styles);size=font_size
    if values.get('display')=='none':return MathBox(0,0,0,diagnostics=box.diagnostics)
    if values.get('display','inline') not in {'inline','inline-block','block','none','contents'}:error('Unsupported static HTML display')
    if values.get('visibility','visible') not in {'visible','hidden','collapse'}:error('Unsupported CSS visibility')
    if values.get('visibility') in {'hidden','collapse'}:return replace(box,commands=())
    if values.get('display')=='contents':return box
    if values.get('position','static') not in {'static','relative'}:error('Only static/relative CSS positioning has a native inline layout')
    if values.get('white-space','nowrap') not in {'normal','nowrap','pre','pre-wrap','pre-line','break-spaces'}:error('Unsupported white-space')
    if values.get('box-sizing','content-box') not in {'content-box','border-box'}:error('Unsupported box-sizing')
    opacity=float(values.get('opacity',1))
    if not math.isfinite(opacity):error('Invalid opacity')
    opacity=max(0.,min(1.,opacity));w=box.width
    cell_ascent,cell_descent,normal_line_height=_font_cell(outer_font,size)
    inline=values.get('display','inline') in {'inline','contents'}
    line=values.get('line-height',outer_line_height)
    if line in ('inherit','unset'):line=outer_line_height
    line_height=normal_line_height if line=='normal' else float(line)*size if re.fullmatch(r'[\d.]+',line) else length(line,size,size)
    if line_height<0:error('Negative line height')
    h=cell_ascent+cell_descent if inline else line_height
    if not inline:
        cell_ascent+=(line_height-cell_ascent-cell_descent)/2
        cell_descent=line_height-cell_ascent
    # Width and height affect replaced/static inline boxes, never TeX glyph scale.
    targetw=length(values['width'],size,w) if not inline and values.get('width') not in (None,'auto') else w
    targeth=length(values['height'],size,h) if not inline and values.get('height') not in (None,'auto') else h
    for prop in ('min-width','max-width','min-height','max-height'):
        if inline:continue  # CSS non-replaced inline sizing does not apply.
        if values.get(prop) in (None,'none','auto'):continue
        amount=length(values[prop],size,w if prop.endswith('width') else h)
        if prop=='min-width':targetw=max(targetw,amount)
        elif prop=='max-width':targetw=min(targetw,amount)
        elif prop=='min-height':targeth=max(targeth,amount)
        else:targeth=min(targeth,amount)
    if min(targetw,targeth)<0:error('Negative static CSS box size')
    top,right,bottom,left=_sides(values.get('padding','0'),size,w)
    mt,mr,mb,ml=_sides(values.get('margin','0'),size,w)
    if inline:mt=mb=0.  # Inline vertical margins do not move its baseline.
    if min(top,right,bottom,left)<0:error('Negative padding')
    border=values.get('border','').split();bw=length(values.get('border-width','0'),size);bs=values.get('border-style','none');bc=values.get('border-color',color)
    for token in border:
        if token in {'solid','none','hidden','dashed','dotted','double'}:bs=token
        elif re.fullmatch(r'[\d.]+(?:px|em|pt)?',token):bw=length(token,size)
        else:bc=token
    if bs not in {'none','hidden','solid','dashed','dotted','double'}:error('Unsupported border style')
    if bs in {'none','hidden'}:bw=0.
    if bw<0:error('Negative border width')
    radius=length(values.get('border-radius','0'),size,min(targetw,targeth))
    if radius<0:error('Negative border radius')
    width=targetw+left+right+2*bw;height=targeth+top+bottom+2*bw
    if not inline and values.get('box-sizing')=='border-box':width=max(targetw,left+right+2*bw);height=max(targeth,top+bottom+2*bw)
    x=left+bw+ml;y=-mt;commands=[]
    borderleft=ml;bordertop=-cell_ascent-top-bw-mt
    bg=values.get('background-color',values.get('background','transparent'))
    def rounded(xx,yy,ww,hh,rr):
        rr=min(rr,ww/2,hh/2)
        return f'M{xx+rr:g} {yy:g}H{xx+ww-rr:g}Q{xx+ww:g} {yy:g} {xx+ww:g} {yy+rr:g}V{yy+hh-rr:g}Q{xx+ww:g} {yy+hh:g} {xx+ww-rr:g} {yy+hh:g}H{xx+rr:g}Q{xx:g} {yy+hh:g} {xx:g} {yy+hh-rr:g}V{yy+rr:g}Q{xx:g} {yy:g} {xx+rr:g} {yy:g}Z'
    if bg!='transparent':
        paint=globals()['color'](bg,color)
        commands.append(Path(rounded(ml,bordertop,width,height,radius),color=paint) if radius else Rule(ml,bordertop,width,height,paint))
    if bw:
        paint=globals()['color'](bc,color)
        if radius and bs!='solid':error('Rounded dashed HTML border is outside the rectangular dash adapter')
        if radius:commands.append(Path(rounded(borderleft+bw/2,bordertop+bw/2,max(0,width-bw),max(0,height-bw),max(0,radius-bw/2)),color=paint,stroke_width=bw))
        elif bs=='solid':commands.extend((Rule(borderleft,bordertop,width,bw,paint),Rule(borderleft,bordertop+height-bw,width,bw,paint),Rule(borderleft,bordertop,bw,height,paint),Rule(borderleft+width-bw,bordertop,bw,height,paint)))
        else:
            # Explicit repeating edge geometry preserves dash/dot/double styles.
            gap=bw*(1 if bs=='dotted' else 3)
            if bs=='double':
                for inset in (0,bw*2/3):
                    thick=bw/3;commands.extend((Rule(borderleft,bordertop+inset,width,thick,paint),Rule(borderleft,bordertop+height-thick-inset,width,thick,paint),Rule(borderleft+inset,bordertop,thick,height,paint),Rule(borderleft+width-thick-inset,bordertop,thick,height,paint)))
            else:
                for z in range(math.ceil(width/(2*gap))):
                    offset=z*2*gap;lengthx=min(gap,width-offset);commands.extend((Rule(borderleft+offset,bordertop,lengthx,bw,paint),Rule(borderleft+offset,bordertop+height-bw,lengthx,bw,paint)))
                for z in range(math.ceil(height/(2*gap))):
                    offset=z*2*gap;lengthy=min(gap,height-offset);commands.extend((Rule(borderleft,bordertop+offset,bw,lengthy,paint),Rule(borderleft+width-bw,bordertop+offset,bw,lengthy,paint)))
    spacing=length(values.get('letter-spacing','0'),size);word=length(values.get('word-spacing','0'),size)
    body=[];advance=0.
    for command in box.commands:
        if isinstance(command,Glyph):body.append(replace(command,x=command.x+advance));advance+=spacing*len(command.text)+word*command.text.count(' ')
        else:body.append(command)
    if advance:width+=advance
    clip=None
    for prop in ('overflow','overflow-x','overflow-y'):
        if values.get(prop,'visible') not in {'visible','hidden','clip','scroll','auto'}:error('Unsupported overflow value')
    if any(values.get(p) in {'hidden','clip','scroll','auto'} for p in ('overflow','overflow-x','overflow-y')):clip=(0,-box.height,targetw,targeth)
    if 'clip' in values and values['clip']!='auto':
        match=re.fullmatch(r'rect\((.*)\)',values['clip'])
        if not match:error('Unsupported CSS clip')
        v=[length(t,size) for t in re.split(r'\s*,\s*|\s+',match[1].strip())]
        if len(v)!=4:error('CSS clip requires four lengths')
        clip=(v[3],v[0],max(0,v[1]-v[3]),max(0,v[2]-v[0]))
    if 'clip-path' in values and values['clip-path']!='none':error('Only rectangular clip is supported in native math HTML')
    alignment=values.get('text-align','left')
    if alignment not in {'left','right','center','start','end','justify'}:error('Unsupported text alignment')
    x+=max(0,targetw-box.width)/2 if alignment=='center' else max(0,targetw-box.width) if alignment in {'right','end'} else 0
    body_index=len(commands)
    commands.append(CommandGroup(tuple(body),x=x,y=y,clip=clip))
    decoration=values.get('text-decoration-line',values.get('text-decoration','none'))
    tokens=re.findall(r'(?:rgb|hsl)a?\([^)]*\)|[^\s]+',decoration)
    line_style=next((token for token in tokens if token in {'solid','dashed','dotted','double','wavy'}),'solid')
    paint=globals()['color'](values.get('text-decoration-color',color),color)
    for token in tokens:
        if token not in {'none','underline','overline','line-through','solid','dashed','dotted','double','wavy'}:paint=globals()['color'](token,color)
    thickness=values.get('text-decoration-thickness','auto')
    thick=max(.5,size*.05) if thickness in {'auto','from-font'} else length(thickness,size)
    if thick<=0:error('Text decoration thickness must be positive')
    for token in tokens:
        if token not in {'underline','overline','line-through'}:continue
        yy=box.depth+size*.08 if token=='underline' else -box.height if token=='overline' else -size*.25
        ww=max(0,targetw+advance)
        if line_style=='solid':commands.append(Rule(x,yy,ww,thick,paint))
        elif line_style=='double':commands.extend((Rule(x,yy,ww,thick,paint),Rule(x,yy+3*thick,ww,thick,paint)))
        elif line_style in {'dashed','dotted'}:
            gap=thick if line_style=='dotted' else thick*3
            for i in range(math.ceil(ww/(gap*2))):commands.append(Rule(x+i*gap*2,yy,min(gap,ww-i*gap*2),thick,paint))
        else:
            pieces=[f'M{x:g} {yy:g}'];step=4*thick;leftover=ww;xx=x;sign=1
            while leftover>0:
                span=min(step,leftover);pieces.append(f'Q{xx+span/2:g} {yy+sign*2*thick:g} {xx+span:g} {yy:g}');xx+=span;leftover-=span;sign=-sign
            commands.append(Path(' '.join(pieces),color=paint,stroke_width=thick))
    filtering=values.get('filter','none')
    if filtering!='none' and not re.fullmatch(r'(?:blur\([\d.]+px\)|drop-shadow\([^()]+\))(?:\s+(?:blur\([\d.]+px\)|drop-shadow\([^()]+\)))*',filtering):error('Unsupported native static CSS filter')
    shadows=[]
    if values.get('text-shadow','none')!='none':
        for spec in re.split(r',(?![^()]*\))',values['text-shadow']):
            parts=spec.split();lengths=[];paint=color
            for token in parts:
                if re.fullmatch(r'[-\d.]+(?:px|em|pt)?',token):lengths.append(length(token,size))
                else:paint=globals()['color'](token,color)
            if not 2<=len(lengths)<=3:error('Invalid text shadow')
            dx,dy=lengths[:2];blur=lengths[2] if len(lengths)>2 else 0.
            shadows.append(CommandGroup(_recolor(tuple(body),paint),x=x+dx,y=y+dy,filter=f'blur({blur:g}px)' if blur else 'none'))
    # Source text shadows paint below glyphs, above the enclosing background.
    if shadows:commands[body_index:body_index]=list(reversed(shadows))
    dx=length(values.get('left','0'),size,width)-length(values.get('right','0'),size,width)
    dy=length(values.get('top','0'),size,height)-length(values.get('bottom','0'),size,height)
    align=values.get('vertical-align','baseline')
    if align in {'baseline','normal'}:shift=0.
    elif align=='middle':shift=(box.height-box.depth)/2-size*.25
    elif align in {'sub','super'}:shift=-size*.2 if align=='super' else size*.2
    elif align in {'top','text-top'}:shift=box.height-.8*size
    elif align in {'bottom','text-bottom'}:shift=.2*size-box.depth
    else:shift=-length(align,size,height)
    matrix=_transform(values.get('transform',''),size,width,height)
    origin=values.get('transform-origin','50% 50%').split()
    keywords={'left':'0%','right':'100%','top':'0%','bottom':'100%','center':'50%'}
    ox=length(keywords.get(origin[0],origin[0]),size,width);oy=length(keywords.get(origin[1],origin[1]),size,height)+bordertop if len(origin)>1 else height/2+bordertop
    matrix=_multiply(_multiply((1,0,0,1,ox,oy),matrix),(1,0,0,1,-ox,-oy))
    # Source makeSpan retains child TeX metrics for an unpainted inline
    # wrapper. A font cell is a background/border paint extent, not a
    # replacement for the nucleus's height in fractions and scripts.
    paint_cell=bg!='transparent' or bw or not inline
    bounds_top=bordertop if paint_cell else -box.height
    bounds_bottom=bordertop+height+mb if paint_cell else box.depth
    a,b,c,d,e,f=matrix;corners=[(a*xx+c*yy+e+dx,b*xx+d*yy+f+dy+shift) for xx in (0,width+ml+mr) for yy in (bounds_top,bounds_bottom)]
    minx=min(p[0] for p in corners);maxx=max(p[0] for p in corners);miny=min(p[1] for p in corners);maxy=max(p[1] for p in corners)
    for shadow in shadows:
        blur=float(re.search(r'[\d.]+',shadow.filter)[0]) if shadow.filter!='none' else 0.
        minx=min(minx,shadow.x-3*blur);maxx=max(maxx,shadow.x+box.width+3*blur)
        miny=min(miny,shadow.y-box.height-3*blur);maxy=max(maxy,shadow.y+box.depth+3*blur)
    for shadow in re.findall(r'drop-shadow\(([^()]*)\)',filtering):
        dimensions=[float(v) for v in re.findall(r'([-+]?[\d.]+)px',shadow)]
        if len(dimensions) not in (2,3):error('drop-shadow requires pixel offsets and optional blur')
        sx,sy=dimensions[:2];blur=dimensions[2] if len(dimensions)>2 else 0.
        old=(minx,miny,maxx,maxy);minx=min(minx,old[0]+sx-3*blur);maxx=max(maxx,old[2]+sx+3*blur);miny=min(miny,old[1]+sy-3*blur);maxy=max(maxy,old[3]+sy+3*blur)
    for blur in re.findall(r'blur\(([\d.]+)px\)',filtering):
        expand=3*float(blur);minx-=expand;maxx+=expand;miny-=expand;maxy+=expand
    return MathBox(max(0,maxx-minx),max(0,-miny),max(0,maxy),(CommandGroup(tuple(commands),x=dx-minx,y=dy+shift,opacity=opacity,matrix=matrix,filter=filtering),),box.atom,diagnostics=box.diagnostics)

def layout_image(node,*,font_size,color,dimension,resources):
    image=resolve_image(node.get('src',node.value),resources)
    height=dimension(node.get('height',(.9,'em')));total=node.get('totalheight',(0,'em'));depth=dimension(total)-height if total[0]>0 else 0.
    totalheight=height+depth;width=dimension(node.get('width',(0,'em'))) if node.get('width',(0,'em'))[0]>0 else image.width/image.height*totalheight
    if not all(math.isfinite(v) for v in (width,height,depth)) or min(width,totalheight)<0:raise ParseError('Invalid includegraphics dimensions',node.position,'INVALID_IMAGE_SIZE')
    return MathBox(width,height,depth,(ImageCommand(image,0,-height,width,totalheight),))
