"""Public Python/CLI projections of fixed Settings and source visible errors."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO

from PIL import Image
from py_katex import MacroState,Options,ParseError,render,typeset

ROOT=Path(__file__).resolve().parents[1]


class FullPublicApiTests(unittest.TestCase):
    def test_explicit_state_reaches_parser_and_persists_only_selected_namespace(self):
        state=MacroState()
        typeset(r'\def\NativeStateProof{\mathbb{R}}',macro_state=state,global_group=True)
        box=typeset(r'x\in\NativeStateProof',macro_state=state)
        self.assertGreater(box.width,0)
        # The fixed source already defines \R (macros.ts:852); use a genuinely
        # fresh control sequence to test request isolation, not a builtin.
        with self.assertRaises(ParseError):typeset(r'\NativeStateProof')

    def test_display_and_leqno_options_reach_real_tag_parser_and_layout(self):
        with self.assertRaises(ParseError):typeset(r'x\tag{A}',display_mode=False)
        box=typeset(r'x\tag{A}',display_mode=True,leqno=True,content_width=400)
        self.assertAlmostEqual(box.width,400)
        self.assertFalse(box.diagnostics)

    def test_native_size_cap_is_source_em_limit_at_public_entry(self):
        box=typeset(r'\rule{10em}{5em}',font_size=20,max_size=1)
        self.assertAlmostEqual(box.width,20)
        self.assertAlmostEqual(box.height+box.depth,20)

    def test_no_throw_keeps_visible_error_metadata_and_actual_error_color(self):
        result=render(r'\frac{1}',throw_on_error=False,error_color='#cc0000',backend='cpu',background='white')
        self.assertTrue(result.box.diagnostics)
        image=Image.open(BytesIO(result.data)).convert('RGB')
        self.assertGreater(sum(r>g*1.5 and r>b*1.5 and g<180 for r,g,b in image.getdata()),5)

    def test_default_error_behavior_still_raises_source_parse_failure(self):
        with self.assertRaises(ParseError):render(r'\frac{1}',backend='cpu')

    def test_color_compatibility_and_macros_are_effective_at_render_entry(self):
        result=render(r'\color{red}{\foo}+y',macros={r'\foo':'x'},color_is_text_color=True,backend='cpu',background='white')
        image=Image.open(BytesIO(result.data)).convert('RGB')
        self.assertTrue(any(r>180 and g<100 and b<100 for r,g,b in image.getdata()))
        self.assertTrue(any(max(r,g,b)<100 for r,g,b in image.getdata()))


class FullCliTests(unittest.TestCase):
    def invoke(self,folder,expression,filename,extra=()):
        output=Path(folder)/filename
        env={**os.environ,'PYTHONPATH':str(ROOT/'src')+os.pathsep+str(ROOT.parent/'py-mermaid/src'),'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'}
        command=[sys.executable,'-m','py_katex',expression,'-o',str(output),'--backend','cpu',*extra]
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,msg=result.stderr)
        receipt=json.loads(result.stdout)
        return output,receipt

    def test_cli_explicit_density_scales_actual_png_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            one,a=self.invoke(folder,'x','one.png')
            two,b=self.invoke(folder,'x','two.png',['--density','2'])
            with Image.open(one) as first,Image.open(two) as second:
                self.assertEqual(second.size,(first.width*2,first.height*2))
                self.assertEqual(second.size,(b['width'],b['height']))

    def test_cli_fractional_expansion_threshold_follows_source_number_option(self):
        with tempfile.TemporaryDirectory() as folder:
            output,receipt=self.invoke(folder,r'\foo','macro.png',['--macro',r'\foo=x','--max-expand','1.5'])
            self.assertGreater(output.stat().st_size,100)
            self.assertEqual(receipt['diagnostics'],[])

    def test_cli_display_tag_and_visible_error_have_different_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            _,tag=self.invoke(folder,r'x\tag{A}','tag.svg',['--display','--leqno','--content-width','400'])
            _,error=self.invoke(folder,r'\frac{1}','error.png',['--no-throw'])
            self.assertEqual(tag['diagnostics'],[])
            self.assertTrue(error['diagnostics'])

    def test_cli_requires_explicit_image_resource_and_draws_source_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            output,receipt=self.invoke(folder,r'\includegraphics[height=1em]{logo}','image.png',
                 ['--trust','--strict','ignore','--image','logo='+str(ROOT/'.local/upstream-katex/website/static/img/khan-academy.png')])
            self.assertFalse(receipt['diagnostics'])
            with Image.open(output) as image:self.assertGreater(image.width,16)


if __name__=='__main__':unittest.main()
