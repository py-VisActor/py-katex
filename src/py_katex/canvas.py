"""Owner-thread public Canvas adapter for immutable native TeX draw commands.

The layout uses bundled KaTeX metrics. This module registers the matching bundled
TTFs explicitly; it never substitutes a system mathematical font or asks a DOM,
SVG host, JavaScript engine or another drawing backend to lay out a formula.
"""
from __future__ import annotations
from importlib.resources import files,as_file
import math,threading
from .model import MathBox,Glyph,Rule,Path,ImageCommand,CommandGroup,ParseError,RenderResult

_FONT_KEYS=frozenset({'AMS-Regular','Caligraphic-Bold','Caligraphic-Regular','Fraktur-Bold',
    'Fraktur-Regular','Main-Bold','Main-BoldItalic','Main-Italic','Main-Regular',
    'Math-BoldItalic','Math-Italic','SansSerif-Bold','SansSerif-Italic','SansSerif-Regular',
    'Script-Regular','Size1-Regular','Size2-Regular','Size3-Regular','Size4-Regular','Typewriter-Regular'})
_registered=threading.local()

def _error(message,code='INVALID_DRAW_COMMAND'):
    raise ParseError(message,code=code)

def _finite(*values):
    return all(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) for value in values)

def font_alias(key:str)->str:
    if key.startswith(('system:','external:')):return key.split(':',1)[1].split('|',1)[0]
    if key not in _FONT_KEYS:_error(f'Unknown bundled KaTeX font: {key}','UNKNOWN_FONT')
    return 'PyKaTeX_'+key

def _font(key:str):
    from py_skia_canvas import FontLibrary,__version__
    if __version__!='0.1.0a18':_error('Expected py-skia-canvas 0.1.0a18','DEPENDENCY_VERSION')
    alias=font_alias(key)
    seen=getattr(_registered,'keys',None)
    if seen is None:seen=set();_registered.keys=seen
    if key not in seen or not FontLibrary.has(alias):
        path=files('py_katex').joinpath('data','fonts','KaTeX_'+key+'.ttf')
        if not path.is_file():_error(f'Bundled font file missing for {key}','MISSING_FONT')
        with as_file(path) as native_path:FontLibrary.use(alias,str(native_path))
        if not FontLibrary.has(alias):_error(f'Could not register bundled font {key}','MISSING_FONT')
        seen.add(key)
    style='italic' if key.endswith(('Italic','BoldItalic')) else 'normal'
    weight='700' if key.endswith(('Bold','BoldItalic')) else '400'
    return alias,style,weight

def glyph_font_alias(command):
    if command.font_resource is None and not command.font.startswith(('system:','external:')) and (command.font_style is not None or command.font_weight is not None):
        return font_alias(_bundled_face(command)[0])
    return font_alias(command.font)


def _bundled_face(command):
    """Lock the physical face before synthesizing missing CSS axes."""
    _,style,weight=_font(command.font)
    style=command.font_style or style
    weight={'normal':'400','bold':'700'}.get(str(command.font_weight or weight),str(command.font_weight or weight))
    if style not in {'normal','italic','oblique'} or not weight.isdigit() or not 1<=int(weight)<=1000:_error('Invalid glyph face override')
    if command.font_style is None and command.font_weight is None:return command.font,0.,0.
    italic=style!='normal';family=command.font.split('-',1)[0]
    def rank(key):
        return (key.endswith(('Italic','BoldItalic'))!=italic,abs((700 if key.endswith(('Bold','BoldItalic')) else 400)-int(weight)),key)
    key=min((item for item in _FONT_KEYS if item.split('-',1)[0]==family),key=rank)
    _,actual_style,actual_weight=_font(key)
    # Skia SkTextFormatParams.h fake-bold interpolation, expressed using the
    # public Canvas stroke+fill operations rather than a family matcher.
    fraction=1/24+(1/32-1/24)*min(1.,max(0.,(command.size-9)/27))
    stroke=command.size*fraction if int(weight)>=600 and int(actual_weight)<600 else 0.
    return key,stroke,-.25 if italic and actual_style=='normal' else 0.


