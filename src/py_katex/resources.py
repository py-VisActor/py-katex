"""Explicit offline mathematical images. No URL fetching or implicit file access.

Descriptor construction/header inspection is pure; actual decoding remains on
Canvas owner thread. Paths are read only by the explicitly called path factory.
"""
from __future__ import annotations
import base64,math,re,struct
from pathlib import Path
from urllib.parse import unquote_to_bytes
import xml.etree.ElementTree as ET
from .model import ImageResource,ResourceBundle,ParseError
MAX_BYTES=32*1024*1024
MAX_BUNDLE_BYTES=128*1024*1024
MAX_PIXELS=64_000_000

def fail(message,code='INVALID_RESOURCE'):raise ParseError(message,code=code)

def validate_svg(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():fail('SVG entities/DOCTYPE forbidden','UNSAFE_RESOURCE')
    try:root=ET.fromstring(data)
    except ET.ParseError as exc:raise ParseError('Invalid SVG resource',code='INVALID_RESOURCE') from exc
    if root.tag.rsplit('}',1)[-1].lower()!='svg':fail('SVG root required')
    for element in root.iter():
        tag=element.tag.rsplit('}',1)[-1].lower()
        if tag in {'script','foreignobject','iframe','object','embed','animate','animatetransform','animatemotion','set'}:fail('Executable or animated SVG forbidden','UNSAFE_RESOURCE')
        for name,value in element.attrib.items():
            key=name.rsplit('}',1)[-1].lower()
            if key.startswith('on'):fail('SVG event callback forbidden','UNSAFE_RESOURCE')
            if key in {'href','src'} and value and not value.startswith('#'):
                if not re.match(r'^data:image/(?:png|jpeg|webp|gif);base64,',value,re.I):fail('SVG image must be self-contained','UNSAFE_RESOURCE')
                image_from_data_uri(value)
            if re.search(r'@import|(?:https?|file|javascript):',value,re.I) and not key.startswith('xmlns'):fail('External SVG reference','UNSAFE_RESOURCE')
            if any(not url.strip(' \"\'').startswith('#') for url in re.findall(r'url\s*\((.*?)\)',value,re.I)):fail('Non-local SVG url()','UNSAFE_RESOURCE')
        if tag=='style' and element.text:
            if re.search(r'@import',element.text,re.I) or any(not url.strip(' \"\'').startswith('#') for url in re.findall(r'url\s*\((.*?)\)',element.text,re.I)):fail('External SVG CSS','UNSAFE_RESOURCE')
    return root

def dimensions(data,mime):
    if mime=='image/png':
        if data[:8]!=b'\x89PNG\r\n\x1a\n' or len(data)<24:fail('Invalid PNG header')
        return struct.unpack('>II',data[16:24])
    if mime in {'image/jpeg','image/jpg'}:
        if not data.startswith(b'\xff\xd8'):fail('Invalid JPEG header')
        i=2
        while i+3<len(data):
            if data[i]!=255:i+=1;continue
            while i<len(data) and data[i]==255:i+=1
            if i>=len(data):break
            marker=data[i];i+=1
            if marker in {0x01,0xd8,0xd9} or 0xd0<=marker<=0xd7:continue
            if i+2>len(data):break
            length=int.from_bytes(data[i:i+2],'big')
            if length<2 or i+length>len(data):break
            if marker in {0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf}:
                if length<7:break
                return int.from_bytes(data[i+5:i+7],'big'),int.from_bytes(data[i+3:i+5],'big')
            i+=length
        fail('JPEG dimensions unavailable')
    if mime=='image/webp':
        if len(data)<30 or data[:4]!=b'RIFF' or data[8:12]!=b'WEBP':fail('Invalid WebP header')
        if data[12:16]==b'VP8X':return 1+int.from_bytes(data[24:27],'little'),1+int.from_bytes(data[27:30],'little')
        if data[12:16]==b'VP8L' and data[20]==0x2f:
            value=int.from_bytes(data[21:25],'little');return (value&0x3fff)+1,((value>>14)&0x3fff)+1
        if data[12:16]==b'VP8 ' and data[23:26]==b'\x9d\x01\x2a':return int.from_bytes(data[26:28],'little')&0x3fff,int.from_bytes(data[28:30],'little')&0x3fff
        fail('Unsupported WebP dimensions')
    if mime=='image/gif':
        if data[:6] not in {b'GIF87a',b'GIF89a'} or len(data)<10:fail('Invalid GIF header')
        # Native decoder's first static frame; no animation lifecycle is created.
        return struct.unpack('<HH',data[6:10])
    if mime=='image/svg+xml':
        root=validate_svg(data)
        def size(value):
            m=re.fullmatch(r'\s*([\d.]+)(px|pt|pc|in|cm|mm)?\s*',value or '')
            if not m:return None
            return float(m[1])*{'px':1,'pt':96/72,'pc':16,'in':96,'cm':96/2.54,'mm':96/25.4,None:1}[m[2]]
        width=size(root.get('width'));height=size(root.get('height'))
        view=re.split(r'[ ,]+',(root.get('viewBox') or '').strip())
        if len(view)==4:
            try:vw,vh=float(view[2]),float(view[3])
            except ValueError:fail('Invalid SVG viewBox')
            if vw<=0 or vh<=0:fail('Invalid SVG viewBox')
            if width is None:width=height*vw/vh if height is not None else vw
            if height is None:height=width*vh/vw
        return (width or 300,height or 150) # SVG replaced-element default viewport
    fail('Unsupported offline image MIME: '+mime,'UNSUPPORTED_IMAGE_FORMAT')

def sniff(data):
    if data.startswith(b'\x89PNG'):return 'image/png'
    if data.startswith(b'\xff\xd8'):return 'image/jpeg'
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP':return 'image/webp'
    if data.startswith((b'GIF87a',b'GIF89a')):return 'image/gif'
    if data.lstrip(b'\xef\xbb\xbf \n\r\t').startswith(b'<'):return 'image/svg+xml'
    fail('Unknown offline image encoding','UNSUPPORTED_IMAGE_FORMAT')

def image_from_bytes(key,data,mime=None):
    if not isinstance(key,str) or not key:fail('Resource key must be nonempty')
    if not isinstance(data,bytes) or not data or len(data)>MAX_BYTES:fail('Image byte budget exceeded','RESOURCE_BUDGET')
    actual=sniff(data);mime=mime or actual
    if mime=='image/jpg':mime='image/jpeg'
    if mime!=actual:fail('Image MIME disagrees with encoded bytes')
    w,h=dimensions(data,mime)
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (w,h)) or w*h>MAX_PIXELS or max(w,h)>32768:fail('Image dimension budget exceeded','RESOURCE_BUDGET')
    return ImageResource(key,data,mime,float(w),float(h))

