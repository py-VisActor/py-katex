"""FULL source-independent layout assertions, authored before behavior runs.

Literal metrics: fixed KaTeX 0.18.11 fontMetricsData.js/fontMetrics.ts.
Geometry equations: cited upstream builders, not the native implementation.
No candidate private helper or candidate-produced coordinate golden is used.
"""
from dataclasses import replace
from pathlib import Path as FilePath
import math
import re
import unittest
import warnings
from unittest.mock import patch

from py_katex.layout import layout
from py_katex.model import CommandGroup, Diagnostic, FontResource, Glyph, MathBox, Node, Options, ParseError, Path, Rule
from py_katex.parser import parse

EM=20.
X_WIDTH=.57153
X_HEIGHT=.43056
X_SKEW=.02778
DIGIT_HEIGHT=.64444

def n(kind,value='',*children,**attrs):return Node(kind,value,tuple(children),tuple(attrs.items()))
def g(*children):return n('group','',*children)
def s(value,atom='mord',mode='math',**attrs):return n('symbol',value,atom=atom,mode=mode,font='main',**attrs)
def sub_sup(base,sup=None,sub=None,**attrs):return n('scripts','',base,sup or g(),sub or g(),**attrs)
def row(*cells):return n('row','',*(g(*cell) if isinstance(cell,tuple) else g(cell) for cell in cells))
def array(*rows,**attrs):return n('array','',*rows,**{'environment':'array','cols':(),'row_gaps':(),'hlines':(),**attrs})
def tag(body,caption,**attrs):return n('tag','',g(body),g(caption),**attrs)
def html(body,style):return n('html','htmlStyle',g(body),attributes=(('style',style),))
def commands(box):
    def visit(seq):
        for command in seq:
            if isinstance(command,CommandGroup):yield from visit(command.commands)
            else:yield command
    return list(visit(box.commands))
def gs(box):return [c for c in commands(box) if isinstance(c,Glyph)]
def rs(box):return [c for c in commands(box) if isinstance(c,Rule)]
def ps(box):return [c for c in commands(box) if isinstance(c,Path)]
def text(box):return ''.join(c.text for c in gs(box))