def _external_font(resource):
    from hashlib import sha256
    from tempfile import TemporaryDirectory
    from pathlib import Path as FilePath
    from py_skia_canvas import FontLibrary
    from .resources import MAX_BYTES
    if len(resource.data)>MAX_BYTES:_error('Fallback font byte budget exceeded','RESOURCE_BUDGET')
    digest=sha256(resource.data).hexdigest();alias='PyKaTeX_Fallback_'+digest
    if not FontLibrary.has(alias):
        folder=getattr(_registered,'font_folder',None)
        if folder is None:folder=TemporaryDirectory(prefix='py-katex-fonts-');_registered.font_folder=folder
        path=FilePath(folder.name)/(digest+'.ttf')
        if not path.exists():path.write_bytes(resource.data)
        FontLibrary.use(alias,str(path))
        if not FontLibrary.has(alias):_error('Cannot register explicit fallback font','MISSING_FONT')
    weight={'normal':'400','bold':'700'}.get(resource.weight,resource.weight)
    if resource.style not in {'normal','italic','oblique'} or not str(weight).isdigit() or not 1<=int(weight)<=1000:_error('Invalid explicit font face','INVALID_RESOURCE')
    return alias,resource.style,str(weight)


def _system_family_allowed(family):
    from py_skia_canvas import FontLibrary
    if not isinstance(family,str) or any(ch in family for ch in '"\\|') or any(ord(ch)<32 for ch in family):return False
    return family in {'serif','sans-serif','monospace'} or FontLibrary.has(family)


def _coverage_pixels(family,style,weight,text):
    """Public native raster witness for fonts whose glyphs have no outlines.

    Color bitmap/COLR/SVG glyphs may legitimately return an empty Path2D. Compare
    actual transparent-surface RGBA against the same font's missing-glyph
    control, never against a fabricated Unicode metric or replacement glyph.
    """
    from py_skia_canvas import Canvas
    from hashlib import sha256
    canvas=Canvas(192,160);canvas.gpu=False;ctx=canvas.getContext('2d')
    ctx.font=f'{style} {weight} 64px "{family}"';ctx.textAlign='left';ctx.textBaseline='alphabetic';ctx.direction='ltr';ctx.textWrap=False
    ctx.fillStyle='black';ctx.fillText(text,32,112)
    data=bytes(ctx.getImageData(0,0,192,160).data)
    return any(data[index] for index in range(3,len(data),4)),sha256(data).digest()


def _platform_covers(family,text,style='normal',weight='400',context=None):
    from py_skia_canvas import Canvas
    if not _system_family_allowed(family):return False
    cache=getattr(_registered,'platform_coverage',None)
    if cache is None:cache={};_registered.platform_coverage=cache
    if context is None:
        canvas=Canvas(1,1);canvas.gpu=False;context=canvas.getContext('2d')
    context.save()
    try:
        context.font=f'{style} {weight} 64px "{family}"';context.textAlign='left';context.textBaseline='alphabetic';context.direction='ltr';context.textWrap=False
        missing_outline=None;missing_pixels=None
        for ch in text:
            if ch.isspace() or ord(ch) in {0x200c,0x200d,0xfe0e,0xfe0f}:continue
            key=(family,style,weight,ch)
            if key not in cache:
                if missing_outline is None:missing_outline=context.outlineText(chr(0x10ffff)).d
                outline=context.outlineText(ch).d
                if outline and outline!=missing_outline:cache[key]=True
                else:
                    if missing_pixels is None:missing_pixels=_coverage_pixels(family,style,weight,chr(0x10ffff))
                    painted,pixels=_coverage_pixels(family,style,weight,ch)
                    cache[key]=painted and pixels!=missing_pixels[1]
            if not cache[key]:return False
        return True
    finally:context.restore()


def _platform_candidates(primary):
    from py_skia_canvas import FontLibrary
    names=FontLibrary.families
    priority=('Segoe UI Symbol','Segoe UI Emoji','Segoe UI','Arial Unicode MS',
              'Noto Sans Symbols 2','Noto Sans Symbols','Noto Color Emoji',
              'Apple Color Emoji','Symbola','DejaVu Sans')
    values=[primary]
    values.extend(name for name in priority if name in names)
    values.extend(name for name in names if not name.startswith(('PyKaTeX_','Independent')))
    return tuple(dict.fromkeys(name for name in values if _system_family_allowed(name)))