def image_from_path(key,path,mime=None):
    # Only this explicit API reads caller-authorized local files.
    path=Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_size>MAX_BYTES:fail('Image file budget exceeded','RESOURCE_BUDGET')
    return image_from_bytes(key,path.read_bytes(),mime)

def image_from_data_uri(uri,key=None):
    if not isinstance(uri,str) or len(uri)>MAX_BYTES*4//3+4096:fail('Image data URI budget exceeded','RESOURCE_BUDGET')
    match=re.fullmatch(r'data:(image/[\w.+-]+)(;base64)?,(.*)',uri,re.S|re.I)
    if not match:fail('Expected explicit image data URI')
    try:data=base64.b64decode(match[3],validate=True) if match[2] else unquote_to_bytes(match[3])
    except (ValueError,TypeError) as exc:raise ParseError('Invalid image data URI',code='INVALID_RESOURCE') from exc
    return image_from_bytes(key or uri,data,match[1].lower())

def validate_bundle(bundle):
    if bundle is None:return ResourceBundle()
    if not isinstance(bundle,ResourceBundle):fail('resources must be ResourceBundle')
    seen=set();total=0
    for image in bundle.images:
        if not isinstance(image,ImageResource) or image.key in seen:fail('Duplicate or invalid image descriptor')
        actual=image_from_bytes(image.key,image.data,image.mime)
        if (actual.width,actual.height)!=(image.width,image.height):fail('Image descriptor dimensions disagree with encoded header')
        seen.add(image.key);total+=len(image.data)
    if total>MAX_BUNDLE_BYTES:fail('Resource bundle budget exceeded','RESOURCE_BUDGET')
    return bundle

def resolve_image(key,bundle=None):
    bundle=validate_bundle(bundle)
    found=next((image for image in bundle.images if image.key==key),None)
    if found:return found
    if key.startswith('data:'):return image_from_data_uri(key)
    fail('Explicit offline image not found: '+key,'RESOURCE_NOT_FOUND')