class FullLayoutSourceTests(unittest.TestCase):
    def near(self,a,b):self.assertAlmostEqual(a,b,places=7)

    # CD.ts projects horizontal arrows to xArrow and vertical arrows to Big.
    def test_f01_cd_all_horizontal_directions_preserve_labels_and_source_head_scale(self):
        for direction in ('>','<','='):
            with self.subTest(direction=direction):
                b=layout(n('cdarrow',direction,g(s('1')),g(s('2'))))
                self.near(b.width,3*EM)
                self.assertEqual(text(b),'12')
                self.near(gs(b)[0].size,.7*EM)
                self.near(gs(b)[0].x,(3*EM-.5*14)/2+(.27778-.55556)*14/2)
                self.assertTrue(ps(b))
                for path in ps(b):self.near(path.scale_x,.001*EM);self.near(path.scale_y,.001*EM)

    def test_f02_cd_both_vertical_arrows_have_real_arrow_and_two_script_labels(self):
        for direction in ('A','V'):
            b=layout(n('cdarrow',direction,g(s('1')),g(s('2'))))
            labels=[c for c in gs(b) if c.text in ('1','2')]
            self.assertEqual(len(labels),2)
            self.assertLess(labels[0].x,0)
            self.assertGreater(labels[1].x,b.width/2)
            self.assertTrue(all(c.size==14 for c in labels))
            self.assertTrue(ps(b) or any(c.text in ('↑','↓','⏐') for c in gs(b)))

    def test_f03_cd_no_arrow_is_source_space_not_an_unknown_empty_stub(self):
        b=layout(n('cdarrow','.',g(),g()))
        self.near(b.width,.25*EM)
        self.assertFalse(ps(b));self.assertFalse(rs(b))

    def test_f04_cd_parallel_bar_uses_source_doublevert_width(self):
        b=layout(n('cdarrow','|',g(),g()))
        self.near(b.width,.556*EM)
        self.assertEqual(len(ps(b)),1)
        self.assertIn('M367',ps(b)[0].d)

    def test_f05_internal_cdlabel_has_zero_tex_extents_with_visible_label_command(self):
        for side in ('left','right'):
            b=layout(n('cdlabel',side,g(s('1'))))
            self.assertEqual((b.width,b.height,b.depth),(0.,0.,0.))
            self.assertEqual(text(b),'1');self.near(gs(b)[0].size,14)

    def test_f06_internal_cdparent_anchors_labels_to_big_arrow_not_document(self):
        arrow=n('sized_delimiter','↑',size=2,atom='mord')
        b=layout(n('group','',g(n('cdlabel','left',g(s('1'))),arrow,n('cdlabel','right',g(s('2')))),cd_parent=True))
        left=next(c for c in gs(b) if c.text=='1');right=next(c for c in gs(b) if c.text=='2')
        self.near(left.x+.5*14,b.width/2-.3*14)
        self.near(right.x,b.width/2+.3*14)

    def test_f07_cd_uses_three_ex_baseline_jot_and_preserves_terminal_empty_row(self):
        b=layout(array(row(s('1')),row(s('2')),n('row'),environment='CD',cell_style='display',col_separation='CD',add_jot=True,hskip_before_after=False,arraystretch=1.))
        one,two=gs(b)
        self.near(two.y-one.y,(3*.431+.3)*EM)
        self.near(b.total_height,(3*3*.431+2*.3)*EM)

    def test_f08_cd_columns_have_quarter_em_pre_and_post_gaps(self):
        b=layout(array(row(s('1'),s('2')),environment='CD',col_specs=(('align','c',(.25,'em'),(.25,'em')),)*2,hskip_before_after=False))
        self.near(gs(b)[1].x-gs(b)[0].x,(.5+.25+.25)*EM)

    def test_f09_mandatory_empty_arrow_above_still_reserves_source_two_mu_clearance(self):
        b=layout(n('xarrow','xrightarrow',g(),g(),below_provided=False))
        # arrow.ts always includes the upper group, even when empty.
        self.near(b.height,(.25+.522/2+.111)*EM)

    def test_f10_explicit_empty_below_label_preserves_source_vlist_baseline(self):
        b=layout(n('xarrow','xrightarrow',g(s('1')),g(),below_provided=True))
        self.near(b.depth,(-.25+.522/2+.111)*EM)

    # buildHTML top tags + katex.scss absolute left/right and fleqn 2em.
    def test_f11_tag_uses_container_right_edge_and_centred_formula(self):
        b=layout(tag(s('1'),s('2')),Options(display_mode=True,content_width=200))
        one,two=gs(b);self.near(b.width,200);self.near(one.x,95);self.near(two.x,190)

    def test_f12_leqno_pins_tag_left_without_shifting_centred_body(self):
        b=layout(tag(s('1'),s('2'),leqno=True),Options(display_mode=True,content_width=200,leqno=True))
        one,two=gs(b);self.near(one.x,95);self.near(two.x,0)

    def test_f13_fleqn_is_two_em_indent_with_right_tag(self):
        b=layout(tag(s('1'),s('2')),Options(display_mode=True,content_width=200,fleqn=True))
        one,two=gs(b);self.near(one.x,2*EM);self.near(two.x,190)

    def test_f14_intrinsic_tag_container_is_finite_and_nonoverlapping(self):
        b=layout(tag(s('1'),s('2')),Options(display_mode=True))
        one,two=gs(b)
        self.assertGreaterEqual(b.width,two.x+.5*EM)
        self.assertGreater(two.x,one.x+.5*EM)

    def test_f15_automatic_numbers_respect_explicit_start_offset_and_false_rows(self):
        b=layout(array(row(s('a')),row(s('b')),row(s('x')),environment='align',tags=(True,False,True),col_specs=(('align','r',(0,'em'),(0,'em')),),hskip_before_after=False),Options(display_mode=True,content_width=300,equation_counter=3))
        caption=''.join(c.text for c in gs(b) if c.x>200)
        self.assertEqual(caption,'(4)(5)')

    def test_f16_manual_tag_does_not_increment_source_css_counter(self):
        b=layout(array(row(s('a')),row(s('b')),environment='align',tags=(g(s('X',mode='text')),True),hskip_before_after=False),Options(display_mode=True,content_width=300))
        self.assertEqual(''.join(c.text for c in gs(b) if c.x>200),'X(1)')

    def test_f17_all_nonumber_flags_draw_only_formula_content(self):
        b=layout(array(row(s('a')),row(s('b')),environment='align',tags=(False,False)),Options(display_mode=True,content_width=300))
        self.assertEqual(text(b),'ab')

    def test_f18_array_leqno_row_tags_are_left_aligned(self):
        b=layout(array(row(s('a')),row(s('b')),environment='align',tags=(g(s('1')),g(s('2'))),leqno=True),Options(display_mode=True,content_width=300,leqno=True))
        for c in gs(b):
            if c.text in '12':self.near(c.x,0)

    def test_f19_equation_counter_is_request_local_and_options_immutable(self):
        tree=array(row(s('a')),environment='equation',tags=(True,))
        options=Options(display_mode=True,equation_counter=8,content_width=300)
        first=layout(tree,options);second=layout(tree,options)
        self.assertEqual(text(first),text(second));self.assertIn('(9)',text(first));self.assertEqual(options.equation_counter,8)

    def test_f20_colspec_source_pregap_postgap_separator_order(self):
        specs=(('align','c',(2,'em'),(1,'em')),('separator','|'),('align','l',(3,'em'),(4,'em')))
        b=layout(array(row(s('1'),s('2')),col_specs=specs,hskip_before_after=True))
        self.near(b.width,11*EM)
        self.near(gs(b)[0].x,2*EM);self.near(gs(b)[1].x,6.5*EM)
        vertical=next(r for r in rs(b) if r.height>r.width)
        self.near(vertical.x,(3.5-.04/2)*EM)

    def test_f21_no_outer_hskip_suppresses_only_outer_colspec_gaps(self):
        specs=(('align','c',(2,'em'),(1,'em')),('separator','|'),('align','l',(3,'em'),(4,'em')))
        b=layout(array(row(s('1'),s('2')),col_specs=specs,hskip_before_after=False))
        self.near(b.width,5*EM);self.near(gs(b)[0].x,0);self.near(gs(b)[1].x,4.5*EM)

    def test_f22_explicit_arraystretch_and_jot_are_independent(self):
        rows=(row(s('1')),row(s('2')))
        for stretch,jot,pitch in ((2.,False,2.4),(1.,True,1.5),(1.,False,1.2)):
            b=layout(array(*rows,arraystretch=stretch,add_jot=jot))
            self.near(gs(b)[1].y-gs(b)[0].y,pitch*EM)

    def test_f23_multiple_hlines_use_source_quarter_em_separation(self):
        b=layout(array(row(s('1')),hlines=((0,'hline'),(0,'hline'))))
        horizontal=sorted((r for r in rs(b) if r.width>r.height),key=lambda r:r.y)
        self.assertEqual(len(horizontal),2);self.near(horizontal[1].y-horizontal[0].y,.25*EM)

    def test_f24_array_rules_honor_minimum_rule_thickness(self):
        b=layout(array(row(s('1'),s('2')),cols=('c','|','c'),hlines=((0,'hline'),)),Options(min_rule_thickness=.12))
        horizontal=next(r for r in rs(b) if r.width>r.height);vertical=next(r for r in rs(b) if r.height>r.width)
        self.near(horizontal.height,.12*EM);self.near(vertical.width,.12*EM)

    # units.ts absolute factors are TeX points, divided by ptPerEm=10.
    def test_f25_all_absolute_source_units_have_literal_pt_factors(self):
        factors={'pt':1,'mm':7227/2540,'cm':7227/254,'in':72.27,'bp':803/800,'pc':12,'dd':1238/1157,'cc':14856/1157,'nd':685/642,'nc':1370/107,'sp':1/65536,'px':803/800}
        for unit,factor in factors.items():
            for style in ('text','script','scriptscript'):
                with self.subTest(unit=unit,style=style):
                    b=layout(n('style',style,g(n('kern',width=(1,unit)))))
                    self.near(b.width,factor*EM/10)

    def test_f26_maxsize_caps_converted_dimensions_in_current_em(self):
        for style,size in (('text',20),('script',14),('scriptscript',10)):
            b=layout(n('style',style,g(n('kern',width=(100,'in')))),Options(max_size=1.))
            self.near(b.width,size)

    def test_f27_maxsize_does_not_absolute_value_negative_kern(self):
        b=layout(n('kern',width=(-.25,'em')),Options(max_size=.1))
        self.near(b.width,-.25*EM)
        zero=layout(n('rule',width=(10,'em'),height=(10,'em'),shift=(0,'em')),Options(max_size=0))
        self.assertEqual((zero.width,zero.total_height),(0.,0.))

    def test_f28_minrule_overline_retains_default_theta_kerns(self):
        b=layout(n('line','overline',g(s('x'))),Options(min_rule_thickness=.12))
        rule=rs(b)[0]
        self.near(rule.height,.12*EM)
        self.near(rule.y,-X_HEIGHT*EM-3*.04*EM-.12*EM)
        self.near(b.height,X_HEIGHT*EM+4*.04*EM+.12*EM)

    def test_f29_fraction_clearance_uses_actual_minimum_bar_width(self):
        # genfrac.ts sets ruleSpacing=rule.height, then clearance=1*ruleSpacing
        # in text style. minRuleThickness=.5em makes the bar and clearance 10px.
        b=layout(n('frac','',g(s('1')),g(s('2')),bar=True),Options(min_rule_thickness=.5))
        one,two=gs(b);rule=rs(b)[0]
        self.near(rule.height,10);self.near(rule.y,-10)
        self.near(one.y,-20);self.near(two.y,DIGIT_HEIGHT*14+10)

    def test_f30_minrule_radical_vinculum_is_real_source_path_geometry(self):
        b=layout(n('sqrt','',g(s('x')),g()),Options(min_rule_thickness=.12))
        path=ps(b)[0]
        segment=re.search(r'H400000v([\d.]+)',path.d)
        self.assertIsNotNone(segment)
        self.near(float(segment[1])*path.scale_y,.12*EM)

    def test_f31_css_mathnormal_locks_math_family_and_italic_not_weight(self):
        b=layout(html(s('x'),'font-family:KaTeX_SansSerif;font-style:normal;font-weight:bold'))
        glyph=gs(b)[0]
        self.assertEqual(glyph.font.split('-')[0],'Math');self.assertEqual(glyph.font_style,'italic');self.assertEqual(glyph.font_weight,'700')
        self.near(b.height,X_HEIGHT*EM)

    def test_f32_css_default_digit_inherits_all_three_font_axes(self):
        b=layout(html(s('1'),'font-family:KaTeX_SansSerif;font-style:italic;font-weight:bold'))
        glyph=gs(b)[0]
        self.assertEqual(glyph.font.split('-')[0],'SansSerif');self.assertEqual(glyph.font_style,'italic');self.assertEqual(glyph.font_weight,'700')
        self.near(b.height,DIGIT_HEIGHT*EM)

    def test_f33_css_mathrm_fixes_only_normal_shape(self):
        b=layout(html(n('font','mathrm',g(s('x'))),'font-family:KaTeX_SansSerif;font-style:italic;font-weight:bold'))
        glyph=gs(b)[0]
        self.assertEqual(glyph.font.split('-')[0],'SansSerif');self.assertEqual(glyph.font_style,'normal');self.assertEqual(glyph.font_weight,'700')

    def test_f34_css_mathbf_locks_main_and_bold_but_inherits_italic(self):
        b=layout(html(n('font','mathbf',g(s('x'))),'font-family:KaTeX_SansSerif;font-style:italic;font-weight:normal'))
        glyph=gs(b)[0]
        self.assertEqual(glyph.font.split('-')[0],'Main');self.assertEqual(glyph.font_style,'italic');self.assertEqual(glyph.font_weight,'700')

    def test_f35_css_mathit_locks_main_italic_but_inherits_bold(self):
        b=layout(html(n('font','mathit',g(s('x'))),'font-family:KaTeX_SansSerif;font-style:normal;font-weight:bold'))
        glyph=gs(b)[0]
        self.assertEqual(glyph.font.split('-')[0],'Main');self.assertEqual(glyph.font_style,'italic');self.assertEqual(glyph.font_weight,'700')

    def test_f36_css_boldsymbol_mathord_locks_all_font_axes(self):
        b=layout(html(n('font','boldsymbol',g(s('x'))),'font-family:KaTeX_SansSerif;font-style:normal;font-weight:normal'))
        glyph=gs(b)[0]
        self.assertEqual(glyph.font.split('-')[0],'Math');self.assertEqual(glyph.font_style,'italic');self.assertEqual(glyph.font_weight,'700')

    def test_f37_css_mathbb_locks_ams_family_only(self):
        b=layout(html(n('font','mathbb',g(s('R'))),'font-family:KaTeX_SansSerif;font-style:italic;font-weight:bold'))
        glyph=gs(b)[0]
        self.assertEqual(glyph.font.split('-')[0],'AMS');self.assertEqual(glyph.font_style,'italic');self.assertEqual(glyph.font_weight,'700')

    def test_f38_style_reset_font_removes_outer_tex_alphabet_not_outer_color(self):
        b=layout(n('color','#b40000',g(n('font','mathbf',g(n('style','text',g(s('x')),reset_font=True))))))
        self.assertEqual(gs(b)[0].font,'Math-Italic');self.assertEqual(gs(b)[0].color,'#b40000')

    def test_f39_textnormal_changes_family_without_resetting_source_weight(self):
        b=layout(n('text','textsf',g(n('text','textbf',g(n('text','textnormal',g(s('A',mode='text'))))))))
        self.assertEqual(gs(b)[0].font,'Main-Bold')

    def test_f40_missing_mathbb_lowercase_uses_source_makeord_mathitalic_fallback(self):
        b=layout(n('font','mathbb',g(s('a'))))
        self.assertEqual(gs(b)[0].font,'Math-Italic');self.near(b.height,.43056*EM)

    def test_f41_mathsym_ignores_mathbf_alphabet_but_honors_boldsymbol(self):
        plain=layout(n('font','mathbf',g(s('+','mbin'))));bold=layout(n('font','boldsymbol',g(s('+','mbin'))))
        self.assertEqual(gs(plain)[0].font,'Main-Regular');self.assertEqual(gs(bold)[0].font,'Main-Bold')

    def test_f42_unicode_extra_map_retains_source_vertical_metrics_not_native_ascent(self):
        measured={'width':47.5,'height':99.,'depth':98.,'font':'system:serif|normal|400','font_resource':None,'italic':0.,'skew':0.}
        with patch('py_katex.canvas.measure_fallback',return_value=measured) as measure:
            b=layout(n('text','text',g(s('А',mode='text'),s('Б',mode='text'))))
        self.near(b.width,47.5);self.near(b.height,.68333*EM);self.near(b.depth,0)
        self.assertEqual(measure.call_count,1);self.assertEqual(measure.call_args.args[0],'АБ')

    def test_f43_unicode_supported_script_retains_m_estimate_and_whole_run(self):
        measured={'width':47.5,'height':99.,'depth':98.,'font':'system:serif|normal|400','font_resource':None,'italic':0.,'skew':0.}
        for value in ('中文','नमस्ते','العربية العربية'):
            with self.subTest(value=value),patch('py_katex.canvas.measure_fallback',return_value=measured) as measure:
                nodes=[n('space','space',width=1/3) if char==' ' else s(char,mode='text') for char in value]
                b=layout(n('text','text',g(*nodes)))
                self.assertEqual(measure.call_count,1);self.assertEqual(measure.call_args.args[0],value)
                self.assertEqual(len(gs(b)),1);self.assertEqual(gs(b)[0].text,value)
                if value!='العربية العربية':self.near(b.height,.68333*EM)

    def test_f44_real_unicode_run_uses_explicit_font_resource_and_single_native_glyph(self):
        font=FilePath(__file__).resolve().parents[1]/'src/py_katex/data/fonts/KaTeX_Math-Italic.ttf'
        resource=FontResource('SourceGreekFallback',font.read_bytes(),scripts=('greek',),style='italic')
        b=layout(n('text','text',g(*(s(char,mode='text') for char in 'αβγ'))),Options(fallback_fonts=(resource,)))
        self.assertEqual(len(gs(b)),1);self.assertEqual(gs(b)[0].text,'αβγ');self.assertEqual(gs(b)[0].font_resource,resource)
        self.assertGreater(b.width,0)

    def test_f45_bundled_text_run_advance_matches_independent_public_canvas_shaping(self):
        from py_skia_canvas import Canvas,FontLibrary
        font=FilePath(__file__).resolve().parents[1]/'src/py_katex/data/fonts/KaTeX_Main-Regular.ttf'
        FontLibrary.use('IndependentSourceMain',str(font))
        canvas=Canvas(1,1);canvas.gpu=False;context=canvas.getContext('2d')
        context.font='normal 400 20px "IndependentSourceMain"';context.textAlign='left';context.textBaseline='alphabetic'
        expected=context.measureText('AV').width
        b=layout(n('text','text',g(s('A',mode='text'),s('V',mode='text'))))
        self.assertEqual(len(gs(b)),1);self.assertEqual(gs(b)[0].text,'AV')
        self.near(b.width,expected);self.near(b.height,.68333*EM)

    def test_f46_text_color_boundary_is_preserved_across_combined_runs(self):
        b=layout(n('text','text',g(n('color','#cc0000',g(s('A',mode='text'),s('V',mode='text'))),s('A',mode='text'),s('V',mode='text'))))
        self.assertEqual([(c.text,c.color) for c in gs(b)],[('AV','#cc0000'),('AV','#000000')])

    def test_f47_all_eight_style_pairs_retain_source_metric_sizes(self):
        for style,scale in (('display',1.),('text',1.),('script',.7),('scriptscript',.5)):
            for cramped in (False,True):
                b=layout(n('style',style,g(s('x')),cramped=cramped))
                self.near(gs(b)[0].size,scale*EM);self.near(b.height,X_HEIGHT*scale*EM)

    def test_f48_verb_enters_textstyle_inside_script_unlike_ordinary_texttt(self):
        for verb,size in ((False,14.),(True,20.)):
            b=layout(n('style','script',g(n('text','texttt',g(s('x',mode='text')),verb=verb))))
            self.near(gs(b)[0].size,size);self.assertEqual(gs(b)[0].font,'Typewriter-Regular')

    def test_f49_explicit_empty_root_index_is_not_absent_index(self):
        absent=layout(n('sqrt','',g(s('x')),g(),index_provided=False))
        explicit=layout(n('sqrt','',g(s('x')),g(),index_provided=True))
        self.near(explicit.width-absent.width,-5*EM/18)
        self.near(gs(explicit)[0].x-gs(absent)[0].x,-5*EM/18)

    def test_f50_right_delimiter_captures_scoped_source_current_color(self):
        b=layout(n('delimiters','',g(s('x')),left='(',right=')',middle=(),right_color='#c00000'))
        close=next(c for c in gs(b) if c.text==')');open_=next(c for c in gs(b) if c.text=='(')
        self.assertEqual(close.color,'#c00000');self.assertEqual(open_.color,'#000000')

    def test_f51_group_and_moustache_delimiters_have_source_stack_parts(self):
        for char,top,bottom in (('⟮','⎧','⎩'),('⟯','⎫','⎭'),('⎰','⎧','⎭'),('⎱','⎫','⎩')):
            b=layout(n('delimiters','',g(n('rule',width=(1,'em'),height=(5,'em'),shift=(0,'em'))),left=char,right='.',middle=()))
            visible=text(b);self.assertIn(top,visible);self.assertIn(bottom,visible)
            self.assertGreater(b.total_height,100)

    def test_f52_never_stacked_angle_delimiter_caps_at_source_size_four(self):
        b=layout(n('delimiters','',g(n('rule',width=(1,'em'),height=(5,'em'),shift=(0,'em'))),left='⟨',right='⟩',middle=()))
        self.assertEqual([c.font for c in gs(b)],['Size4-Regular','Size4-Regular'])

    def test_f53_character_accent_delegates_script_shift_to_nucleus(self):
        plain=layout(sub_sup(s('x'),g(s('1'))))
        accented=layout(sub_sup(n('accent','hat',g(s('x')),shifty=True),g(s('1'))))
        self.near(next(c.y for c in gs(plain) if c.text=='1'),-.363*EM)
        self.near(next(c.y for c in gs(accented) if c.text=='1'),-.363*EM)
        self.assertIn('^',text(accented))

    def test_f54_utilde_has_source_twelve_hundredths_em_gap_below(self):
        b=layout(n('accent','utilde',g(s('x')),shifty=False))
        self.assertEqual(len(ps(b)),1);self.near(ps(b)[0].y,.12*EM)

    def test_f55_overbrace_with_both_scripts_does_not_delegate_per_not_sub_flag(self):
        # supsub.ts uses const isSup = !group.sub. Both scripts mean false,
        # so an overbrace takes ordinary side scripts, retaining both.
        base=n('overunder','overbrace',g(s('x'),s('x')),g())
        b=layout(sub_sup(base,g(s('n')),g(s('m'))))
        self.assertIn('n',text(b));self.assertIn('m',text(b))
        self.assertGreaterEqual(next(c.x for c in gs(b) if c.text=='n'),1.6*EM)
        self.assertGreaterEqual(next(c.x for c in gs(b) if c.text=='m'),1.6*EM)

    def test_f56_underbrace_both_scripts_preserves_fixed_source_delegation_quirk(self):
        # The same !group.sub flag delegates an underbrace; horizBrace then
        # chooses grp.sup and places that note below. Its opposite note is
        # not painted by the fixed source. Do not invent additional content.
        base=n('overunder','underbrace',g(s('x'),s('x')),g())
        b=layout(sub_sup(base,g(s('n')),g(s('m'))))
        self.assertIn('n',text(b));self.assertNotIn('m',text(b))
        self.assertGreater(next(c.y for c in gs(b) if c.text=='n'),0)

    def test_f57_operatorname_always_handle_flag_in_display_does_not_require_limits(self):
        op=n('operator','',g(s('L',mode='text')),roman=True,limits=False,always_handle_supsub=True,command='operatornamewithlimits')
        b=layout(sub_sup(op,sub=g(s('i'))),Options(display_mode=True))
        base,sub=gs(b);self.assertLess(sub.x,base.x+.625*EM)
        self.assertGreater(sub.y,base.y)

    def test_f58_operator_always_handle_true_forces_limits_in_textstyle(self):
        op=n('operator','∑',symbol=True,limits=True,always_handle_supsub=True)
        b=layout(sub_sup(op,g(s('n'))))
        symbol,note=gs(b);self.assertLess(note.x,symbol.x+1.05556*EM)
        self.assertLess(note.y,-.75*EM)

    def test_f59_suppress_base_shift_is_source_flag_not_ignored(self):
        normal=layout(n('operator','∑',symbol=True),Options(display_mode=True))
        suppressed=layout(n('operator','∑',symbol=True,suppress_base_shift=True),Options(display_mode=True))
        self.near(gs(normal)[0].y,((1.05-.55001)/2-.25)*EM)
        self.near(gs(suppressed)[0].y,0)

    def test_f60_size_style_fraction_rule_composition_uses_source_size_map(self):
        frac=n('frac','',g(s('1')),g(s('2')),bar=True)
        b=layout(n('style','script',g(n('size','Huge',g(frac)))),Options(min_rule_thickness=.12))
        self.assertEqual([c.size for c in gs(b)],[2.074*EM,2.074*EM])
        self.near(rs(b)[0].height,.12*2.488*EM)

    def test_f61_unsupported_command_stays_visible_and_diagnostic_through_composition(self):
        unsupported=n('unsupported',r'\href',color='#cc0000',message='Untrusted command',code='UNTRUSTED_COMMAND',rejected=True)
        b=layout(n('frac','',g(unsupported),g(s('1')),bar=True))
        self.assertIn(r'\href',text(b));self.assertTrue(any(d.code=='UNTRUSTED_COMMAND' and d.severity=='warning' for d in b.diagnostics))
        self.assertTrue(all(c.color=='#cc0000' for c in gs(b) if c.text!='1'))

    def test_f62_error_box_is_visible_raw_tex_and_error_diagnostic_not_success_stub(self):
        b=layout(n('error',r'\unknown{a}',message='Unknown command',code='UNKNOWN_COMMAND'))
        self.assertEqual(text(b),r'\unknown{a}')
        self.assertEqual(b.diagnostics,(Diagnostic('Unknown command',0,'UNKNOWN_COMMAND','error'),))

    def test_f63_display_host_width_is_logical_and_keeps_unbreakable_overflow_commands(self):
        b=layout(g(*(s('x') for _ in range(20))),Options(display_mode=True,content_width=20))
        self.near(b.width,20)
        self.assertLess(min(c.x for c in gs(b)),0)
        self.assertGreater(max(c.x+X_WIDTH*EM for c in gs(b)),20)
        self.assertFalse(any(isinstance(c,CommandGroup) and c.clip is not None for c in b.commands))

    def test_f64_source_geometry_guard_catches_dropped_tag_and_compressed_cd_head(self):
        def check_tag(box):
            caption=[c for c in gs(box) if c.text=='9'];self.assertEqual(len(caption),1);self.near(caption[0].x,190)
        tagged=layout(tag(s('1'),s('9')),Options(display_mode=True,content_width=200));check_tag(tagged)
        bad=replace(tagged,commands=tuple(c for c in tagged.commands if not isinstance(c,Glyph) or c.text!='9'))
        with self.assertRaises(AssertionError):check_tag(bad)
        arrow=layout(n('cdarrow','>',g(s('1')),g()))
        def check_head(box):
            self.assertTrue(ps(box));self.near(ps(box)[0].scale_x,.02);self.assertIsNotNone(ps(box)[0].clip)
        check_head(arrow)
        bad=replace(arrow,commands=tuple(replace(c,scale_x=.0001) if isinstance(c,Path) else c for c in arrow.commands))
        with self.assertRaises(AssertionError):check_head(bad)

    def test_f65_regular_source_space_uses_actual_face_metric(self):
        for wrapper,width in ((None,.25),('texttt',.525)):
            node=n('space','space',width=1/3)
            if wrapper:node=n('text',wrapper,g(node))
            b=layout(node);self.near(b.width,width*EM)

    def test_f66_public_thinspace_and_quad_macro_keep_source_units_in_script(self):
        tree=parse(r'\scriptstyle x\,x\quad x')
        b=layout(tree);letters=[c for c in gs(b) if c.text=='x']
        self.assertEqual(len(letters),3)
        self.near(letters[1].x-letters[0].x,X_WIDTH*14+3*1.171*14/18)
        self.near(letters[2].x-letters[1].x,X_WIDTH*14+1*EM)

    def test_f67_allowbreak_nobreak_and_root_newline_are_distinct(self):
        def formula(control):return g(s('x'),s('+','mbin'),n('space',control,break_kind=control,width=0),s('a'),s('+','mbin'),s('b'))
        allowed=layout(formula('allowbreak'),Options(content_width=30));blocked=layout(formula('nobreak'),Options(content_width=30))
        self.assertGreater(max(c.y for c in gs(allowed)),0)
        x,a=[next(c for c in gs(blocked) if c.text==ch) for ch in ('x','a')]
        self.near(x.y,a.y)
        newline=layout(g(s('x'),n('linebreak',gap=(1,'em')),s('a')))
        self.near(gs(newline)[1].x,0);self.assertGreaterEqual(gs(newline)[1].y,2.2*EM)

    def test_f68_hbox_prevents_soft_break_but_explicit_newline_remains_root_control(self):
        body=n('group','',s('x'),s('+','mbin'),s('a'),reset_font=True,no_break=True)
        b=layout(g(body,s('+','mbin'),s('b')),Options(content_width=25))
        x=next(c for c in gs(b) if c.text=='x');a=next(c for c in gs(b) if c.text=='a')
        self.near(x.y,a.y)

    def test_f69_pmb_shadow_blurs_text_but_does_not_duplicate_fraction_rule(self):
        b=layout(n('pmb','',g(n('frac','',g(s('1')),g(s('2')),bar=True))))
        shadow=next(c for c in b.commands if isinstance(c,CommandGroup))
        self.assertEqual(shadow.filter,'blur(0.04px)')
        self.assertTrue(any(isinstance(c,Glyph) for c in shadow.commands))
        self.assertFalse(any(isinstance(c,(Rule,Path)) for c in shadow.commands))
        self.assertEqual(len([c for c in b.commands if isinstance(c,Rule)]),1)

    def test_f70_fleqn_leqno_tag_left_is_relative_to_padded_html_content_box(self):
        # katex.scss: fleqn adds 2em padding on .katex; its .katex-html is
        # the positioned containing block. leqno left:0 is therefore 2em
        # from the unpadded display host, not the host's x=0.
        b=layout(tag(s('1'),s('2'),leqno=True),Options(display_mode=True,content_width=200,fleqn=True,leqno=True))
        one,two=gs(b);self.near(one.x,2*EM);self.near(two.x,2*EM)