def measure_fallback(text,options,size,*,font='',style='normal',weight='normal'):
    """Source Unicode fallback only; bundled mathematical metrics stay intact.

    Explicit fonts require cmap coverage. Platform serif uses actual native
    outlines and rejects missing-glyph equality; no fictional KaTeX metrics.
    """
    from py_skia_canvas import Canvas,FontLibrary,__version__
    from .resources import font_covers
    if __version__!='0.1.0a18':_error('Expected Canvas0.1.0a18','DEPENDENCY_VERSION')
    if not isinstance(text,str) or len(text)>20000 or not _finite(size) or not 0<size<=16384:_error('Invalid fallback request','INVALID_MEASUREMENT')
    from .resources import validate_font_resources
    validate_font_resources(options.fallback_fonts)
    for explicit in options.fallback_fonts:
        try:_external_font(explicit)
        except Exception as exc:
            if isinstance(exc,ParseError):raise
            raise ParseError('Cannot decode explicit fallback font: '+str(exc),code='INVALID_RESOURCE') from exc
    resource=next((item for item in options.fallback_fonts if font_covers(item.data,text)),None)
    if resource:
        from dataclasses import replace
        resource=replace(resource,style=style if style!='normal' else resource.style,weight=weight if weight not in {'normal','400'} else resource.weight)
        alias,style,weight=_external_font(resource);key='external:'+alias
    else:
        alias='sans-serif' if 'SansSerif' in font else 'monospace' if 'Typewriter' in font else 'serif'
        weight={'normal':'400','bold':'700'}.get(weight,weight);key='system:'+alias+'|'+style+'|'+weight
    canvas=Canvas(1,1);canvas.gpu=False;ctx=canvas.getContext('2d')
    ctx.font=f'{style} {weight} {size:g}px "{alias}"';ctx.textAlign='left';ctx.textBaseline='alphabetic';ctx.direction='ltr';ctx.textWrap=False
    if resource is None:
        primary=font.split('|')[0].removeprefix('system:') if font.startswith('system:') else font if FontLibrary.has(font) else alias
        alias=next((family for family in _platform_candidates(primary) if _platform_covers(family,text,style,weight,ctx)),None)
        if alias is None:_error('Platform fallback has no real glyph coverage for '+','.join(f'U+{ord(ch):04X}' for ch in text),'MISSING_GLYPH')
        key='system:'+alias+'|'+style+'|'+weight
        ctx.font=f'{style} {weight} {size:g}px "{alias}"'
    metric=ctx.measureText(text)
    w=metric.width;a=metric.actualBoundingBoxAscent;d=metric.actualBoundingBoxDescent
    if not _finite(w,a,d) or w<0 or a+d<0:_error('Invalid native fallback metrics','INVALID_MEASUREMENT')
    return {'width':w,'height':a,'depth':d,'font':key,'font_resource':resource,'italic':0.,'skew':0.}


def _glyph_state(context,command):
    if command.font_resource is not None:
        from .resources import font_covers
        if not font_covers(command.font_resource.data,command.text):_error('Fallback font lacks glyph coverage','MISSING_GLYPH')
        alias,style,weight=_external_font(command.font_resource)
    elif command.font.startswith('system:'):
        parts=command.font.split('|');family=parts[0]
        if not _system_family_allowed(family.split(':',1)[1]):_error('Unavailable platform fallback family','UNKNOWN_FONT')
        alias=family.split(':',1)[1];style=parts[1] if len(parts)>1 else 'normal';weight=parts[2] if len(parts)>2 else '400'
        if style not in {'normal','italic','oblique'} or not weight.isdigit() or not 1<=int(weight)<=1000:_error('Invalid platform fallback face')
        if not _platform_covers(alias,command.text,style,weight):_error('Platform font has no real glyph coverage','MISSING_GLYPH')
    else:
        key,stroke,shear=_bundled_face(command)
        alias,style,weight=_font(key)
        context.font=f'{style} {weight} {command.size:g}px "{alias}"'
        context.textAlign='left';context.textBaseline='alphabetic';context.direction='ltr'
        context.textWrap=False;context.textDecoration='none';context.letterSpacing='0px';context.wordSpacing='0px'
        return stroke,shear
    if command.font_style is not None:
        if command.font_style not in {'normal','italic','oblique'}:_error('Invalid glyph style override')
        style=command.font_style
    if command.font_weight is not None:
        value={'normal':'400','bold':'700'}.get(str(command.font_weight),str(command.font_weight))
        if not value.isdigit() or not 1<=int(value)<=1000:_error('Invalid glyph weight override')
        weight=value
    # Numeric weight avoids a18's ambiguous `italic normal` reset.
    context.font=f'{style} {weight} {command.size:g}px "{alias}"'
    context.textAlign='left';context.textBaseline='alphabetic';context.direction='ltr'
    context.textWrap=False;context.textDecoration='none';context.letterSpacing='0px';context.wordSpacing='0px'
    return 0.,0.


