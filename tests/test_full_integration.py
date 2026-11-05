"""Real public Mermaid/ELK/native math integration, no hand-built diagrams.

Source Mermaid keeps trustfalse and HTMLfalse literal. Logical math geometry
remains TeX geometry, while actual overflow must stay inside encoded viewport.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import math,unittest
from unittest.mock import patch
from PIL import Image,ImageChops
from py_mermaid.api import render,parse
from py_mermaid.rendering.skia import CanvasSession
from py_mermaid.model.flowchart import ImageResource,ResourceBundle,MermaidError
from py_katex.model import CommandGroup

QUAD='<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="red"/></svg>'

def source(tex,prefix='',suffix=''):
    # Input is independent TeX. createText's HTML branch folds actual double
    # slashes once, so the Mermaid source contains two per intended TeX slash.
    return 'flowchart TD\nA["'+prefix+'$$'+tex.replace('\\','\\\\')+'$$'+suffix+'"]'

def image(r):
    im=Image.open(BytesIO(r.data));im.load();return im.convert('RGB')

def glyph_pixels(r):
    im=image(r);events=[e for e in r.trace if e.kind=='math'];assert events
    count=0
    for e in events:
        b=e.box;crop=im.crop((max(0,math.floor(b.x)),max(0,math.floor(b.y)),min(im.width,math.ceil(b.x+b.width)),min(im.height,math.ceil(b.y+b.height))))
        count+=sum(min(p)<150 for p in crop.getdata())
    assert count>2,'no real mathematical glyph ink'
    return events

class FullMathIntegrationTests(unittest.TestCase):
    def test_unicode_text_mixed_with_math_and_plain_labels(self):
        text='\u79c1\u306f\u30d0\u30ca\u30ca'
        r=render(source(r'\text{'+text+'}+x','Before ',' after'),backend='cpu');glyph_pixels(r)
        self.assertTrue(any(text in (e.text or '') for e in r.trace if e.kind=='math-glyph'))
        self.assertTrue(any('Before' in (e.text or '') for e in r.trace if e.kind=='text'))
        self.assertTrue(any('after' in (e.text or '') for e in r.trace if e.kind=='text'))

    def test_source_trustfalse_keeps_includegraphics_visible_rejection(self):
        resources=ResourceBundle(images=(ImageResource('quad',QUAD.encode(),'image/svg+xml'),))
        r=render(source(r'\includegraphics{quad}'),resources=resources,backend='cpu')
        self.assertFalse(any(e.kind=='math-image' for e in r.trace));self.assertTrue(r.diagnostics)
        self.assertTrue(any(e.kind=='math-diagnostic' for e in r.trace))
        self.assertGreater(sum(p[0]>120 and p[1]<110 and p[2]<110 for p in image(r).getdata()),4)

    def test_source_trustfalse_htmlstyle_does_not_execute_inline_css(self):
        r=render(source(r'\htmlStyle{color:lime}{x}'),backend='cpu')
        self.assertTrue(r.diagnostics);self.assertTrue(any(e.kind=='math-diagnostic' for e in r.trace))
        self.assertFalse(any(p[1]>220 and p[0]<50 and p[2]<50 for p in image(r).getdata()))
        self.assertGreater(sum(p[0]>120 and p[1]<110 and p[2]<110 for p in image(r).getdata()),4)

    def test_repeated_pure_cache_keeps_per_request_diagnostics(self):
        d=parse(source(r'\includegraphics{offline}'));s=CanvasSession('cpu')
        first=s.measure(d);first_diagnostics=tuple(s._diagnostics)
        second=s.measure(d);second_diagnostics=tuple(s._diagnostics)
        self.assertTrue(first_diagnostics);self.assertEqual(first_diagnostics,second_diagnostics);self.assertEqual(first,second)
        self.assertTrue(any(run.kind=='math' for run in second[0].runs))

    def test_lap_overflow_extends_real_viewport_without_changing_logical_node(self):
        tex=r'\llap{MMMMMMMMMMMMMMMMMMMM}'
        r=render(source(tex),backend='cpu')
        # Source lap has zero logical advance, but the ink lies well left of the
        # ordinary min120px node. It must be exported rather than clipped away.
        self.assertLessEqual(r.measured[0].label_width,120.0001)
        self.assertGreater(r.width,r.measured[0].width+25)
        im=image(r);firstcol=min(x for y in range(im.height) for x in range(im.width) if max(im.getpixel((x,y)))<150)
        self.assertGreaterEqual(firstcol,7)
        glyphs=[e for e in r.trace if e.kind=='math-glyph'];self.assertTrue(glyphs)
        self.assertTrue(all(e.points[0].x>=0 for e in glyphs))
        with patch('py_katex.canvas.draw',return_value=None):bad=render(source(tex),backend='cpu')
        self.assertGreater(sum(ImageChops.difference(im,image(bad)).convert('L').getdata()),5000)

    def test_smash_vertical_ink_is_inside_export_for_node_edge_group(self):
        tex=r'\smash{\frac{\frac{1}{2}}{\frac{3}{4}}}'
        encoded=tex.replace('\\','\\\\')
        text='flowchart TD\nsubgraph G["$$'+encoded+'$$"]\nA["$$'+encoded+'$$"] -->|"$$'+encoded+'$$"| B["End"]\nend'
        r=render(text,backend='cpu');self.assertEqual(len([e for e in r.trace if e.kind=='math']),3)
        im=image(r)
        # Every pixel of mathematical ink and route/frame is guarded by the
        # source diagram outer padding, even for zero-height TeX boxes.
        edge=[]
        for y in range(im.height):edge.extend(im.getpixel((x,y)) for x in (0,1,im.width-2,im.width-1))
        for x in range(im.width):edge.extend(im.getpixel((x,y)) for y in (0,1,im.height-2,im.height-1))
        self.assertTrue(all(min(p)>235 for p in edge))
        with patch('py_katex.canvas.draw',return_value=None):bad=render(text,backend='cpu')
        self.assertGreater(sum(ImageChops.difference(im,image(bad)).convert('L').getdata()),5000)

    def test_cd_tag_new_groups_keep_nested_glyph_trace_and_pixels(self):
        tex=r'\begin{CD}A@>f>>B\\@VgVV@VVhV\\C@>>k>D\end{CD}'
        r=render(source(tex),backend='cpu');glyph_pixels(r)
        texts=''.join(e.text or '' for e in r.trace if e.kind=='math-glyph')
        for value in 'ABCDfghk':self.assertIn(value,texts)
        self.assertTrue(any(e.kind=='math-path' for e in r.trace))
        self.assertTrue(all(0<=p.x<=r.width and 0<=p.y<=r.height for e in r.trace if e.kind=='math-glyph' for p in e.points[:1]))

    def test_pmb_command_group_is_drawn_and_traced_recursively(self):
        r=render(source(r'\pmb{F}'),backend='cpu');glyph_pixels(r)
        self.assertTrue(any(e.kind=='math-group' for e in r.trace))
        glyphs=[e for e in r.trace if e.kind=='math-glyph' and e.text=='F']
        self.assertGreaterEqual(len(glyphs),2)
        self.assertGreater(max(e.points[0].x for e in glyphs)-min(e.points[0].x for e in glyphs),0)

    def test_htmlfalse_remains_literal_even_for_promoted_static_commands(self):
        r=render(source(r'\includegraphics{offline}'),config={'htmlLabels':False},backend='cpu')
        self.assertFalse(any(e.kind.startswith('math') for e in r.trace))
        visible=''.join(e.text or '' for e in r.trace if e.kind=='text')
        self.assertIn('$$',visible);self.assertIn('includegraphics',visible)

    def test_formula_math_run_paint_and_visibility_noop_negative_control(self):
        original=source(r'\pmb{F}+\frac{1}{2}')
        good=render(original,backend='cpu');glyph_pixels(good)
        with patch('py_katex.canvas.draw',return_value=None):bad=render(original,backend='cpu')
        self.assertTrue(any(e.kind=='math-group' for e in bad.trace))
        with self.assertRaises(AssertionError):glyph_pixels(bad)

    def test_colour_fallback_mixed_run_smash_reaches_actual_viewport(self):
        word=chr(0x0411)+chr(0x270c)+chr(0x0413)
        tex=r'\smash{\frac{\text{'+word+r'}}{\text{'+word+'}}}'
        text=source(tex);result=render(text,backend='cpu');im=image(result)
        self.assertTrue(any(chr(0x270c) in (event.text or '') for event in result.trace if event.kind=='math-glyph'))
        # Include all colored channels, rather than treating bright yellow as
        # white or relying on a nonexistent color-font outline.
        border=[im.getpixel((x,y)) for x in range(im.width) for y in (0,im.height-1)]
        border.extend(im.getpixel((x,y)) for y in range(im.height) for x in (0,im.width-1))
        self.assertTrue(all(min(pixel)>245 for pixel in border))
        with patch('py_katex.canvas.draw',return_value=None):missing=render(text,backend='cpu')
        self.assertEqual(im.size,image(missing).size)
        self.assertGreater(sum(ImageChops.difference(im,image(missing)).convert('L').getdata()),1000)

    def test_unicode_math_state_remains_owner_thread_only(self):
        d=parse(source(r'\text{'+chr(0x0411)+'}'));s=CanvasSession('cpu')
        def attempt():
            try:s.measure(d);return None
            except MermaidError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=1) as pool:code=pool.submit(attempt).result()
        self.assertEqual(code,'THREAD_OWNERSHIP')

    def test_five_export_formats_keep_new_group_content(self):
        for fmt,magic in [('png',b'\x89PNG'),('jpg',b'\xff\xd8'),('webp',b'RIFF'),('svg',b'<'),('pdf',b'%PDF')]:
            with self.subTest(format=fmt):
                r=render(source(r'\pmb{F}+\frac{1}{2}'),format=fmt,backend='cpu')
                self.assertTrue(r.data.lstrip().startswith(magic));self.assertTrue(any(e.kind=='math-glyph' for e in r.trace))
                if fmt in ('png','jpg','webp'):glyph_pixels(r)

if __name__=='__main__':unittest.main()
