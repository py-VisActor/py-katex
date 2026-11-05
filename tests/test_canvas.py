"""Independent source/PNG controls. Import creates no native object or output.

KaTeX genfrac/supsub/sqrt/array and bundled fonts are the expectations. Test-only
command deletion and ordinary-text painting demonstrate that geometry metadata
or successful encoding alone cannot satisfy the visible mathematics oracle.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path as FilePath
import math,re,unittest
from PIL import Image,ImageChops
from py_skia_canvas import Canvas,FontLibrary
from py_katex import typeset,render
from py_katex.canvas import draw,render_box
from py_katex.model import MathBox,Glyph,Rule,Path,ParseError

FONTS=('AMS-Regular','Caligraphic-Bold','Caligraphic-Regular','Fraktur-Bold','Fraktur-Regular','Main-Bold','Main-BoldItalic','Main-Italic','Main-Regular','Math-BoldItalic','Math-Italic','SansSerif-Bold','SansSerif-Italic','SansSerif-Regular','Script-Regular','Size1-Regular','Size2-Regular','Size3-Regular','Size4-Regular','Typewriter-Regular')

def image(result):
    result=Image.open(BytesIO(result.data));result.load()
    rgba=result.convert('RGBA');white=Image.new('RGBA',rgba.size,'white');white.alpha_composite(rgba)
    return white.convert('RGB')

def ink(im,rect=None):
    if rect:im=im.crop(tuple(round(x) for x in rect))
    return sum(max(pixel)<170 for pixel in im.getdata())

def region(im,rect,minimum=2):
    assert ink(im,rect)>=minimum,(rect,'missing mathematical ink')

def fraction_pixels(im,width,baseline,padding=8,size=40):
    # KaTeX fontMetrics axisHeight=.25em/defaultRuleThickness=.04em.
    # Main-Regular digits have advance .5em; display numerator and denominator
    # occupy opposite sides of the rule, with nonzero source clearances.
    y=baseline-size*.25
    left=round(padding+.12*size)  # genfrac's two source null delimiters
    row=max(sum(max(im.getpixel((x,yy)))<170 for x in range(left,left+round(width))) for yy in range(math.floor(y)-1,math.ceil(y)+2))
    assert row>=width*.75,'missing fraction rule'
    region(im,(left,0,left+width,y-3))
    region(im,(left,y+3,left+width,im.height))

class CanvasTests(unittest.TestCase):
    def test_all_twenty_bundled_font_aliases_real_pixels(self):
        fontdir=FilePath(__file__).resolve().parents[1]/'src/py_katex/data/fonts'
        for key in FONTS:
            with self.subTest(font=key):
                # Size fonts contain delimiter parentheses, rather than Latin A.
                text='(' if key.startswith('Size') else 'A'
                box=MathBox(60,55,20,(Glyph(text,8,0,key,36),))
                result=render_box(box,backend='cpu',background='white');im=image(result)
                self.assertTrue((fontdir/('KaTeX_'+key+'.ttf')).is_file())
                self.assertTrue(FontLibrary.has('PyKaTeX_'+key))
                self.assertGreater(ink(im),12)

    def test_italic_bold_faces_match_independent_public_canvas_reference(self):
        fontdir=FilePath(__file__).resolve().parents[1]/'src/py_katex/data/fonts'
        for key,style,weight,text in [('Math-Italic','italic','400','x'),('Main-Bold','normal','700','F'),('Main-BoldItalic','italic','700','F')]:
            with self.subTest(font=key):
                box=MathBox(70,45,10,(Glyph(text,12,0,key,40),));actual=image(render_box(box,backend='cpu',background='white'))
                alias='IndependentReference_'+key;FontLibrary.use(alias,str(fontdir/('KaTeX_'+key+'.ttf')))
                canvas=Canvas(86,71);canvas.gpu=False;ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,86,71)
                ctx.font=f'{style} {weight} 40px "{alias}"';ctx.textBaseline='alphabetic';ctx.fillStyle='black';ctx.fillText(text,20,53)
                reference=Image.open(BytesIO(canvas.toBufferSync('png'))).convert('RGB')
                self.assertEqual(actual.tobytes(),reference.tobytes())
                normal=image(render_box(replace(box,commands=(replace(box.commands[0],font='Main-Regular'),)),backend='cpu',background='white'))
                self.assertGreater(sum(ImageChops.difference(actual,normal).convert('L').getdata()),1000)

    def test_fraction_two_dimensional_pixels_and_source_rule(self):
        box=typeset(r'\frac{1}{2}',font_size=40,display_mode=True)
        self.assertAlmostEqual(box.width,(.5+2*.12)*40,places=5)
        result=render_box(box,backend='cpu',background='white')
        fraction_pixels(image(result),20,8+box.height)
        self.assertTrue(any(isinstance(c,Rule) for c in box.commands))

    def test_fraction_pixel_oracle_rejects_blank_lost_rule_plain_string(self):
        box=typeset(r'\frac{1}{2}',font_size=40,display_mode=True)
        baseline=8+box.height;good=image(render_box(box,backend='cpu',background='white'))
        fraction_pixels(good,20,baseline)
        blank=Image.new('RGB',good.size,'white')
        missing=image(render_box(replace(box,commands=tuple(c for c in box.commands if not isinstance(c,Rule))),backend='cpu',background='white'))
        canvas=Canvas(good.width,good.height);canvas.gpu=False;ctx=canvas.getContext('2d')
        ctx.fillStyle='white';ctx.fillRect(0,0,good.width,good.height);ctx.fillStyle='black';ctx.font='40px Arial';ctx.fillText(r'\frac{1}{2}',8,baseline)
        plain=Image.open(BytesIO(canvas.toBufferSync('png'))).convert('RGB')
        for bad in (blank,missing,plain):
            with self.assertRaises(AssertionError):fraction_pixels(bad,20,baseline)

    def test_scripts_actual_upper_and_lower_ink_negative_control(self):
        box=typeset(r'x_1^2',font_size=40);result=render_box(box,backend='cpu',background='white');im=image(result)
        glyphs=[c for c in box.commands if isinstance(c,Glyph)]
        base=next(c for c in glyphs if c.text=='x');up=next(c for c in glyphs if c.text=='2');down=next(c for c in glyphs if c.text=='1')
        self.assertLess(up.y,base.y);self.assertGreater(down.y,base.y)
        self.assertAlmostEqual(up.size,28);self.assertAlmostEqual(down.size,28)
        # Main Math-Italic x source height .43056/depth0 excludes all base
        # ink. These strict exterior bands cannot pass after deleting scripts.
        baseline=8+box.height
        areas=((8,0,8+box.width,baseline-.43056*40-1),(8,baseline+1,8+box.width,8+box.height+box.depth+8))
        for rect in areas:region(im,rect)
        missing=image(render_box(replace(box,commands=(base,)),backend='cpu',background='white'))
        with self.assertRaises(AssertionError):region(missing,areas[0])

    def test_square_root_native_path_and_rule_pixels(self):
        box=typeset(r'\sqrt{x+1}',font_size=36);im=image(render_box(box,backend='cpu',background='white'))
        self.assertTrue(any(isinstance(c,Path) for c in box.commands));self.assertGreater(ink(im),120)
        # Radical has visible left hook and upper vinculum, absent plain radicand.
        region(im,(8,8,8+min(20,box.width/3),8+box.height+box.depth))
        pathless=image(render_box(replace(box,commands=tuple(c for c in box.commands if not isinstance(c,Path))),backend='cpu',background='white'))
        self.assertGreater(ink(im)-ink(pathless),12)

    def test_matrix_actual_four_cells_on_two_rows(self):
        box=typeset(r'\begin{matrix}1&2\\3&4\end{matrix}',font_size=32,display_mode=True)
        glyphs=[c for c in box.commands if isinstance(c,Glyph) and c.text in '1234']
        self.assertEqual(len(glyphs),4)
        positions={c.text:(c.x,c.y) for c in glyphs}
        self.assertLess(positions['1'][0],positions['2'][0]);self.assertLess(positions['1'][1],positions['3'][1])
        im=image(render_box(box,backend='cpu',background='white'))
        for c in glyphs:region(im,(8+c.x,8+box.height+c.y-c.size,8+c.x+c.size,8+box.height+c.y+3))
        oneline=replace(box,commands=tuple(replace(c,y=0) if isinstance(c,Glyph) else c for c in box.commands))
        bad=image(render_box(oneline,backend='cpu',background='white'))
        first=min(c.y for c in glyphs)
        with self.assertRaises(AssertionError):region(bad,(8,8,8+box.width,8+box.height+first-3))

    def test_public_path_local_clip_preserves_large_viewbox(self):
        box=MathBox(80,20,0,(Path('M0 0H400000V20H0Z',y=-20,clip=(10,0,30,20)),))
        im=image(render_box(box,backend='cpu',background='white'))
        self.assertEqual(im.getpixel((20,18)),(0,0,0));self.assertEqual(im.getpixel((55,18)),(255,255,255))
        self.assertEqual(im.getpixel((12,18)),(255,255,255))
        self.assertEqual(ink(im),600)

    def test_reflected_glyph_real_mirror_and_normal_negative_control(self):
        normal=MathBox(70,45,10,(Glyph('F',12,0,'Main-Regular',40),))
        reflected=replace(normal,commands=(replace(normal.commands[0],x=58,scale_x=-1),))
        a=image(render_box(normal,backend='cpu',background='white'));b=image(render_box(reflected,backend='cpu',background='white'))
        # Axis x=padding+35, so full image width86 mirrors x to 85-x (1px
        # raster phase tolerance handled by best adjacent translation).
        flip=a.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        scores=[]
        for offset in (-1,0,1):scores.append(sum(ImageChops.difference(b,ImageChops.offset(flip,offset,0)).convert('L').getdata()))
        self.assertLess(min(scores),5000);self.assertGreater(sum(ImageChops.difference(a,b).convert('L').getdata()),10000)

    def test_signed_height_depth_and_baseline_origin(self):
        box=MathBox(20,-2,12,(Rule(0,2,20,10),));r=render_box(box,backend='cpu',background='white');im=image(r)
        self.assertEqual((r.width,r.height),(36,26));self.assertEqual(im.getpixel((10,10)),(0,0,0));self.assertEqual(im.getpixel((10,6)),(255,255,255))
        self.assertEqual(ink(im),200)

    def test_draw_offset_and_context_state_restored(self):
        canvas=Canvas(80,70);canvas.gpu=False;ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,80,70);ctx.fillStyle='red'
        draw(ctx,MathBox(20,10,0,(Rule(0,-10,20,10),)),30,40)
        ctx.fillRect(0,0,5,5);im=Image.open(BytesIO(canvas.toBufferSync('png'))).convert('RGB')
        self.assertEqual(im.getpixel((35,35)),(0,0,0));self.assertEqual(im.getpixel((2,2)),(255,0,0));self.assertEqual(im.getpixel((25,35)),(255,255,255))

    def test_native_five_export_signatures_and_dimensions(self):
        box=MathBox(40,20,10,(Rule(0,-20,40,30,'#153c9a'),))
        for fmt,magic,mime in [('png',b'\x89PNG','image/png'),('jpg',b'\xff\xd8','image/jpeg'),('webp',b'RIFF','image/webp'),('pdf',b'%PDF-','application/pdf'),('svg',b'<','image/svg+xml')]:
            with self.subTest(format=fmt):
                r=render_box(box,format=fmt,backend='cpu',padding=8,background='white');self.assertEqual(r.mime,mime);self.assertEqual((r.width,r.height),(56,46))
                self.assertTrue(r.data.lstrip().startswith(magic))
                if fmt in ('png','jpg','webp'):self.assertEqual(image(r).size,(56,46));self.assertGreater(ink(image(r)),800)
                elif fmt=='svg':self.assertIn(b'<svg',r.data);self.assertIn(b'56',r.data);self.assertIn(b'46',r.data)
                else:self.assertIn(b'/MediaBox',r.data)

    def test_cpu_auto_gpu_backend_contract(self):
        box=MathBox(12,12,0,(Rule(0,-12,12,12),))
        self.assertEqual(dict(render_box(box,backend='cpu').backend)['renderer'],'CPU')
        expected=Canvas(2,2).engine['renderer'];self.assertEqual(dict(render_box(box,backend='auto').backend)['renderer'],expected)
        if expected=='GPU':self.assertEqual(dict(render_box(box,backend='gpu').backend)['renderer'],'GPU')
        else:
            with self.assertRaises(ParseError) as caught:render_box(box,backend='gpu')
            self.assertEqual(caught.exception.code,'GPU_UNAVAILABLE')

    def test_native_context_cross_thread_rejected(self):
        canvas=Canvas(40,40);ctx=canvas.getContext('2d');box=MathBox(10,10,0,(Rule(0,-10,10,10),))
        def attempt():
            try:draw(ctx,box);return None
            except Exception as exc:return exc
        with ThreadPoolExecutor(max_workers=1) as pool:result=pool.submit(attempt).result()
        self.assertIsNotNone(result)

    def test_repeat_draw_and_pure_box_owner_transfer(self):
        box=typeset(r'\frac{x^2}{y}',font_size=32)
        first=render_box(box,backend='cpu',background='white');second=render_box(box,backend='cpu',background='white')
        self.assertEqual(image(first).tobytes(),image(second).tobytes())
        with ThreadPoolExecutor(max_workers=1) as pool:third=pool.submit(lambda:render_box(box,backend='cpu',background='white')).result()
        self.assertEqual(image(first).tobytes(),image(third).tobytes())

    def test_invalid_commands_and_export_budgets_fail_explicitly(self):
        for box in (MathBox(-1,2,0),MathBox(1,-2,1),MathBox(1,2,0,(Glyph('x',0,0,'Main-Regular',20,scale_x=0),)),MathBox(1,2,0,(Path('M0 0',clip=(0,0,-1,1)),))):
            with self.subTest(box=box),self.assertRaises(ParseError):render_box(box,backend='cpu')
        for kwargs in ({'backend':'fallback'},{'format':'gif'},{'density':0},{'quality':2},{'padding':-1}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ParseError):render_box(MathBox(1,1,0),**kwargs)
        with self.assertRaises(ParseError):render_box(MathBox(100000,1,0))

if __name__=='__main__':unittest.main()