def draw(context,box:MathBox,x:float=0,y:float=0)->None:
    """Draw logical-pixel commands at left baseline (x,y), on context owner.

    Native Context methods enforce its creation-thread ownership. Registration
    is thread-local too; only immutable MathBox commands/encoded bytes transfer.
    Caller transforms/opacity are retained, and all state changes are restored.
    """
    if not isinstance(box,MathBox) or not _finite(box.width,box.height,box.depth,x,y) or box.width<0 or box.height+box.depth<0:
        _error('Invalid mathematical box geometry','INVALID_BOX')
    stack=[(box.commands,0)];count=0
    while stack:
        commands,depth=stack.pop()
        if depth>128:_error('Mathematical group nesting budget exceeded','RENDER_BUDGET')
        count+=len(commands)
        if count>200_000:_error('Mathematical command budget exceeded','RENDER_BUDGET')
        for item in commands:
            if isinstance(item,CommandGroup):stack.append((item.commands,depth+1))
    from py_skia_canvas import Path2D
    context.save()
    try:
        context.translate(x,y)
        for command in box.commands:
            context.save()
            try:
                if isinstance(command,Glyph):
                    if not isinstance(command.text,str) or not _finite(command.x,command.y,command.size,command.scale_x) or command.size<=0 or command.scale_x==0:
                        _error('Invalid mathematical glyph')
                    stroke,shear=_glyph_state(context,command)
                    context.translate(command.x,command.y);context.scale(command.scale_x,1)
                    if shear:context.transform(1,0,shear,1,0,0)
                    context.fillStyle=command.color
                    if stroke:
                        context.strokeStyle=command.color;context.lineWidth=stroke;context.lineJoin='round';context.setLineDash([])
                        context.strokeText(command.text,0,0)
                    context.fillText(command.text,0,0)
                elif isinstance(command,Rule):
                    if not _finite(command.x,command.y,command.width,command.height) or min(command.width,command.height)<0:
                        _error('Invalid mathematical rule')
                    context.fillStyle=command.color
                    if command.width and command.height:context.fillRect(command.x,command.y,command.width,command.height)
                elif isinstance(command,Path):
                    if not _finite(command.x,command.y,command.scale_x,command.scale_y,command.stroke_width) or command.stroke_width<0 or not isinstance(command.d,str):
                        _error('Invalid mathematical path')
                    context.translate(command.x,command.y);context.scale(command.scale_x,command.scale_y)
                    if command.clip is not None:
                        if len(command.clip)!=4 or not _finite(*command.clip) or min(command.clip[2:])<0:_error('Invalid mathematical clip')
                        cx,cy,cw,ch=command.clip;clip=Path2D();clip.rect(cx,cy,cw,ch);context.clip(clip)
                    path=Path2D(command.d)
                    if command.stroke_width:
                        context.strokeStyle=command.color;context.lineWidth=command.stroke_width;context.setLineDash([]);context.stroke(path)
                    else:context.fillStyle=command.color;context.fill(path)
                elif isinstance(command,ImageCommand):
                    if not _finite(command.x,command.y,command.width,command.height,command.opacity) or min(command.width,command.height)<0 or not 0<=command.opacity<=1:_error('Invalid mathematical image')
                    from .resources import image_from_bytes
                    resource=command.resource
                    checked=image_from_bytes(resource.key,resource.data,resource.mime)
                    if (checked.width,checked.height)!=(resource.width,resource.height):_error('Image dimensions disagree with encoded data','INVALID_RESOURCE')
                    from py_skia_canvas import Image
                    image_data=resource.data
                    if resource.mime=='image/svg+xml' and command.width and command.height:
                        # SVG viewBox layout uses the concrete CSS viewport.
                        # Stretching an intrinsically decoded bitmap would lose
                        # preserveAspectRatio, including default xMidYMid meet.
                        from xml.etree import ElementTree as ET
                        ET.register_namespace('','http://www.w3.org/2000/svg')
                        root=ET.fromstring(image_data)
                        root.set('width',f'{command.width:g}px');root.set('height',f'{command.height:g}px')
                        root.set('style',root.get('style','')+f';width:{command.width:g}px;height:{command.height:g}px')
                        image_data=ET.tostring(root,encoding='utf-8')
                    native=Image(image_data)
                    if native.width<=0 or native.height<=0:_error('Native image decode produced no pixels','INVALID_RESOURCE')
                    context.globalAlpha=context.globalAlpha*command.opacity
                    if command.width and command.height:context.drawImage(native,command.x,command.y,command.width,command.height)
                elif isinstance(command,CommandGroup):
                    if not _finite(command.x,command.y,command.scale_x,command.scale_y,command.opacity) or not 0<=command.opacity<=1 or len(command.matrix)!=6 or not _finite(*command.matrix):_error('Invalid mathematical command group')
                    context.translate(command.x,command.y);context.scale(command.scale_x,command.scale_y);context.transform(*command.matrix)
                    if command.clip is not None:
                        if len(command.clip)!=4 or not _finite(*command.clip) or min(command.clip[2:])<0:_error('Invalid mathematical group clip')
                        clip=Path2D();clip.rect(*command.clip);context.clip(clip)
                    context.globalAlpha=context.globalAlpha*command.opacity
                    if command.filter!='none':
                        import re
                        if not re.fullmatch(r'(?:blur\([\d.]+px\)|drop-shadow\([^()]+\))(?:\s+(?:blur\([\d.]+px\)|drop-shadow\([^()]+\)))*',command.filter):_error('Invalid native mathematical filter')
                        context.filter=command.filter
                    draw(context,MathBox(0,0,0,command.commands))
                else:_error('Unknown mathematical drawing command')
            finally:context.restore()
    finally:context.restore()