__all__=['ImageResource','ResourceBundle','image_from_bytes','image_from_path','image_from_data_uri','validate_bundle','resolve_image']

# Public factory names exposed lazily by py_katex.
def image_resource(key,data,mime=None):return image_from_bytes(key,data,mime)
def image_resource_from_file(key,path,mime=None):return image_from_path(key,path,mime)


def font_covers(data,text):
    """Read only the standard sfnt Unicode cmap; no shaping replacement."""
    try:
        start=0
        if data[:4]==b'ttcf':start=int.from_bytes(data[12:16],'big')
        count=int.from_bytes(data[start+4:start+6],'big');offset=None
        for i in range(count):
            pos=start+12+i*16
            if data[pos:pos+4]==b'cmap':offset=int.from_bytes(data[pos+8:pos+12],'big');break
        if offset is None:return False
        entries=int.from_bytes(data[offset+2:offset+4],'big');tables=[]
        for i in range(entries):
            pos=offset+4+i*8;platform=int.from_bytes(data[pos:pos+2],'big');encoding=int.from_bytes(data[pos+2:pos+4],'big')
            if platform==0 or platform==3 and encoding in (1,10):tables.append(offset+int.from_bytes(data[pos+4:pos+8],'big'))
        def covered(cp):
            for pos in tables:
                fmt=int.from_bytes(data[pos:pos+2],'big')
                if fmt==12:
                    n=int.from_bytes(data[pos+12:pos+16],'big')
                    if n>1_000_000:return False
                    for i in range(n):
                        off=pos+16+i*12;lo,hi,gid=struct.unpack('>III',data[off:off+12])
                        if lo<=cp<=hi and gid+cp-lo:return True
                elif fmt==4 and cp<=0xffff:
                    seg=int.from_bytes(data[pos+6:pos+8],'big')//2;ends=pos+14;starts=ends+2*seg+2;deltas=starts+2*seg;ranges=deltas+2*seg
                    for i in range(seg):
                        hi=int.from_bytes(data[ends+2*i:ends+2*i+2],'big');lo=int.from_bytes(data[starts+2*i:starts+2*i+2],'big')
                        if lo<=cp<=hi:
                            delta=int.from_bytes(data[deltas+2*i:deltas+2*i+2],'big');ro=int.from_bytes(data[ranges+2*i:ranges+2*i+2],'big')
                            if not ro:gid=(cp+delta)&65535
                            else:
                                off=ranges+2*i+ro+2*(cp-lo);gid=int.from_bytes(data[off:off+2],'big');gid=(gid+delta)&65535 if gid else 0
                            if gid:return True
            return False
        return all(ch.isspace() or ord(ch) in {0x200c,0x200d,0xfe0f} or covered(ord(ch)) for ch in text)
    except (ValueError,IndexError,struct.error):return False


def validate_font_resources(fonts):
    """Reject invalid explicit sfnt payloads/budgets before coverage selection."""
    total=0
    for font in fonts:
        data=font.data
        if not isinstance(data,bytes) or not data or len(data)>MAX_BYTES:fail('Explicit fallback font byte budget exceeded','RESOURCE_BUDGET')
        total+=len(data)
        if data[:4] not in {b'\0\1\0\0',b'OTTO',b'true',b'ttcf'}:fail('Explicit fallback font is not a supported sfnt font','INVALID_RESOURCE')
        start=int.from_bytes(data[12:16],'big') if data[:4]==b'ttcf' else 0
        if start+12>len(data):fail('Truncated explicit font header')
        count=int.from_bytes(data[start+4:start+6],'big')
        if not 0<count<=4096 or start+12+count*16>len(data):fail('Invalid explicit font table directory')
        tags=set()
        for index in range(count):
            off=start+12+index*16;tag=data[off:off+4];pos=int.from_bytes(data[off+8:off+12],'big');length=int.from_bytes(data[off+12:off+16],'big')
            if pos+length>len(data):fail('Explicit font table extends beyond payload')
            tags.add(tag)
        if b'cmap' not in tags:fail('Explicit font has no Unicode cmap')
    if total>MAX_BUNDLE_BYTES:fail('Explicit fallback font bundle byte budget exceeded','RESOURCE_BUDGET')