class FullLayoutRepairSourceTests(unittest.TestCase):
    def test_r01_internal_dotless_i_uses_source_math_metric_in_all_math_fonts(self):
        # symbols.ts deliberately registers the PUA only through @imath;
        # makeOrd must preserve that source token when choosing mathord.
        for command in ('mathnormal','mathbf','mathcal','mathfrak','mathrm','mathsf','mathscr','mathtt'):
            with self.subTest(command=command):
                b=layout(parse('\\'+command+r'{\@imath}'))
                glyph=gs(b)[0]
                self.assertEqual(glyph.text,'\ue131')
                self.assertIn(glyph.font,('Math-Italic','Math-BoldItalic'))
                self.assertAlmostEqual(b.width,(.39352 if glyph.font=='Math-BoldItalic' else .32246)*EM)

    def test_r02_blackboard_digits_and_nonstretch_accent_fall_back_to_main(self):
        # buildCommon.makeOrd default textord fallback, not AMS nor native.
        self.assertEqual(gs(layout(parse(r'\mathbb{2}')))[0].font,'Main-Regular')
        b=layout(parse(r'\mathbb{\hat I}'))
        self.assertEqual(gs(b)[-1].font,'Main-Regular')
        self.assertEqual(gs(b)[-1].text,'^')

    def test_r03_registered_missing_symbol_obeys_source_strict_policy(self):
        # symbols.ts intentionally lists origof absent from bundled metrics;
        # makeSymbol must report symbolNotInFont before native glyph lookup.
        with self.assertRaisesRegex(ParseError,'symbolNotInFont'):
            layout(parse(r'\origof'),Options(strict='error'))

    def test_r04_text_circumflex_is_different_source_glyph_from_math_hat(self):
        self.assertEqual(gs(layout(parse(r'\text{\^A}')))[-1].text,'\u02c6')
        self.assertEqual(gs(layout(parse(r'\hat A')))[-1].text,'^')

    def test_r05_rule_css_content_pixel_does_not_change_logical_tex_extents(self):
        b=layout(n('rule',width=(3,'pt'),height=(2,'sp'),shift=(0,'pt')))
        self.assertAlmostEqual(b.height,2/65536*2)
        self.assertEqual(b.depth,0)
        self.assertAlmostEqual(rs(b)[0].height,1+2/65536*2)
        self.assertAlmostEqual(rs(b)[0].y,-1-2/65536*2)

    def test_r06_emph_toggles_are_equivalent_to_source_textit_textup_pairs(self):
        # katex-spec.ts source buildLike cases, four enclosing scopes.
        for outer in ('','text','textup','textit'):
            left=r'\emph{foo \emph{bar}}'
            right=(r'\textup{foo \textit{bar}}' if outer=='textit' else r'\textit{foo \textup{bar}}')
            if outer:left='\\'+outer+'{'+left+'}';right='\\'+outer+'{'+right+'}'
            a=layout(parse(left));b=layout(parse(right))
            self.assertEqual((a.width,a.height,a.depth,a.commands),(b.width,b.height,b.depth,b.commands))

    def test_r07_combining_math_accents_equal_explicit_source_commands(self):
        # katex-spec.ts Unicode accents / combining characters parseLike.
        for left,right in (('A\u0301',r'\acute A'),('\u0106',r'\acute C')):
            a=layout(parse(left,strict=False));b=layout(parse(right,strict=False))
            self.assertEqual((a.width,a.height,a.depth,a.commands),(b.width,b.height,b.depth,b.commands))

    def test_r08_typewriter_deconstructs_text_ligatures_before_source_lookup(self):
        # buildCommon.ts215: makeOrd deconstructs absent Typewriter ligatures.
        b=layout(parse(r"\texttt{-- --- `` ''}"))
        self.assertEqual(''.join(text(b).split()),'-----\u2018\u2018\u2019\u2019')
        self.assertTrue(all(c.font=='Typewriter-Regular' for c in gs(b)))
        self.assertTrue(all('system:' not in c.font for c in gs(b)))

    def test_r09_verb_looks_up_each_raw_quote_before_combining_chars(self):
        # functions/verb.ts: makeSymbol(c, Typewriter) applies symbols.ts
        # substitutions to backtick/quote, but does not form dash ligatures.
        b=layout(parse(r"\verb|``---''~|"))
        self.assertEqual(text(b),'\u2018\u2018---\u2019\u2019~')
        self.assertTrue(all(c.font=='Typewriter-Regular' for c in gs(b)))

    def test_r10_fallback_run_reports_missing_source_metrics_before_native_measurement(self):
        # fontMetrics has no estimate for U270C. Parser unknownSymbol and
        # buildCommon.makeSymbol symbolNotInFont are separate source reports.
        # Stub only the external native measurement boundary for this policy
        # test; real platform emoji rendering is covered by core corpus/C.
        measured=dict(width=12,height=14,depth=2,font='system:serif',font_resource=None,italic=0,skew=0)
        with patch('py_katex.canvas.measure_fallback',return_value=measured):
            for tex in ('\u270c',r'\text{'+ '\u270c'+'}'):
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter('always')
                    layout(parse(tex,strict='warn'),Options(strict='warn'))
                codes=[re.search(r'\[([^\]]+)\]',str(w.message)).group(1) for w in captured]
                self.assertEqual(codes,['unknownSymbol','symbolNotInFont'])
            with self.assertRaisesRegex(ParseError,'symbolNotInFont'):
                layout(parse('\u270c',strict=False),Options(strict='error'))