def measure_bundled_text(text,font,size,*,style=None,weight=None):
    """Actual source-font kerning/ligatures for source-eligible text runs."""
    if not isinstance(text,str) or len(text)>20000 or not _finite(size) or size<=0:_error('Invalid bundled text request','INVALID_MEASUREMENT')
    from py_skia_canvas import Canvas
    canvas=Canvas(1,1);canvas.gpu=False;context=canvas.getContext('2d')
    _glyph_state(context,Glyph(text,0,0,font,size,font_style=style,font_weight=weight));metric=context.measureText(text)
    return {'width':metric.width,'height':metric.actualBoundingBoxAscent,'depth':metric.actualBoundingBoxDescent,'font':font,'italic':0.,'skew':0.,'font_ascent':metric.fontBoundingBoxAscent,'font_descent':metric.fontBoundingBoxDescent}


def _matrix_mul(a,b):
    A,B,C,D,E,F=a;g,h,i,j,k,l=b
    return (A*g+C*h,B*g+D*h,A*i+C*j,B*i+D*j,A*k+C*l+E,B*k+D*l+F)


def _rect_transform(rect,matrix):
    a,b,c,d,e,f=matrix;left,top,right,bottom=rect
    points=[(a*x+c*y+e,b*x+d*y+f) for x in (left,right) for y in (top,bottom)]
    return (min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points))


def _union(a,b):
    if a is None:return b
    if b is None:return a
    return min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])


def _intersection(a,b):
    if a is None or b is None:return None
    value=max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])
    return value if value[2]>value[0] and value[3]>value[1] else None


def _visible_color(color):
    import re
    value=str(color).strip().lower()
    if value=='transparent':return False
    if re.fullmatch(r'#[0-9a-f]{8}',value) and value[-2:]=='00':return False
    if re.fullmatch(r'#[0-9a-f]{4}',value) and value[-1:]=='0':return False
    if re.search(r'(?:,|/)\s*0(?:\.0*)?%?\s*\)$',value) and (value.startswith(('rgba','hsla')) or '/' in value):return False
    return True


