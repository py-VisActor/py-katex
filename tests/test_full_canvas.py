"""MATH-FULL Canvas acceptance designed from fixed sources, never candidate goldens.

Only test execution creates fixture encodings/native objects. Pillow constructs
hand-authored test assets and decodes outputs; production uses public Canvas.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path as FilePath
import json,math,re,struct,tempfile,unittest,zlib,warnings
import xml.etree.ElementTree as ET
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageChops
from py_skia_canvas import Canvas,FontLibrary
from py_katex import typeset,parse,render,Options,FontResource,ResourceBundle
from py_katex.model import MathBox,Glyph,Rule,Path,ImageCommand,CommandGroup,ParseError
from py_katex.canvas import render_box,draw,ink_bounds,measure_fallback
from py_katex.resources import image_resource,image_resource_from_file,image_from_data_uri,validate_bundle

ROOT=FilePath(__file__).resolve().parents[1]
QUAD='<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" viewBox="0 0 40 20"><path fill="red" d="M0 0H20V10H0Z"/><path fill="lime" d="M20 0H40V10H20Z"/><path fill="blue" d="M0 10H20V20H0Z"/><path fill="yellow" d="M20 10H40V20H20Z"/></svg>'

def raster(fmt='PNG',animated=False):
    # This fixture is independently authored geometry, not a product render.
    im=Image.new('RGB',(40,20),'red');d=ImageDraw.Draw(im)
    if not animated:
        d.rectangle((20,0,39,9),fill='lime');d.rectangle((0,10,19,19),fill='blue');d.rectangle((20,10,39,19),fill='yellow')
    out=BytesIO();kwargs={'quality':100,'subsampling':0} if fmt=='JPEG' else {}
    if animated:kwargs.update(save_all=True,append_images=[Image.new('RGB',(40,20),'blue')],duration=100,loop=0)
    im.save(out,format=fmt,**kwargs);return out.getvalue()

def img(result):
    im=Image.open(BytesIO(result.data));im.load();rgba=im.convert('RGBA');white=Image.new('RGBA',rgba.size,'white');white.alpha_composite(rgba);return white.convert('RGB')

def dark_count(im):return sum(max(p)<160 for p in im.getdata())

def ink_bbox(im):
    mask=im.convert('L').point(lambda p:255 if p<190 else 0);return mask.getbbox()

def assert_quad(im,left=8,top=8,width=40,height=20,tolerance=30):
    for x,y,color in ((.25,.25,(255,0,0)),(.75,.25,(0,255,0)),(.25,.75,(0,0,255)),(.75,.75,(255,255,0))):
        actual=im.getpixel((round(left+x*width),round(top+y*height)))
        assert max(abs(a-b) for a,b in zip(actual,color))<=tolerance,(actual,color)

def commands(box):
    def walk(items):
        for item in items:
            if isinstance(item,CommandGroup):yield from walk(item.commands)
            else:yield item
    return tuple(walk(box.commands))

def reference_glyph(text,key,size=48,style=None,weight=None):
    # Independent physical-font reference: never registers sibling faces or
    # invokes the same family matcher that previously selected upright Bold.
    alias='IndependentPhysicalFull_'+key
    FontLibrary.use(alias,str(ROOT/'src/py_katex/data/fonts'/('KaTeX_'+key+'.ttf')))
    style=style or ('italic' if 'Italic' in key else 'normal');weight=weight or ('700' if 'Bold' in key else '400')
    intrinsic_style='italic' if 'Italic' in key else 'normal';intrinsic_weight='700' if 'Bold' in key else '400'
    c=Canvas(800,200);c.gpu=False;x=c.getContext('2d');x.fillStyle='white';x.fillRect(0,0,800,200);x.fillStyle='black';x.font=f'{intrinsic_style} {intrinsic_weight} {size}px "{alias}"';x.textBaseline='alphabetic'
    if weight=='700' and intrinsic_weight=='400':
        # Independent literal from upstream SkTextFormatParams.h; Canvas a18
        # ignores synthetic bold on a single italic face, so request the same
        # physical glyph contour plus source fake-bold stroke explicitly.
        x.strokeStyle='black';x.lineWidth=size*(1/32 if size>=36 else 1/24 if size<=9 else 1/24+(size-9)/27*(1/32-1/24));x.lineJoin='round';x.strokeText(text,30,100)
    x.fillText(text,30,100)
    return Image.open(BytesIO(c.toBufferSync('png'))).convert('RGB')

def shape_distance(a,b):
    aa=a.crop(ink_bbox(a)).convert('L');bb=b.crop(ink_bbox(b)).convert('L')
    # Normalize only raster origin/one-pixel phase, preserving glyph contours.
    bb=bb.resize(aa.size)
    return sum(ImageChops.difference(aa,bb).getdata())/(max(1,aa.width*aa.height)*255)

class FullResourceCanvasTests(unittest.TestCase):
    def test_real_png_jpeg_webp_svg_decoding_and_four_colors(self):
        for fmt,mime in [('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp'),('SVG','image/svg+xml')]:
            with self.subTest(format=fmt):
                data=QUAD.encode() if fmt=='SVG' else raster(fmt)
                resource=image_resource('quad',data,mime);self.assertEqual((resource.width,resource.height),(40,20))
                b=typeset(r'\includegraphics[height=1em]{quad}',options=Options(trust=True,resources=ResourceBundle((resource,))),font_size=20)
                self.assertAlmostEqual(b.width,40);self.assertAlmostEqual(b.height,20);self.assertEqual(b.depth,0)
                result=render_box(b,backend='cpu',background='white');assert_quad(img(result))
                bad=Image.new('RGB',(result.width,result.height),'white')
                with self.assertRaises(AssertionError):assert_quad(bad)

    def test_gif_uses_first_static_frame_not_later_blue_frame(self):
        resource=image_resource('anim',raster('GIF',True),'image/gif')
        box=MathBox(40,20,0,(ImageCommand(resource,0,-20,40,20),));im=img(render_box(box,backend='cpu',background='white'))
        self.assertEqual(im.getpixel((28,18)),(255,0,0));self.assertNotEqual(im.getpixel((28,18)),(0,0,255))

    def test_includegraphics_default_height_totalheight_depth_and_width(self):
        resource=image_resource('quad',QUAD.encode())
        opts=Options(trust=True,resources=ResourceBundle((resource,)))
        default=typeset(r'\includegraphics{quad}',options=opts,font_size=40)
        self.assertAlmostEqual(default.height,36);self.assertAlmostEqual(default.depth,0);self.assertAlmostEqual(default.width,72)
        b=typeset(r'\includegraphics[height=1em,totalheight=1.4em,width=2em,alt=Four colors]{quad}',options=opts,font_size=40)
        self.assertAlmostEqual(b.height,40);self.assertAlmostEqual(b.depth,16);self.assertAlmostEqual(b.width,80)
        assert_quad(img(render_box(b,backend='cpu',background='white')),width=80,height=56)
        tree=parse(r'\includegraphics[alt=Four colors]{quad}',trust=True)
        stack=[tree];found=[]
        while stack:
            n=stack.pop();stack.extend(n.children)
            if n.kind=='image':found.append(n)
        self.assertEqual(found[0].get('alt'),'Four colors')

    def test_includegraphics_unitless_bp_and_source_default_alt(self):
        resource=image_resource('folder/quad.png',QUAD.encode())
        box=typeset(r'\includegraphics[height=1,totalheight=1.5,width=2]{folder/quad.png}',font_size=40,trust=True,resources=ResourceBundle((resource,)))
        # includegraphics.sizeData defaults unitless measurements to bp;
        # source units.ts bp=803/800 pt, source ptPerEm=10.
        self.assertAlmostEqual(box.width,2*(803/800)*40/10)
        self.assertAlmostEqual(box.height,(803/800)*40/10)
        self.assertAlmostEqual(box.depth,.5*(803/800)*40/10)
        tree=parse(r'\includegraphics{folder/quad.png}',trust=True)
        stack=[tree]
        while stack:
            node=stack.pop();stack.extend(node.children)
            if node.kind=='image':self.assertEqual(node.get('alt'),'quad');break
        else:self.fail('source image AST missing')

    def test_datauri_percent_encoded_svg_and_base64_png_offline(self):
        import base64
        from urllib.parse import quote
        for datauri in ('data:image/svg+xml,'+quote(QUAD),'data:image/png;base64,'+base64.b64encode(raster()).decode()):
            resource=image_from_data_uri(datauri);self.assertEqual((resource.width,resource.height),(40,20))
            box=typeset(r'\includegraphics[height=1em]{'+datauri+'}',options=Options(trust=True),font_size=20)
            assert_quad(img(render_box(box,backend='cpu',background='white')))

    def test_explicit_file_factory_does_not_implicit_fetch_formula_url(self):
        with tempfile.TemporaryDirectory() as folder:
            p=FilePath(folder)/'quad.svg';p.write_text(QUAD,encoding='utf8');resource=image_resource_from_file('offline',p)
            self.assertEqual(resource.data,QUAD.encode())
        for url in ('https://example.com/a.png','file:///C:/secret.png','../secret.png'):
            with self.subTest(url=url),patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')),self.assertRaises(ParseError) as caught:
                typeset(r'\includegraphics{'+url+'}',options=Options(trust=True))
            self.assertEqual(caught.exception.code,'RESOURCE_NOT_FOUND')

    def test_svg_scripts_events_external_css_entities_and_foreignobject_rejected(self):
        bodies=['<script>alert(1)</script>','<rect onload="x()"/>','<image href="https://example.com/a.png"/>','<use href="file:///x"/>','<style>@import "https://example.com/x.css";</style>','<foreignObject/>','<animate attributeName="x"/>']
        for body in bodies:
            with self.subTest(body=body),self.assertRaises(ParseError):image_resource('unsafe',('<svg xmlns="http://www.w3.org/2000/svg">'+body+'</svg>').encode())
        with self.assertRaises(ParseError):image_resource('entity',b'<!DOCTYPE svg [<!ENTITY x "x">]><svg/>')

    def test_resource_budgets_mime_and_descriptor_mismatch(self):
        valid=image_resource('quad',QUAD.encode())
        for data,mime in ((b'','image/png'),(QUAD.encode(),'image/png'),(b'x'*(32*1024*1024+1),None)):
            with self.subTest(mime=mime),self.assertRaises((ParseError,ValueError)):image_resource('bad',data,mime)
        with self.assertRaises(ParseError):validate_bundle(ResourceBundle((replace(valid,width=41),)))
        with self.assertRaises(ValueError):ResourceBundle((valid,valid))
        giant=b'\x89PNG\r\n\x1a\n'+b'\0'*8+struct.pack('>II',40000,40000)
        with self.assertRaises(ParseError):image_resource('giant',giant)
        # Independently sized images exercise total budget without mocking limits.
        padded=QUAD.encode()+b' '*(27*1024*1024)
        resources=tuple(image_resource('q'+str(i),padded) for i in range(5))
        with self.assertRaises(ParseError) as caught:validate_bundle(ResourceBundle(resources))
        self.assertEqual(caught.exception.code,'RESOURCE_BUDGET')

    def test_trustfalse_renders_visible_rejection_with_diagnostic(self):
        b=typeset(r'\includegraphics{https://example.com/x.png}',options=Options(trust=False))
        self.assertTrue(b.diagnostics);self.assertFalse(any(isinstance(c,ImageCommand) for c in commands(b)))
        im=img(render_box(b,backend='cpu',background='white'))
        self.assertGreater(sum(p[0]>120 and p[1]<110 and p[2]<110 for p in im.getdata()),8)

    def test_source_unicode_script_families_have_real_shaped_ink(self):
        samples=('\u011b\u0161\u010d','\u0411\u0413\u0414','\u0531\u0532','\u0928\u092e\u0938\u094d\u0924\u0947','\u10d2\u10d0\u10db','\u79c1\u306f\u30d0\u30ca\u30ca','\uc5ec\ubcf4\uc138\uc694')
        for text in samples:
            with self.subTest(script=text):
                b=typeset(r'\text{'+text+'}',font_size=32,strict='ignore');im=img(render_box(b,backend='cpu',background='white'))
                self.assertGreater(dark_count(im),10);self.assertTrue(any(isinstance(c,Glyph) for c in commands(b)))

    def test_explicit_font_resource_real_coverage_and_owner_transfer(self):
        path=FilePath('C:/Windows/Fonts/arial.ttf');self.assertTrue(path.is_file(),'declared test fixture Arial must exist')
        data=path.read_bytes();fixture=json.loads((ROOT/'tests/full-resource-cases.json').read_text(encoding='utf8'))
        self.assertEqual(sha256(data).hexdigest(),fixture['fonts'][0]['sha256'])
        resource=FontResource('ExplicitArial',data,scripts=('cyrillic',))
        text='\u0411\u0413\u0414'
        b=typeset(r'\text{'+text+'}',font_size=36,fallback_fonts=(resource,),strict='ignore')
        self.assertTrue(any(c.font_resource is not None for c in commands(b) if isinstance(c,Glyph)))
        a=render_box(b,backend='cpu',background='white')
        with ThreadPoolExecutor(max_workers=1) as pool:other=pool.submit(lambda:render_box(b,backend='cpu',background='white')).result()
        self.assertEqual(img(a).tobytes(),img(other).tobytes());self.assertGreater(dark_count(img(a)),10)

    def test_platform_peace_sign_colour_glyph_is_real_and_not_missing_control(self):
        text=chr(0x270c)
        for tex in (text,r'\text{'+text+'}',r'\smash{\text{'+chr(0x0411)+text+chr(0x0413)+'}}'):
            with self.subTest(tex=tex),warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                box=typeset(tex,font_size=48,strict='warn')
                self.assertTrue(any('unknownSymbol' in str(item.message) for item in caught))
                self.assertTrue(any('symbolNotInFont' in str(item.message) for item in caught))
                self.assertIsNotNone(ink_bounds(box))
                result=render_box(box,backend='cpu',background='white');actual=img(result)
                mask=Image.new('L',actual.size);mask.putdata([255 if min(pixel)<250 else 0 for pixel in actual.getdata()]);bounds=mask.getbbox()
                self.assertIsNotNone(bounds);self.assertGreater(sum(min(pixel)<200 for pixel in actual.getdata()),25)
                self.assertGreaterEqual(bounds[0],7);self.assertGreaterEqual(bounds[1],7)
                self.assertLessEqual(bounds[2],actual.width-7);self.assertLessEqual(bounds[3],actual.height-7)
        # Public installed-family path is valid too; it must not need a file
        # read selected by TeX, and a named colour-font empty outline must not
        # prevent real pixel painting or physical ink-bound discovery.
        for family in ('Segoe UI Symbol','Segoe UI Emoji'):
            self.assertTrue(FontLibrary.has(family),'declared Windows platform fixture missing')
            box=MathBox(100,70,20,(Glyph(text,0,0,'system:'+family+'|normal|400',48),))
            self.assertIsNotNone(ink_bounds(box));self.assertGreater(sum(min(pixel)<200 for pixel in img(render_box(box,backend='cpu',background='white')).getdata()),25)
        # Real native direct rendering proves the hand and the selected font's
        # missing control have different pixels, independently of our coverage
        # helper, production glyph trace, or a non-empty encoded PNG header.
        reference=[]
        for value in (text,chr(0x10ffff)):
            canvas=Canvas(160,140);canvas.gpu=False;ctx=canvas.getContext('2d')
            ctx.fillStyle='white';ctx.fillRect(0,0,160,140);ctx.font='normal 400 48px serif';ctx.fillStyle='black';ctx.textBaseline='alphabetic';ctx.fillText(value,20,100)
            reference.append(Image.open(BytesIO(canvas.toBufferSync('png'))).convert('RGB'))
        self.assertGreater(sum(ImageChops.difference(*reference).convert('L').getdata()),10000)
        with self.assertRaises(ParseError) as error:typeset(r'\text{'+chr(0x10ffff)+'}',strict='ignore')
        self.assertEqual(error.exception.code,'MISSING_GLYPH')

    def test_visual_tool_color_metric_roi_rejects_white_noop_image(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('color_visual_support',ROOT/'tools/full_visual_support.py')
        support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
        # Declared Windows color font really paints the hand without a path.
        # This is an independent native image, not a synthetic trace golden.
        self.assertTrue(FontLibrary.has('Segoe UI Emoji'))
        box=MathBox(100,80,20,(Glyph(chr(0x270c),0,0,'system:Segoe UI Emoji|normal|400',48),))
        result=render_box(box,backend='cpu',background='white');scene=support.flatten_commands(box)
        errors,details=support.glyph_pixel_checks(img(result),scene,(8,88))
        self.assertEqual(errors,[]);self.assertGreater(details['tested'],0);self.assertGreater(details['metricQueries'],0)
        errors,details=support.glyph_pixel_checks(Image.new('RGB',(result.width,result.height),'white'),scene,(8,88))
        self.assertTrue(errors);self.assertTrue(details['missing'])

    def test_unknown_unicode_missing_glyph_is_not_successful_tofu(self):
        with self.assertRaises(ParseError) as caught:typeset(r'\text{'+chr(0x10ffff)+'}',font_size=32,strict='ignore')
        self.assertEqual(caught.exception.code,'MISSING_GLYPH')
        with patch('py_katex.canvas.measure_fallback',side_effect=AssertionError('bundled metrics must remain bundled')):
            b=typeset(r'\frac{x^2+1}{y}',font_size=32)
        self.assertTrue(all(c.font_resource is None for c in commands(b) if isinstance(c,Glyph)))

    def test_text_runs_preserve_source_ligature_kerning_and_brahmic_shaping(self):
        b=typeset(r'\text{office AV}',font_size=40)
        glyphs=[c for c in commands(b) if isinstance(c,Glyph)]
        self.assertTrue(any(len(c.text)>1 for c in glyphs),'source tryCombineChars should preserve native shaping run')
        expected=reference_glyph('office AV','Main-Regular',40)
        actual=img(render_box(b,backend='cpu',background='white'));self.assertLess(shape_distance(actual,expected),.08)
        text='\u0928\u092e\u0938\u094d\u0924\u0947'
        native=typeset(r'\text{'+text+'}',font_size=36,strict='ignore')
        self.assertTrue(any(text in c.text for c in commands(native) if isinstance(c,Glyph)))

    def test_invalid_explicit_font_and_font_byte_budget_are_not_ignored(self):
        for data in (b'not-a-font',b'x'*(32*1024*1024+1)):
            options=Options(fallback_fonts=(FontResource('BadExplicit',data),),strict='ignore')
            with self.subTest(bytes=len(data)),self.assertRaises((ParseError,ValueError,RuntimeError)):
                typeset(r'\text{'+chr(0x0411)+'}',options=options)

    def test_nested_command_depth_count_and_bad_group_parameters_rejected(self):
        nested=(Rule(0,-10,10,10),)
        for _ in range(130):nested=(CommandGroup(nested),)
        for box in (MathBox(10,10,0,nested),MathBox(10,10,0,(Rule(0,-10,1,1),)*200001),MathBox(10,10,0,(CommandGroup((),opacity=2),)),MathBox(10,10,0,(CommandGroup((),matrix=(math.nan,0,0,1,0,0)),))):
            with self.subTest(commands=len(box.commands)),self.assertRaises(ParseError):render_box(box,backend='cpu')

    def test_html_font_axes_obey_generated_inner_classes_with_pixels(self):
        cases=[(r'\htmlStyle{font-family:KaTeX_SansSerif;font-style:normal;}{x}','x','Math-Italic','italic','400'),(r'\htmlStyle{font-weight:bold;}{x}','x','Math-BoldItalic','italic','700'),(r'\htmlStyle{font-style:italic;}{\mathbf{F}}','F','Main-BoldItalic','italic','700'),(r'\htmlStyle{font-family:KaTeX_SansSerif;font-style:italic;font-weight:bold;}{\mathrm{F}}','F','SansSerif-Bold','normal','700'),(r'\htmlStyle{font-weight:bold;}{\mathbb{A}}','A','AMS-Regular','normal','700'),(r'\htmlStyle{font-family:KaTeX_SansSerif;font-style:italic;font-weight:bold;}{1}','1','SansSerif-Italic','italic','700')]
        for tex,text,key,style,weight in cases:
            with self.subTest(tex=tex):
                b=typeset(tex,font_size=48,trust=True);actual=img(render_box(b,backend='cpu',background='white'))
                correct=reference_glyph(text,key,48,style,weight);wrong=reference_glyph(text,'Main-Regular',48,'normal','400')
                self.assertLess(shape_distance(actual,correct),.09)
                self.assertLess(shape_distance(actual,correct),shape_distance(actual,wrong))

    def test_synthetic_bold_retains_physical_italic_contour_and_added_ink(self):
        # Three disjoint physical references expose both previous defects:
        # wrong upright sibling, and correct italic face without bold paint.
        formula=r'\htmlStyle{font-family:KaTeX_SansSerif;font-style:italic;font-weight:bold;}{1}'
        actual=img(render_box(typeset(formula,font_size=96,trust=True),backend='cpu',background='white'))
        italic=reference_glyph('1','SansSerif-Italic',96,'italic','400')
        bolditalic=reference_glyph('1','SansSerif-Italic',96,'italic','700')
        upright=reference_glyph('1','SansSerif-Bold',96,'normal','700')
        self.assertLess(shape_distance(actual,bolditalic),.06)
        self.assertLess(shape_distance(actual,bolditalic),shape_distance(actual,upright)*.65)
        self.assertGreater(dark_count(actual),dark_count(italic)*1.12)
        self.assertGreater(shape_distance(actual,italic),.015)

    def test_svg_concrete_viewport_preserves_default_meet_alignment_and_none(self):
        for preserve,top,bottom in ((None,4,24),('xMidYMin meet',0,20),('xMaxYMax meet',8,28),('none',0,28)):
            with self.subTest(preserve=preserve):
                markup=QUAD if preserve is None else QUAD.replace('viewBox=',f'preserveAspectRatio="{preserve}" viewBox=')
                resource=image_resource('viewport',markup.encode())
                b=MathBox(40,20,8,(ImageCommand(resource,0,-20,40,28),))
                im=img(render_box(b,backend='cpu',background='white'))
                colored=[(x,y) for y in range(im.height) for x in range(im.width) if max(im.getpixel((x,y)))-min(im.getpixel((x,y)))>100]
                self.assertEqual((min(y for x,y in colored),max(y for x,y in colored)+1),(8+top,8+bottom))
                self.assertEqual((min(x for x,y in colored),max(x for x,y in colored)+1),(8,48))
                if preserve is None:
                    self.assertEqual(im.getpixel((20,9)),(255,255,255))
                    self.assertNotEqual(im.getpixel((20,13)),(255,255,255))
        # Raster CSS images really stretch: SVG letterboxing must not leak
        # into unrelated image formats with the same intrinsic aspect ratio.
        resource=image_resource('raster',raster())
        im=img(render_box(MathBox(40,20,8,(ImageCommand(resource,0,-20,40,28),)),backend='cpu',background='white'))
        self.assertNotEqual(im.getpixel((20,9)),(255,255,255))

    def test_htmlclass_inline_precedence_id_data_and_color_background(self):
        tex=r'\htmlId{stable-id}{\htmlData{a=b,c={,}}{\htmlClass{paint}{\htmlStyle{color:blue;background-color:#ffff00;padding:4px;}{x}}}}'
        b=typeset(tex,font_size=40,trust=True,html_styles=(('paint','color:red;'),))
        im=img(render_box(b,backend='cpu',background='white'))
        self.assertGreater(sum(p[2]>130 and p[0]<100 for p in im.getdata()),8);self.assertGreater(sum(p[0]>200 and p[1]>200 and p[2]<80 for p in im.getdata()),30)
        self.assertEqual(dark_count(img(render_box(replace(b,commands=()),backend='cpu',background='white'))),0)

    def test_html_visible_style_properties_native_background_border_spacing_shadow(self):
        base=typeset(r'\htmlStyle{padding:0px;}{FF}',font_size=40,trust=True)
        rich=typeset(r'\htmlStyle{background-color:yellow;border:2px solid blue;border-radius:4px;padding:6px;letter-spacing:3px;text-decoration:underline red wavy;text-shadow:3px 4px 2px green;}{FF}',font_size=40,trust=True)
        im=img(render_box(rich,backend='cpu',background='white'))
        self.assertGreater(rich.width,base.width+10)
        self.assertGreater(sum(p[0]>220 and p[1]>220 and p[2]<70 for p in im.getdata()),30)
        self.assertGreater(sum(p[2]>170 and p[0]<100 for p in im.getdata()),15)
        self.assertGreater(sum(p[0]>120 and p[1]<100 and p[2]<100 for p in im.getdata()),2)
        self.assertGreater(sum(p[1]>p[0]*1.3 and p[1]>p[2]*1.3 for p in im.getdata()),2)
        actual=ink_bbox(im);self.assertGreaterEqual(actual[0],7);self.assertLessEqual(actual[2],im.width-7)

    def test_unknown_visible_css_and_executable_css_have_explicit_errors(self):
        for style in ('content:"missing"','background-image:url(https://example.com/x)','position:fixed','transform:rotateX(30deg)'):
            with self.subTest(style=style),self.assertRaises(ParseError):typeset(r'\htmlStyle{'+style+'}{x}',font_size=32,trust=True)

    def test_html_data_attribute_name_is_rejected_only_at_source_build_boundary(self):
        # html.ts parses metadata; domTree.ts checks attribute names when
        # building markup. Native static adapter keeps this exact distinction.
        for name in ('a>b','a b','a"b',"a'b",'a/b'):
            tex=r'\htmlData{'+name+'=value}{x}'
            with self.subTest(name=name):
                self.assertIsNotNone(parse(tex,trust=True,strict=False))
                with self.assertRaises(ParseError) as caught:typeset(tex,trust=True,strict=False)
                self.assertEqual(caught.exception.code,'INVALID_HTML_ATTRIBUTE')

    def test_html_opacity_display_and_visibility_do_not_silently_paint(self):
        visible=typeset(r'\htmlStyle{opacity:0.5;}{\htmlStyle{opacity:0.5;}{x}}',font_size=48,trust=True)
        im=img(render_box(visible,backend='cpu',background='white'));minimum=min(min(p) for p in im.getdata())
        self.assertGreaterEqual(minimum,185);self.assertLess(minimum,205)
        hidden=typeset(r'\htmlStyle{visibility:hidden;}{x}',font_size=48,trust=True)
        removed=typeset(r'\htmlStyle{display:none;}{x}',font_size=48,trust=True)
        self.assertGreater(hidden.width,0);self.assertEqual(removed.width,0);self.assertEqual(dark_count(img(render_box(hidden,backend='cpu',background='white'))),0)

    def test_group_affine_clip_and_filter_have_actual_spatial_effect(self):
        group=CommandGroup((Rule(0,-20,40,20,'red'),),x=10,y=0,matrix=(0,1,-1,0,0,0),clip=(0,-20,20,20),opacity=.5)
        im=img(render_box(MathBox(60,30,30,(group,)),backend='cpu',background='white'))
        red=[(x,y) for y in range(im.height) for x in range(im.width) if im.getpixel((x,y))[0]>240 and 110<im.getpixel((x,y))[1]<150]
        self.assertGreater(len(red),200);self.assertLess(len(red),500)
        plain=MathBox(20,20,0,(Rule(0,-20,20,20),));blurred=replace(plain,commands=(CommandGroup(plain.commands,filter='blur(3px)'),))
        a=img(render_box(plain,backend='cpu',background='white'));b=img(render_box(blurred,backend='cpu',background='white'))
        self.assertGreater(b.width,a.width);self.assertTrue(any(15<min(p)<235 for p in b.getdata()))

    def test_source_pmb_retains_real_blurred_second_layer(self):
        b=typeset(r'\pmb{F}',font_size=60);groups=[c for c in b.commands if isinstance(c,CommandGroup)]
        self.assertTrue(any('blur(0.04px)' in c.filter for c in groups))
        actual=img(render_box(b,backend='cpu',background='white'));normal=img(render_box(typeset('F',font_size=60),backend='cpu',background='white'))
        self.assertGreater(dark_count(actual),dark_count(normal))

    def test_logical_width_smash_lap_and_content_width_preserve_overflow_ink(self):
        for tex,settings in [(r'\llap{MMMM}',{}),(r'\smash{\frac{1}{2}}',{}),('MMMMMMMM',{'display_mode':True,'content_width':20})]:
            with self.subTest(tex=tex):
                box=typeset(tex,font_size=36,**settings);old=(box.width,box.height,box.depth)
                result=render_box(box,backend='cpu',background='white');bounds=ink_bbox(img(result))
                self.assertIs(result.box,box);self.assertEqual((box.width,box.height,box.depth),old);self.assertIsNotNone(bounds)
                self.assertGreaterEqual(bounds[0],7);self.assertGreaterEqual(bounds[1],7);self.assertLessEqual(bounds[2],result.width-7);self.assertLessEqual(bounds[3],result.height-7)
                if tex.startswith(r'\llap') or settings:self.assertGreater(result.width,box.width+16)
                if tex.startswith(r'\smash'):self.assertGreater(result.height,box.height+box.depth+16)

    def test_exact_rule_affine_negative_ink_bounds_without_helper_expected(self):
        box=MathBox(10,5,0,(CommandGroup((Rule(-30,-10,20,10),),matrix=(1,0,0,1,-5,-2)),))
        self.assertEqual(ink_bounds(box),(-35,-12,-15,-2))
        result=render_box(box,backend='cpu',background='white');self.assertEqual((result.width,result.height),(61,28))
        self.assertEqual(img(result).getpixel((9,9)),(0,0,0))

    def test_transparent_commands_do_not_invent_extra_export_extent(self):
        box=MathBox(20,20,0,(CommandGroup((Rule(-1000,-1000,3000,3000),),opacity=0),Rule(-900,-900,2000,2000,'transparent')))
        self.assertIsNone(ink_bounds(box));result=render_box(box,backend='cpu');self.assertEqual((result.width,result.height),(36,36))

    def test_stroke_and_rotation_overflow_not_cropped_at_physical_edges(self):
        box=MathBox(0,0,0,(CommandGroup((Path('M-40 -20L40 20',stroke_width=4),),matrix=(0,1,-1,0,0,0)),))
        result=render_box(box,backend='cpu',background='white');bounds=ink_bbox(img(result));self.assertGreater(result.width,40);self.assertGreater(result.height,80)
        self.assertGreaterEqual(bounds[0],7);self.assertGreaterEqual(bounds[1],7);self.assertLess(bounds[2],result.width-6);self.assertLess(bounds[3],result.height-6)

    def test_resources_and_groups_export_five_formats_with_native_backends(self):
        # SVG Image keeps vector paint in native vector exports; raster inputs
        # independently exercise encoded image embedding.
        for resource_kind,data in (('vector',QUAD.encode()),('raster',raster('PNG'))):
            resource=image_resource('quad',data);box=MathBox(40,20,0,(ImageCommand(resource,0,-20,40,20),))
            for backend in ('cpu','auto','gpu'):
                for fmt,magic in [('png',bytes.fromhex('89504e47')),('jpg',bytes.fromhex('ffd8')),('webp',b'RIFF'),('svg',b'<'),('pdf',b'%PDF')]:
                    with self.subTest(resource=resource_kind,backend=backend,format=fmt):
                        r=render_box(box,backend=backend,format=fmt,background='white');self.assertTrue(r.data.lstrip().startswith(magic));self.assertEqual((r.width,r.height),(56,36))
                        if backend in ('cpu','gpu'):self.assertEqual(dict(r.backend)['renderer'],backend.upper())
                        if fmt in ('png','jpg','webp'):assert_quad(img(r),tolerance=40)
                        elif fmt=='svg':
                            root=ET.fromstring(r.data)
                            if resource_kind=='raster':self.assertTrue(any(node.tag.rsplit('}',1)[-1]=='image' for node in root.iter()))
                            else:
                                from PIL import ImageColor
                                colors={ImageColor.getrgb(node.get('fill')) for node in root.iter() if node.get('fill') and node.get('fill')!='none'}
                                self.assertTrue({(255,0,0),(0,255,0),(0,0,255),(255,255,0)}<=colors)
                            from py_skia_canvas import Image as NativeImage
                            native=NativeImage(r.data);c=Canvas(56,36);c.gpu=False;context=c.getContext('2d');context.drawImage(native,0,0)
                            decoded=Image.open(BytesIO(c.toBufferSync('png'))).convert('RGB');assert_quad(decoded,tolerance=40)
                        else:
                            self.assertRegex(r.data,rb'/MediaBox\s*\[\s*0\s+0\s+56\s+36\s*\]')
                            if resource_kind=='raster':self.assertIn(b'/Subtype /Image',r.data)
                            else:
                                streams=[]
                                for payload in re.findall(rb'stream\r?\n(.*?)\r?\nendstream',r.data,re.S):
                                    try:streams.append(zlib.decompress(payload))
                                    except zlib.error:streams.append(payload)
                                content=b'\n'.join(streams).decode('latin1')
                                colors=[tuple(float(v) for v in values) for values in re.findall(r'([-+.\d]+)\s+([-+.\d]+)\s+([-+.\d]+)\s+rg\b',content)]
                                for expected in ((1,0,0),(0,1,0),(0,0,1),(1,1,0)):
                                    self.assertTrue(any(max(abs(a-b) for a,b in zip(actual,expected))<1e-6 for actual in colors),(expected,colors))
                                self.assertRegex(content,r'\bf\b')

    def test_native_owner_guard_for_group_image_and_ink_queries(self):
        c=Canvas(30,30);ctx=c.getContext('2d');resource=image_resource('quad',QUAD.encode());box=MathBox(40,20,0,(ImageCommand(resource,0,-20,40,20),))
        def attempt(fn):
            try:fn();return None
            except Exception as exc:return exc
        with ThreadPoolExecutor(max_workers=1) as pool:
            for fn in (lambda:draw(ctx,box),lambda:ink_bounds(box,ctx)):
                self.assertIsNotNone(pool.submit(attempt,fn).result())

    def test_native_command_noop_image_is_rejected_by_color_oracle(self):
        resource=image_resource('quad',QUAD.encode());box=MathBox(40,20,0,(ImageCommand(resource,0,-20,40,20),))
        good=render_box(box,backend='cpu',background='white');assert_quad(img(good))
        with patch('py_katex.canvas.draw',return_value=None):bad=render_box(box,backend='cpu',background='white')
        with self.assertRaises(AssertionError):assert_quad(img(bad))

if __name__=='__main__':unittest.main()