class HtmlInlineCellSourceTests(unittest.TestCase):
    # Independent fixed-browser probe: Run170615Z-9072a0d0, cell-0..6 and
    # cell-nested. Literal hhea Main903/-272 and Sans750/-250 at1000upem.
    # These assert enclosing CSS font cells, not inner glyph ink metrics.
    def frame(self,box):return next(r for r in rs(box) if r.color=='yellow')
    def htmlbox(self,style,body='x'):
        return layout(parse(r'\htmlStyle{'+style+'}{'+body+'}',trust=True),Options(font_size=40,trust=True))

    def test_h01_inline_padding_border_background_use_outer_main_cell(self):
        b=self.htmlbox('background:yellow;border:2px solid blue;padding:6px;color:red;')
        frame=self.frame(b)
        self.assertEqual((frame.y,frame.height),(-44,63))
        self.assertAlmostEqual(frame.width,22.8612+16,places=4)
        # Padding expands paint above/below the unchanged baseline.
        outer=b.commands[0];body=next(c for c in outer.commands if isinstance(c,CommandGroup))
        self.assertEqual((body.x,body.y),(8,0))

    def test_h02_nonreplaced_inline_ignores_width_height_and_lineheight_for_paint_cell(self):
        for style in ('width:100px;height:100px;','line-height:2;','line-height:12px;','min-width:90px;min-height:100px;max-height:1px;'):
            with self.subTest(style=style):
                b=self.htmlbox('background:yellow;'+style)
                frame=self.frame(b)
                self.assertEqual((frame.y,frame.height),(-36,47))
                self.assertAlmostEqual(frame.width,22.8612,places=4)

    def test_h03_inlineblock_uses_own_lineheight_and_honors_explicit_dimensions(self):
        b=self.htmlbox('display:inline-block;background:yellow;line-height:2;padding:6px;border:2px solid blue;')
        self.assertEqual(self.frame(b).height,96)  # 80px line + 16px sides.
        c=self.htmlbox('display:inline-block;background:yellow;width:100px;height:100px;')
        self.assertEqual((self.frame(c).width,self.frame(c).height),(100,100))

    def test_h04_font_size_and_nested_outer_family_have_source_cells(self):
        b=self.htmlbox('font-size:20px;background:yellow;padding:3px;border:1px solid blue;')
        self.assertEqual((self.frame(b).y,self.frame(b).height),(-22,31))
        nested=r'\htmlStyle{background:yellow;padding:6px;border:2px solid blue;}{x}'
        b=self.htmlbox('font-family:KaTeX_SansSerif;font-size:30px;',nested)
        self.assertEqual((self.frame(b).y,self.frame(b).height),(-31,47))

    def test_h05_plain_inline_keeps_outer_cell_and_baseline_without_background(self):
        b=self.htmlbox('padding:0px;')
        # html.ts makeSpan preserves its child's TeX metrics; an invisible
        # enclosing font cell must not inflate fraction/script geometry.
        self.assertAlmostEqual(b.height,X_HEIGHT*40)
        self.assertEqual(b.depth,0)
        self.assertFalse(rs(b))
        self.assertEqual(b.commands[0].commands[0].y,0)

    def test_h06_nested_inlineblock_inherits_absolute_and_unitless_lineheight(self):
        inner=r'\htmlStyle{display:inline-block;background:yellow;font-size:20px;}{x}'
        # Absolute40px stays40 through a smaller child; unitless2 scales to40.
        for line in ('40px','2'):
            b=self.htmlbox('line-height:'+line+';',inner)
            self.assertEqual(self.frame(b).height,40)
        b=self.htmlbox('line-height:2;',r'\htmlStyle{display:inline-block;background:yellow;}{x}')
        self.assertEqual(self.frame(b).height,80)

    def test_h07_real_pixels_match_source_frame_and_baseline_and_reject_shifted_body(self):
        from io import BytesIO
        from PIL import Image
        from py_katex.canvas import render_box
        b=self.htmlbox('background:yellow;border:2px solid blue;padding:6px;color:red;')
        result=render_box(b,backend='cpu',background='white')
        im=Image.open(BytesIO(result.data)).convert('RGB')
        def bbox(image,predicate):
            points=[(x,y) for y in range(image.height) for x in range(image.width) if predicate(image.getpixel((x,y)))]
            self.assertTrue(points)
            return min(x for x,y in points),min(y for x,y in points),max(x for x,y in points)+1,max(y for x,y in points)+1
        red=lambda p:p[0]>160 and p[1]<100 and p[2]<100
        blue=lambda p:p[2]>160 and p[0]<100 and p[1]<100
        def guard(image):
            r=bbox(image,red);f=bbox(image,blue)
            # Source actual PNG blue height63, red top gap26, bottom gap19.
            self.assertEqual(f[3]-f[1],63)
            self.assertAlmostEqual(r[1]-f[1],26,delta=1)
            self.assertAlmostEqual(f[3]-r[3],19,delta=1)
            self.assertGreater(r[0],f[0]+6);self.assertLess(r[2],f[2]-6)
        guard(im)
        # Independent negative control emulates the rejected double-padding
        # baseline shift; never uses another backend font matcher as oracle.
        bad=im.copy();points=[(x,y,im.getpixel((x,y))) for y in range(im.height) for x in range(im.width) if red(im.getpixel((x,y)))]
        for x,y,pixel in points:bad.putpixel((x,y),(255,255,0))
        for x,y,pixel in points:
            if y+8<bad.height:bad.putpixel((x,y+8),pixel)
        with self.assertRaises(AssertionError):guard(bad)


if __name__=='__main__':unittest.main()