def _filter_bounds(rect,filtering,matrix):
    if rect is None or filtering=='none':return rect
    import re
    # Canvas filters operate after the primitive transform, in device pixels.
    result=rect
    for function,arguments in re.findall(r'(blur|drop-shadow)\(([^()]*)\)',filtering):
        values=[float(value) for value in re.findall(r'([-+]?(?:\d+(?:\.\d*)?|\.\d+))px',arguments)]
        if function=='blur':
            if len(values)!=1 or values[0]<0:_error('Invalid blur footprint')
            extent=3*values[0];result=(result[0]-extent,result[1]-extent,result[2]+extent,result[3]+extent)
        else:
            if len(values) not in (2,3):_error('Invalid drop-shadow footprint')
            dx,dy=values[:2];blur=values[2] if len(values)==3 else 0
            if blur<0:_error('Negative drop-shadow blur')
            extent=3*blur;result=_union(result,(result[0]+dx-extent,result[1]+dy-extent,result[2]+dx+extent,result[3]+dy+extent))
    return result


def ink_bounds(box,context=None):
    """Actual native command ink in baseline coordinates (left,top,right,bottom).

    Logical TeX metrics are not rewritten. Native outline/path bounds and pure
    image/rule rectangles are composed through group affine transforms/clips.
    Conservative stroke/filter footprints prevent export clipping. No raster
    decoding, postprocessing, browser, or synthetic font metrics are used here.
    """
    if not isinstance(box,MathBox):_error('Expected MathBox','INVALID_BOX')
    from py_skia_canvas import Canvas,Path2D
    if context is None:
        canvas=Canvas(1,1);canvas.gpu=False;context=canvas.getContext('2d')
    budget=[0]
    def path_rect(path,matrix):
        if not path.d:return None
        bounds=path.transform(*matrix).bounds
        value=tuple(bounds[key] for key in ('left','top','right','bottom'))
        if not _finite(*value):_error('Invalid native path bounds','INVALID_MEASUREMENT')
        return value
    def rectangle(x,y,width,height):
        if not _finite(x,y,width,height) or min(width,height)<0:_error('Invalid mathematical rectangle')
        return (x,y,x+width,y+height)
    def walk(commands,matrix=(1,0,0,1,0,0),depth=0):
        if depth>128:_error('Mathematical group nesting budget exceeded','RENDER_BUDGET')
        budget[0]+=len(commands)
        if budget[0]>200000:_error('Mathematical command budget exceeded','RENDER_BUDGET')
        result=None
        for command in commands:
            rect=None
            if isinstance(command,Glyph):
                if not _finite(command.x,command.y,command.size,command.scale_x) or command.size<=0 or not command.scale_x:_error('Invalid mathematical glyph')
                if not _visible_color(command.color):continue
                stroke,shear=_glyph_state(context,command)
                local=_matrix_mul(matrix,(command.scale_x,0,command.scale_x*shear,1,command.x,command.y))
                outline=context.outlineText(command.text)
                rect=path_rect(outline,local)
                if rect is not None and stroke:
                    a,b,c,d,e,f=local
                    ex=stroke/2*math.hypot(a,c);ey=stroke/2*math.hypot(b,d)
                    rect=(rect[0]-ex,rect[1]-ey,rect[2]+ex,rect[3]+ey)
                if command.text.strip() and (rect is None or command.font_resource is not None or command.font.startswith(('system:','external:'))):
                    # A mixed fallback run may have outlines for ordinary
                    # letters but none for its color glyphs. Union the native
                    # actual TextMetrics, rather than trusting a partial path.
                    metrics=context.measureText(command.text)
                    bounds=(-metrics.actualBoundingBoxLeft,-metrics.actualBoundingBoxAscent,metrics.actualBoundingBoxRight,metrics.actualBoundingBoxDescent)
                    if not _finite(*bounds):_error('Invalid color glyph ink metrics','INVALID_MEASUREMENT')
                    if bounds[2]>bounds[0] and bounds[3]>bounds[1]:rect=_union(rect,_rect_transform(bounds,local))
            elif isinstance(command,Rule):
                if not _visible_color(command.color) or not command.width or not command.height:continue
                rect=_rect_transform(rectangle(command.x,command.y,command.width,command.height),matrix)
            elif isinstance(command,Path):
                if not _visible_color(command.color):continue
                if not _finite(command.x,command.y,command.scale_x,command.scale_y,command.stroke_width) or command.stroke_width<0:_error('Invalid mathematical path')
                local=_matrix_mul(matrix,(command.scale_x,0,0,command.scale_y,command.x,command.y))
                rect=path_rect(Path2D(command.d),local)
                if rect is not None and command.stroke_width:
                    a,b,c,d,e,f=local
                    # Default Canvas miterLimit10 bounds acute stroke joins too.
                    extent=command.stroke_width/2*max(math.hypot(a,c),math.hypot(b,d))*10
                    rect=(rect[0]-extent,rect[1]-extent,rect[2]+extent,rect[3]+extent)
                if command.clip is not None:
                    if len(command.clip)!=4:_error('Invalid mathematical path clip')
                    rect=_intersection(rect,_rect_transform(rectangle(*command.clip),local))
            elif isinstance(command,ImageCommand):
                if not _finite(command.opacity) or not 0<=command.opacity<=1:_error('Invalid image opacity')
                if command.opacity==0 or not command.width or not command.height:continue
                rect=_rect_transform(rectangle(command.x,command.y,command.width,command.height),matrix)
            elif isinstance(command,CommandGroup):
                if not _finite(command.x,command.y,command.scale_x,command.scale_y,command.opacity,*command.matrix) or len(command.matrix)!=6 or not 0<=command.opacity<=1:_error('Invalid mathematical group')
                if command.opacity==0:continue
                local=_matrix_mul(_matrix_mul(matrix,(command.scale_x,0,0,command.scale_y,command.x,command.y)),command.matrix)
                rect=_filter_bounds(walk(command.commands,local,depth+1),command.filter,local)
                if command.clip is not None:
                    if len(command.clip)!=4:_error('Invalid mathematical group clip')
                    rect=_intersection(rect,_rect_transform(rectangle(*command.clip),local))
            else:_error('Unknown mathematical command')
            result=_union(result,rect)
        return result
    context.save()
    try:return walk(box.commands)
    finally:context.restore()


