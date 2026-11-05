"""Canonical offline options, pure scene receipts and independent visual checks.

No formula execution at import. Callers supply already-constructed callbacks or
Macro values; no source/JSON expression is evaluated by this adapter.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import fields,is_dataclass,replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import base64,json,math,re,unicodedata
ROOT=Path(__file__).resolve().parents[1]

class ToolError(ValueError):pass

def digest(data):return sha256(data).hexdigest()

def _path(value,root):
    if not isinstance(value,(str,Path)):raise ToolError('Expected explicit resource path')
    result=Path(value).expanduser()
    if not result.is_absolute():result=root/result
    return result.resolve(strict=True)

def _image(entry,root):
    from py_katex.resources import image_resource,image_resource_from_file,image_from_data_uri
    if not isinstance(entry,dict):raise ToolError('Image resource must be an object')
    key=entry.get('key',entry.get('id'))
    if not isinstance(key,str) or not key:raise ToolError('Image requires key')
    sources=[name for name in ('path','dataUri','dataBase64') if name in entry]
    if len(sources)!=1:raise ToolError('Image requires exactly one explicit path/dataUri/dataBase64')
    if sources[0]=='path':image=image_resource_from_file(key,_path(entry['path'],root),entry.get('mime'))
    elif sources[0]=='dataUri':image=image_from_data_uri(entry['dataUri'],key)
    else:
        try:data=base64.b64decode(entry['dataBase64'],validate=True)
        except (ValueError,TypeError) as exc:raise ToolError('Invalid explicit image base64') from exc
        image=image_resource(key,data,entry.get('mime'))
    if entry.get('sha256') and digest(image.data)!=entry['sha256']:raise ToolError('Resource SHA mismatch: '+key)
    return image

def options_for_case(case,*,root=ROOT):
    from py_katex import Options,ResourceBundle,FontResource
    root=Path(root);provided=case.get('options',{})
    if isinstance(provided,Options):options=provided
    elif isinstance(provided,dict):
        values=dict(provided);values.setdefault('font_size',case.get('fontSize',28))
        if 'display' in case:values.setdefault('display_mode',case['display'])
        if 'macros' in case:values.setdefault('macros',case['macros'])
        options=Options(**values)
    else:raise ToolError('options must contain native snake_case fields or an Options instance')
    if 'resources' in case:
        raw=case['resources']
        entries=raw.get('images',[]) if isinstance(raw,dict) else raw
        if not isinstance(entries,list):raise ToolError('resources must be a list of explicit image descriptors')
        prior=options.resources.images if options.resources else ()
        options=replace(options,resources=ResourceBundle(tuple(prior)+tuple(_image(item,root) for item in entries)))
    if 'fallbackFonts' in case:
        fonts=[]
        for entry in case['fallbackFonts']:
            if not isinstance(entry,dict) or not entry.get('family'):raise ToolError('Fallback font needs family and explicit path')
            data=_path(entry['path'],root).read_bytes()
            if entry.get('sha256') and digest(data)!=entry['sha256']:raise ToolError('Fallback font SHA mismatch')
            fonts.append(FontResource(entry['family'],data,tuple(entry.get('scripts',())),entry.get('style','normal'),entry.get('weight','normal')))
        options=replace(options,fallback_fonts=options.fallback_fonts+tuple(fonts))
    if 'htmlStyles' in case:
        raw=case['htmlStyles'];styles=tuple(raw.items()) if isinstance(raw,dict) else tuple(tuple(item) for item in raw)
        options=replace(options,html_styles=options.html_styles+styles)
    return options

def normalized_case(case,*,root=ROOT):
    if not isinstance(case,dict) or not isinstance(case.get('tex'),str):raise ToolError('Case requires TeX string')
    if not isinstance(case.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,150}',case['id']):raise ToolError('Unsafe or invalid case ID')
    return {'id':case['id'],'tex':case['tex'],'options':options_for_case(case,root=root)}

def pure(value):
    if isinstance(value,bytes):return {'bytes':len(value),'sha256':digest(value)}
    if is_dataclass(value):return {'type':type(value).__name__,**{field.name:pure(getattr(value,field.name)) for field in fields(value)}}
    if isinstance(value,dict):return {str(key):pure(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return [pure(item) for item in value]
    if isinstance(value,float) and not math.isfinite(value):return str(value)
    if callable(value):return {'callable':getattr(value,'__qualname__',type(value).__name__)}
    if value is None or isinstance(value,(str,int,float,bool)):return value
    return {'type':type(value).__name__}

def normalize_text(text):
    if isinstance(text,(tuple,list)):text=''.join(str(item) for item in text)
    return ''.join(ch for ch in unicodedata.normalize('NFKD',str(text or '')) if not ch.isspace() and unicodedata.category(ch)!='Cf')

def matrix_multiply(a,b):
    A,B,C,D,E,F=a;g,h,i,j,k,l=b
    return (A*g+C*h,B*g+D*h,A*i+C*j,B*i+D*j,A*k+C*l+E,B*k+D*l+F)

def transform_point(matrix,x,y):
    a,b,c,d,e,f=matrix;return a*x+c*y+e,b*x+d*y+f

def transform_rect(matrix,rect):
    x,y,w,h=rect;points=[transform_point(matrix,xx,yy) for xx in (x,x+w) for yy in (y,y+h)]
    return (min(xx for xx,yy in points),min(yy for xx,yy in points),max(xx for xx,yy in points),max(yy for xx,yy in points))

def visible_color(value):
    value=str(value).lower().strip()
    if value=='transparent':return False
    if re.fullmatch(r'#[0-9a-f]{8}',value) and value[-2:]=='00':return False
    if re.fullmatch(r'#[0-9a-f]{4}',value) and value[-1]=='0':return False
    return not (re.search(r'(?:,|/)\s*0(?:\.0*)?%?\s*\)$',value) and (value.startswith(('rgba','hsla')) or '/' in value))

def flatten_commands(box):
    # Values are already the result of real native layout; this adapter only
    # composes positions and records command types, never draws replacement ink.
    out=[]
    def walk(commands,matrix=(1,0,0,1,0,0),opacity=1.,clips=(),depth=0):
        if depth>128:raise ToolError('Scene group depth exceeds contract')
        for command in commands:
            kind=type(command).__name__;value=pure(command)
            if kind=='CommandGroup':
                alpha=opacity*command.opacity
                if alpha<=0:continue
                child=matrix_multiply(matrix_multiply(matrix,(command.scale_x,0,0,command.scale_y,command.x,command.y)),command.matrix)
                child_clips=clips+(transform_rect(child,command.clip),) if command.clip else clips
                if any(c[2]<=c[0] or c[3]<=c[1] for c in child_clips):continue
                walk(command.commands,child,alpha,child_clips,depth+1)
            elif kind in ('Glyph','Rule','Path','ImageCommand'):
                alpha=opacity*(command.opacity if kind=='ImageCommand' else 1)
                if alpha<=0:continue
                value['worldMatrix']=matrix;value['worldOpacity']=alpha;value['worldClips']=clips
                if hasattr(command,'x'):value['x'],value['y']=transform_point(matrix,command.x,command.y)
                out.append(value)
            else:raise ToolError('Unknown native command type '+kind)
    walk(box.commands);return out

def decode_png(data):
    from PIL import Image
    if not isinstance(data,bytes) or not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ToolError('Native output is not PNG bytes')
    im=Image.open(BytesIO(data));im.load();rgba=im.convert('RGBA');white=Image.new('RGBA',rgba.size,'white');white.alpha_composite(rgba);return white.convert('RGB')

def image_ink_bbox(image):
    # Difference from white handles red/blue paint as well as dark glyphs.
    mask=image.point(lambda p:255-p).convert('RGB')
    # RGB getbbox counts any channel; threshold removes only near-white noise.
    mask=mask.point(lambda p:255 if p>0 else 0)
    return mask.getbbox()

def crop_pixels(image,rect):
    l,t,r,b=rect;l=max(0,math.floor(l));t=max(0,math.floor(t));r=min(image.width,math.ceil(r));b=min(image.height,math.ceil(b))
    return list(image.crop((l,t,max(l,r),max(t,b))).getdata()) if r>l and b>t else []

def _glyphs(flat,text=None):return [g for g in flat if g['type']=='Glyph' and (text is None or g['text']==text)]

def check_geometry(box,flat,checks):
    errors=[];results=[]
    for spec in checks or []:
        if not isinstance(spec,dict):raise ToolError('geometryChecks entries must be objects')
        kind=spec.get('type',spec.get('kind'));ok=True;detail=None;tolerance=float(spec.get('tolerance',1e-6))
        required={'logical_width':('value',),'min_baselines':('value',),'glyph_x':('text','value'),'glyph_y':('text','value'),'font_axes':('text',),'min_rule_thickness':('value',),'path_scale':('x','y'),'no_glyph':('text',),'glyph_run':('text',)}
        if kind in required and any(key not in spec for key in required[kind]):raise ToolError('Missing fields in geometry check '+kind)
        if kind=='logical_width':detail=box.width;ok=abs(detail-float(spec['value']))<=tolerance
        elif kind=='min_baselines':detail=len({round(g['y'],4) for g in _glyphs(flat)});ok=detail>=spec['value']
        elif kind in ('glyph_x','glyph_y'):
            matches=_glyphs(flat,spec['text']);index=spec.get('occurrence',0)
            if not isinstance(index,int) or index<0:raise ToolError('Invalid glyph occurrence')
            if index>=len(matches):ok=False;detail='glyph missing'
            else:detail=matches[index][kind[-1]];ok=abs(detail-float(spec['value']))<=tolerance
        elif kind=='font_axes':
            matches=_glyphs(flat,spec['text']);ok=False;detail=[]
            for glyph in matches:
                key=glyph['font'];resource=glyph.get('font_resource');parts=key.split('|')
                family=resource['family'] if resource else key.split('-',1)[0]
                if key.startswith('system:'):family=parts[0].split(':',1)[1]
                style=glyph.get('font_style') or (resource['style'] if resource else parts[1] if key.startswith('system:') and len(parts)>1 else 'italic' if 'Italic' in key else 'normal')
                weight=glyph.get('font_weight') or (resource['weight'] if resource else parts[2] if key.startswith('system:') and len(parts)>2 else '700' if 'Bold' in key else '400')
                weight={'normal':'400','bold':'700'}.get(str(weight),str(weight));actual={'family':family,'style':style,'weight':weight};detail.append(actual)
                if all(str(actual[k])==str(spec[k]) for k in ('family','style','weight') if k in spec):ok=True
        elif kind=='min_rule_thickness':
            rules=[command['height'] for command in flat if command['type']=='Rule' and command['height']>0];detail=min(rules) if rules else None;ok=detail is not None and detail+tolerance>=float(spec['value'])
        elif kind=='path_scale':
            detail=[(p['scale_x'],p['scale_y']) for p in flat if p['type']=='Path'];ok=any(abs(x-spec['x'])<=tolerance and abs(y-spec['y'])<=tolerance for x,y in detail)
        elif kind=='no_glyph':detail=len(_glyphs(flat,spec['text']));ok=detail==0
        elif kind=='glyph_run':detail=len(_glyphs(flat,spec['text']));ok=detail==spec.get('count',1)
        else:raise ToolError('Unknown geometry check '+str(kind))
        results.append({'type':kind,'status':'PASS' if ok else 'FAIL','actual':detail,'expected':spec})
        if not ok:errors.append('geometry '+str(kind)+' failed')
    return errors,results

def check_pixels(image,flat,checks,origin):
    errors=[];results=[]
    for spec in checks or []:
        if not isinstance(spec,dict):raise ToolError('pixelChecks entries must be objects')
        kind=spec.get('type',spec.get('kind'));ok=True;actual=None
        if kind=='ink_present':actual=image_ink_bbox(image);ok=actual is not None
        elif kind=='border_margin':
            actual=image_ink_bbox(image);margin=float(spec.get('pixels',1));ok=actual is not None and actual[0]>=margin and actual[1]>=margin and image.width-actual[2]>=margin and image.height-actual[3]>=margin
        elif kind=='rule_ink':
            fractions=[]
            for rule in (item for item in flat if item['type']=='Rule' and item['width']>0 and item['height']>0 and visible_color(item['color'])):
                # Use original local coordinates through the full affine matrix.
                local=rule['worldMatrix'];a,b,c,d,e,f=local
                # x/y were flattened above: retain the rectangle by local origin
                # reconstruction from its world top-left and linear components.
                wx,wy=rule['x'],rule['y'];pts=[(wx+a*x+c*y+origin[0],wy+b*x+d*y+origin[1]) for x in (0,rule['width']) for y in (0,rule['height'])]
                rect=(min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts))
                for clip in rule['worldClips']:rect=(max(rect[0],clip[0]+origin[0]),max(rect[1],clip[1]+origin[1]),min(rect[2],clip[2]+origin[0]),min(rect[3],clip[3]+origin[1]))
                pixels=crop_pixels(image,rect)
                if pixels:fractions.append(sum(min(p)<245 for p in pixels)/len(pixels))
            actual=fractions;ok=bool(fractions) and all(value>=float(spec.get('minimumFraction',.2)) for value in fractions)
        elif kind in ('sample_color','image_color'):
            target=spec.get('rgb',spec.get('color'))
            if not isinstance(target,(list,tuple)) or len(target)!=3:raise ToolError('Color check requires RGB triple')
            if kind=='sample_color':x,y=float(spec['x']),float(spec['y'])
            else:
                matches=[item for item in flat if item['type']=='ImageCommand' and (not spec.get('resource') or item['resource']['key']==spec['resource'])]
                if not matches:actual='image command missing';ok=False;x=y=None
                else:
                    item=matches[spec.get('occurrence',0)];a,b,c,d,e,f=item['worldMatrix'];rx=float(spec.get('relativeX',spec.get('x',.5)))*item['width'];ry=float(spec.get('relativeY',spec.get('y',.5)))*item['height']
                    x=item['x']+a*rx+c*ry+origin[0];y=item['y']+b*rx+d*ry+origin[1]
            if x is not None:
                if not 0<=round(x)<image.width or not 0<=round(y)<image.height:actual='sample outside image';ok=False
                else:actual=image.getpixel((round(x),round(y)));ok=max(abs(a-b) for a,b in zip(actual,target))<=float(spec.get('tolerance',30))
        else:raise ToolError('Unknown pixel check '+str(kind))
        results.append({'type':kind,'status':'PASS' if ok else 'FAIL','actual':actual,'expected':spec})
        if not ok:errors.append('pixels '+str(kind)+' failed')
    return errors,results


def required_characters(case,oracle,flat):
    actual=Counter(normalize_text(''.join(item['text'] for item in flat if item['type']=='Glyph')))
    # Each independent list is a requirement, not a sum of duplicated fixture
    # and DOM descriptions. PMB may legitimately paint a source letter twice.
    demands=[]
    if oracle.get('status')=='PASS':demands.append(('oracleVisibleText',oracle.get('visibleText','')))
    if case.get('requiredGlyphs') is not None:demands.append(('requiredGlyphs',case['requiredGlyphs']))
    if case.get('glyphs') is not None:demands.append(('legacyGlyphs',case['glyphs']))
    errors=[];results=[]
    for label,text in demands:
        expected=Counter(normalize_text(text));missing={char:count-actual[char] for char,count in expected.items() if actual[char]<count}
        results.append({'check':label,'status':'FAIL' if missing else 'PASS','missing':missing,'expected':dict(expected),'actual':dict(actual)})
        if missing:errors.append(label+' missing native characters '+repr(missing))
    return errors,results

def legacy_scene(box,flat,origin,padding):
    # The old checker assumes baseline padding+height. Shift the pure receipt,
    # not the image, so its actual-rule pixel sampling remains valid with visible
    # overflow. Original logical dimensions and recursive box.json are retained.
    adjusted=[]
    for value in flat:
        item=dict(value)
        if item['type']=='Rule':
            a,b,c,d,e,f=item['worldMatrix'];wx,wy=item['x'],item['y'];points=[(wx+a*x+c*y,wy+b*x+d*y) for x in (0,item['width']) for y in (0,item['height'])]
            item['x']=min(x for x,y in points);item['y']=min(y for x,y in points);item['width']=max(x for x,y in points)-item['x'];item['height']=max(y for x,y in points)-item['y']
        if 'x' in item:item['x']+=origin[0]-padding;item['y']+=origin[1]-padding-box.height
        adjusted.append(item)
    return {'width':box.width,'height':box.height,'depth':box.depth,'commands':adjusted}

def native_origin(box):
    from py_katex.canvas import ink_bounds
    ink=ink_bounds(box);left=0.;top=-box.height;right=box.width;bottom=box.depth
    if ink is not None:left=min(left,ink[0]);top=min(top,ink[1]);right=max(right,ink[2]);bottom=max(bottom,ink[3])
    return (left,top,right,bottom)

def glyph_pixel_checks(image,flat,origin):
    """Independent actual glyph ROI guards against valid metadata/no painting.

    Native public outline bounds localize glyphs; pixels still come only from
    the encoded output. This is not an alternative renderer or a golden image.
    """
    from py_skia_canvas import Canvas
    errors=[];tested=0;missing=[];metric_queries=0;canvas=Canvas(1,1);canvas.gpu=False;ctx=canvas.getContext('2d')
    for glyph in _glyphs(flat):
        if not glyph['text'].strip() or not visible_color(glyph['color']):continue
        resource=glyph.get('font_resource');key=glyph['font'];parts=key.split('|')
        if key.startswith(('system:','external:')):family=parts[0].split(':',1)[1]
        else:family='PyKaTeX_'+key
        style=glyph.get('font_style') or (resource['style'] if resource else parts[1] if key.startswith('system:') and len(parts)>1 else 'italic' if 'Italic' in key else 'normal')
        weight=glyph.get('font_weight') or (resource['weight'] if resource else parts[2] if key.startswith('system:') and len(parts)>2 else '700' if 'Bold' in key else '400')
        weight={'normal':'400','bold':'700'}.get(str(weight),str(weight))
        shear=0.
        if not key.startswith(('system:','external:')):
            # Localization uses an explicitly selected physical file, never a
            # native family matcher. Independent test_full_canvas pixel
            # controls (physical Italic / upright Bold / missing bold) validate
            # format; this ROI only checks the output really contains ink.
            from py_skia_canvas import FontLibrary
            directory=ROOT/'src/py_katex/data/fonts'
            candidates=[p.stem.removeprefix('KaTeX_') for p in directory.glob('KaTeX_'+key.split('-',1)[0]+'-*.ttf')]
            face=min(candidates,key=lambda name:(name.endswith(('Italic','BoldItalic'))!=(style!='normal'),abs((700 if name.endswith(('Bold','BoldItalic')) else 400)-int(weight)),name))
            family='IndependentVisualROI_'+face;FontLibrary.use(family,str(directory/('KaTeX_'+face+'.ttf')))
            physical_style='italic' if face.endswith(('Italic','BoldItalic')) else 'normal'
            shear=-.25 if style!='normal' and physical_style=='normal' else 0.
            style=physical_style;weight='700' if face.endswith(('Bold','BoldItalic')) else '400'
        ctx.font=f'{style} {weight} {glyph["size"]:g}px "{family}"';ctx.textAlign='left';ctx.textBaseline='alphabetic';ctx.direction='ltr';ctx.textWrap=False
        path=ctx.outlineText(glyph['text'])
        a,b,c,d,e,f=glyph['worldMatrix'];sx=glyph.get('scale_x',1);matrix=(a*sx,b*sx,c+a*sx*shear,d+b*sx*shear,glyph['x']+origin[0],glyph['y']+origin[1])
        if path.d:
            bounds=path.transform(*matrix).bounds;rect=tuple(bounds[k] for k in ('left','top','right','bottom'))
        else:
            # Color fonts may have no path but do paint real pixels. Query the
            # native actual bounds; the encoded PNG must still contain ink in
            # that rectangle. A correct trace plus a white image cannot pass.
            metric=ctx.measureText(glyph['text']);metric_queries+=1
            local=(-metric.actualBoundingBoxLeft,-metric.actualBoundingBoxAscent,metric.actualBoundingBoxRight+metric.actualBoundingBoxLeft,metric.actualBoundingBoxAscent+metric.actualBoundingBoxDescent)
            if not all(math.isfinite(value) for value in local):raise ToolError('Nonfinite color glyph metrics')
            rect=transform_rect(matrix,local)
        for clip in glyph['worldClips']:
            rect=(max(rect[0],clip[0]+origin[0]),max(rect[1],clip[1]+origin[1]),min(rect[2],clip[2]+origin[0]),min(rect[3],clip[3]+origin[1]))
        if rect[2]<=rect[0] or rect[3]<=rect[1]:continue
        # Wholly white text is allowed on the report's white background. Color
        # validity/readability is a source/theme contract, not fabricated ink.
        color=str(glyph['color']).lower().replace(' ','')
        if color in {'white','#fff','#ffffff','rgb(255,255,255)','rgba(255,255,255,1)'}:continue
        pixels=crop_pixels(image,(rect[0]-1,rect[1]-1,rect[2]+1,rect[3]+1));tested+=1
        if not pixels or not any(min(p)<255 for p in pixels):missing.append({'text':glyph['text'],'rect':rect})
    if missing:errors.append('actual glyph pixels missing in '+str(len(missing))+' native ROIs')
    return errors,{'tested':tested,'metricQueries':metric_queries,'missing':missing}


def image_decode_checks(box):
    from py_skia_canvas import Image
    values=[];seen=set()
    def walk(commands):
        for command in commands:
            kind=type(command).__name__
            if kind=='CommandGroup':yield from walk(command.commands)
            elif kind=='ImageCommand':yield command.resource
    for resource in walk(box.commands):
        sha=digest(resource.data)
        if (resource.key,sha) in seen:continue
        seen.add((resource.key,sha));native=Image(resource.data)
        if native.width<=0 or native.height<=0:raise ToolError('Native image decoder returned no actual dimensions')
        values.append({'key':resource.key,'sha256':sha,'encodedBytes':len(resource.data),'mime':resource.mime,'actualNativeWidth':native.width,'actualNativeHeight':native.height})
    return values


def path_pixel_checks(image,flat,origin):
    from py_skia_canvas import Canvas,Path2D
    canvas=Canvas(1,1);canvas.gpu=False;ctx=canvas.getContext('2d');tested=[];missing=[]
    for item in (value for value in flat if value['type']=='Path' and visible_color(value['color'])):
        color=str(item['color']).lower().replace(' ','')
        if color in {'white','#fff','#ffffff','rgb(255,255,255)','rgba(255,255,255,1)'}:continue
        a,b,c,d,e,f=item['worldMatrix'];sx=item['scale_x'];sy=item['scale_y'];matrix=(a*sx,b*sx,c*sy,d*sy,item['x'],item['y'])
        path=Path2D(item['d']).transform(*matrix)
        if not path.d:continue
        bounds=path.bounds;rect=tuple(bounds[key] for key in ('left','top','right','bottom'));stroke=item['stroke_width']*max(math.hypot(a*sx,b*sx),math.hypot(c*sy,d*sy))
        if stroke:rect=(rect[0]-stroke/2,rect[1]-stroke/2,rect[2]+stroke/2,rect[3]+stroke/2)
        clips=list(item['worldClips'])
        if item.get('clip') is not None:clips.append(transform_rect(matrix,item['clip']))
        for clip in clips:rect=(max(rect[0],clip[0]),max(rect[1],clip[1]),min(rect[2],clip[2]),min(rect[3],clip[3]))
        if rect[2]<=rect[0] or rect[3]<=rect[1]:continue
        ctx.lineWidth=stroke or 1;points=[]
        for iy in range(17):
            for ix in range(17):
                x=rect[0]+(ix+.5)*(rect[2]-rect[0])/17;y=rect[1]+(iy+.5)*(rect[3]-rect[1])/17
                if (ctx.isPointInStroke(path,x,y) if stroke else path.contains(x,y)):points.append((x,y))
        if not points:tested.append({'samples':0,'status':'NO_INTERIOR_GRID_POINTS','rect':rect});continue
        hits=0
        for x,y in points:
            values=crop_pixels(image,(x+origin[0]-1,y+origin[1]-1,x+origin[0]+2,y+origin[1]+2))
            if any(min(pixel)<255 for pixel in values):hits+=1
        record={'samples':len(points),'inkHits':hits,'rect':rect};tested.append(record)
        if hits==0:missing.append(record)
    return (['Native path actual pixels absent in '+str(len(missing))+' sampled paths'] if missing else []),{'paths':tested,'missing':missing}
