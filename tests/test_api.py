"""Public math API safety and packaging contracts, independent of its layout."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import hashlib,json,math,tomllib,unittest
import py_katex
from py_katex import Options

ROOT=Path(__file__).resolve().parents[1]


class PublicContracts(unittest.TestCase):
    def test_version_and_native_dependency_are_explicit(self):
        project=tomllib.loads((ROOT/'pyproject.toml').read_text('utf-8'))['project']
        self.assertEqual(project['version'],py_katex.__version__)
        self.assertEqual(project['dependencies'],['py-skia-canvas==0.1.0a18'])
        self.assertIn('data/fonts/*.ttf',tomllib.loads((ROOT/'pyproject.toml').read_text('utf-8'))['tool']['setuptools']['package-data']['py_katex'])

    def test_twenty_fonts_are_exact_pinned_offline_files(self):
        lock=json.loads((ROOT/'references/upstream.lock.json').read_text('utf-8'))
        self.assertEqual(lock['version'],'0.18.11');self.assertEqual(len(lock['fontFiles']),20)
        for source,wanted in lock['fontFiles'].items():
            with self.subTest(source=source):
                data=(ROOT/'src/py_katex/data/fonts'/Path(source).name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),wanted)
        self.assertEqual(hashlib.sha256((ROOT/'references/licenses/katex-LICENSE').read_bytes()).hexdigest(),lock['licenseSha256'])

    def test_dimensions_and_budgets_reject_nonfinite_or_unbounded_inputs(self):
        for size in [0,-1,True,math.nan,math.inf,'20']:
            with self.subTest(size=size),self.assertRaises((ValueError,TypeError)):Options(font_size=size)
        for name,values in [('max_expand',[True,math.nan,'1000']),('max_depth',[0,257]),('max_nodes',[0,1000001])]:
            for value in values:
                with self.subTest(name=name,value=value),self.assertRaises((ValueError,TypeError)):Options(**{name:value})
        # Settings.ts maxExpand is numeric (not an integer capped at 100000).
        # Its processor clamps negative thresholds to zero; infinity is an
        # explicit source option. Native depth/node budgets remain independent.
        for value,wanted in [(0,0),(-1,0),(1.5,1.5),(100001,100001),(math.inf,math.inf)]:
            with self.subTest(source_max_expand=value):self.assertEqual(Options(max_expand=value).max_expand,wanted)

    def test_options_freeze_callers_macro_mapping(self):
        original={r'\RR':r'\mathbb{R}'};options=Options(macros=original)
        original[r'\RR']='x'
        self.assertEqual(dict(options.macros),{r'\RR':r'\mathbb{R}'})
        with self.assertRaises(FrozenInstanceError):options.font_size=10

    def test_typeset_options_and_direct_arguments_have_defined_precedence(self):
        # Numeric glyph width .5em is a literal Main-Regular metric in KaTeX.
        box=py_katex.typeset('1',options=Options(font_size=10,color='red'),font_size=30)
        self.assertAlmostEqual(box.width,15,places=5)
        self.assertEqual(box.commands[0].color,'red')
        self.assertEqual(box.commands[0].size,30)

    def test_cli_invalid_macro_is_rejected_before_a_success_file(self):
        from py_katex.__main__ import main
        with self.assertRaises(SystemExit) as caught:main(['x','-o','unused.png','--macro','invalid'])
        self.assertEqual(caught.exception.code,2)


if __name__=='__main__':unittest.main()