def render_box(box:MathBox,*,format:str='png',backend:str='auto',padding:float=8,
               background:str='transparent',density:int=1,quality:float|None=None)->RenderResult:
    """Encode a native single-page formula; default Canvas device is preserved."""
    if backend not in {'auto','cpu','gpu'}:_error('backend must be auto/cpu/gpu','INVALID_BACKEND')
    format='jpg' if format=='jpeg' else format
    if format not in {'png','jpg','webp','svg','pdf'}:_error('Unsupported mathematical export format','UNSUPPORTED_FORMAT')
    if not _finite(padding) or padding<0 or not isinstance(density,int) or isinstance(density,bool) or density<1:
        _error('Invalid mathematical export dimensions','INVALID_EXPORT_OPTIONS')
    if quality is not None and (not _finite(quality) or not 0<=quality<=1):_error('quality must be in [0,1]','INVALID_EXPORT_OPTIONS')
    if not isinstance(box,MathBox) or not _finite(box.width,box.height,box.depth) or box.width<0 or box.height+box.depth<0:_error('Invalid mathematical box','INVALID_BOX')
    ink=ink_bounds(box)
    logical=(0.,-box.height,box.width,box.depth)
    extent=_union(logical,ink);left,top,right,bottom=extent
    width=max(1,math.ceil(right-left+2*padding));height=max(1,math.ceil(bottom-top+2*padding))
    if max(width,height)>32768 or width*height*density*density>64_000_000:_error('Formula image budget exceeded','RENDER_BUDGET')
    from py_skia_canvas import Canvas,__version__
    if __version__!='0.1.0a18':_error('Expected py-skia-canvas 0.1.0a18','DEPENDENCY_VERSION')
    canvas=Canvas(width,height)
    if backend=='cpu':canvas.gpu=False
    if backend=='gpu' and canvas.engine.get('renderer')!='GPU':_error('GPU required; Canvas selected CPU','GPU_UNAVAILABLE')
    context=canvas.getContext('2d');context.fillStyle=background;context.fillRect(0,0,width,height)
    draw(context,box,padding-left,padding-top)
    opts={'density':density}
    if quality is not None:opts['quality']=quality
    data=bytes(canvas.toBufferSync(format,opts));raster=format in {'png','jpg','webp'}
    mime={'png':'image/png','jpg':'image/jpeg','webp':'image/webp','svg':'image/svg+xml','pdf':'application/pdf'}[format]
    return RenderResult(data,width*density if raster else width,height*density if raster else height,mime,box,
        tuple((str(key),str(value)) for key,value in sorted(canvas.engine.items())))

__all__=['draw','render_box','font_alias','measure_fallback','measure_bundled_text','ink_bounds','glyph_font_alias']
