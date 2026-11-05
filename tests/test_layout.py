"""Independent KaTeX 0.18.11 literal-metric and TeX-rule assertions.

P2 authorship: no expected value is obtained from Python layout helpers or a
candidate render. The constants below are transcribed from the fixed upstream
fontMetricsData.js; equations cite their upstream builder beside each group.
"""
from dataclasses import replace
import math
import unittest

from py_katex.layout import layout
from py_katex.model import CommandGroup, Glyph, MathBox, Node, Options, ParseError, Path, Rule


def n(kind, value='', *children, **attrs):
    return Node(kind,value,tuple(children),tuple(attrs.items()))


def sym(value, atom='mord', mode='math', **attrs):
    return n('symbol',value,atom=atom,mode=mode,font='main',**attrs)


def group(*children): return n('group','',*children)
def scripts(base,sup=None,sub=None,**attrs):
    return n('scripts','',base,sup or group(),sub or group(),limits=attrs.get('limits'))
def glyphs(box): return [c for c in box.commands if isinstance(c,Glyph)]
def rules(box): return [c for c in box.commands if isinstance(c,Rule)]
def paths(box): return [c for c in box.commands if isinstance(c,Path)]


# fontMetricsData.js: [depth,height,italic,skew,width], in source em.
MI = {'x':(0,.43056,0,.02778,.57153),'y':(.19444,.43056,.03588,.05556,.49028),
      'f':(.19444,.69444,.10764,.16667,.48959),'i':(0,.65952,0,0,.34451),
      'j':(.19444,.65952,.05724,0,.41181),'a':(0,.43056,0,0,.52859),
      'b':(0,.69444,0,0,.42917),'n':(0,.43056,0,0,.60023)}
EM=20.


class LayoutSourceTests(unittest.TestCase):
    def assertNear(self, actual, expected): self.assertAlmostEqual(actual,expected,places=7)

    def test_l01_source_glyph_tuple_and_signed_relation_depth(self):
        b=layout(sym('f'))
        d,h,it,sk,w=MI['f']
        for actual,expected in zip((b.depth,b.height,b.italic,b.skew,b.width),(d*EM,h*EM,it*EM,sk*EM,w*EM)):
            self.assertNear(actual,expected)
        self.assertEqual(glyphs(b)[0].font,'Math-Italic')
        eq=layout(sym('=','mrel'))
        self.assertNear(eq.depth,-.13313*EM)
        self.assertNear(eq.height,.36687*EM)

    def test_l02_all_eight_style_sizes(self):
        # Style.ts id pairs share size; Options.ts normalsize [6,3,1].
        for style,scale in (('display',1),('text',1),('script',.7),('scriptscript',.5)):
            for cramped in (False,True):
                with self.subTest(style=style,cramped=cramped):
                    b=layout(n('style',style,group(sym('x')),cramped=cramped))
                    self.assertNear(glyphs(b)[0].size,EM*scale)
                    self.assertNear(b.height,MI['x'][1]*EM*scale)

    def test_l03_source_size_table_and_script_size_mapping(self):
        for command,scale,script_scale in (('tiny',.5,.5),('small',.9,.6),('normalsize',1,.7),('Large',1.44,1),('Huge',2.488,2.074)):
            with self.subTest(command=command):
                b=layout(n('size',command,group(sym('x'),scripts(sym('a'),group(sym('1'))))))
                gs=glyphs(b)
                self.assertNear(gs[0].size,EM*scale)
                self.assertNear(gs[-1].size,EM*script_scale)

    def test_l04_mathchoice_uses_style_not_display_option_alone(self):
        choice=n('mathchoice','',*(group(sym(c)) for c in '1234'))
        for index,style in enumerate(('display','text','script','scriptscript')):
            b=layout(n('style',style,group(choice)))
            self.assertEqual([g.text for g in glyphs(b)],[str(index+1)])

    def test_l05_bin_glue_is_four_mu_on_each_side(self):
        b=layout(group(sym('x'),sym('+','mbin'),sym('x')))
        x,plus,last=glyphs(b);glue=4*EM/18
        self.assertNear(plus.x,MI['x'][4]*EM+glue)
        self.assertNear(last.x,plus.x+.77778*EM+glue)

    def test_l06_relation_glue_five_mu_and_operator_glue_three_mu(self):
        relation=layout(group(sym('x'),sym('=','mrel'),sym('x')))
        self.assertNear(glyphs(relation)[1].x,MI['x'][4]*EM+5*EM/18)
        operator=layout(group(sym('x'),n('operator','sin',symbol=False,limits=False)))
        self.assertNear(glyphs(operator)[1].x,MI['x'][4]*EM+3*EM/18)

    def test_l07_binary_cancellation_at_expression_boundaries(self):
        for children in ((sym('+','mbin'),sym('x')),(sym('x'),sym('+','mbin'))):
            b=layout(group(*children));a,z=glyphs(b)
            expected=.77778*EM if a.text=='+' else MI['x'][4]*EM
            self.assertNear(z.x,expected)

    def test_l08_binary_cancellation_next_to_open_rel_close(self):
        for children in ((sym('(','mopen'),sym('+','mbin'),sym('x')),
                         (sym('x'),sym('+','mbin'),sym('=','mrel')),
                         (sym('x'),sym('+','mbin'),sym(')','mclose'))):
            with self.subTest(children=tuple(c.value for c in children)):
                b=layout(group(*children));gs=glyphs(b)
                if children[0].value=='(':self.assertNear(gs[1].x,.38889*EM)
                else:self.assertNear(gs[1].x,MI['x'][4]*EM)

    def test_l09_tight_style_omits_binary_and_relation_glue(self):
        b=layout(n('style','script',group(sym('x'),sym('+','mbin'),sym('x'),sym('=','mrel'),sym('a'))))
        gs=glyphs(b);e=.7*EM
        self.assertNear(gs[1].x,MI['x'][4]*e)
        self.assertNear(gs[2].x,(MI['x'][4]+.77778)*e)

    def test_l10_color_fragment_does_not_cancel_bin_at_fragment_boundary(self):
        b=layout(group(n('color','#cc0000',group(sym('x'),sym('+','mbin'))),sym('x')))
        gs=glyphs(b)
        self.assertNear(gs[1].x,MI['x'][4]*EM+4*EM/18)
        self.assertNear(gs[2].x,gs[1].x+.77778*EM+4*EM/18)
        self.assertEqual([g.color for g in gs],['#cc0000','#cc0000','#000000'])

    def test_l11_negative_kern_and_absolute_units(self):
        b=layout(group(sym('x'),n('kern',width=(-2,'pt')),sym('a')))
        self.assertNear(glyphs(b)[1].x,MI['x'][4]*EM-4)
        small=layout(n('style','script',group(n('kern',width=(1,'pt')),sym('x'))))
        self.assertNear(glyphs(small)[0].x,2.)

    def test_l12_relative_em_ex_and_mu_follow_source_unit_rules(self):
        # units.ts: em/ex use text style even inside a script; mu follows quad.
        for dim,expected in (((1,'em'),20.),((1,'ex'),.431*20),((18,'mu'),1.171*14)):
            b=layout(n('style','script',group(n('kern',width=dim),sym('x'))))
            self.assertNear(glyphs(b)[0].x,expected)

    def test_l13_text_fraction_baselines_axis_and_thickness(self):
        b=layout(n('frac','',group(sym('1')),group(sym('2')),bar=True,style='auto'))
        a,z=glyphs(b);bar=rules(b)[0]
        self.assertNear(a.size,14);self.assertNear(z.size,14)
        self.assertNear(a.y,-.394*EM);self.assertNear(z.y,.345*EM)
        self.assertNear(bar.y,-(.25+.04/2)*EM);self.assertNear(bar.height,.04*EM)
        self.assertNear(bar.width,.5*14)
        self.assertNear(b.width,.5*14+2*.12*EM)

    def test_l14_display_fraction_uses_text_children(self):
        b=layout(n('frac','',group(sym('1')),group(sym('2')),bar=True),Options(display_mode=True))
        a,z=glyphs(b)
        self.assertNear(a.size,20);self.assertNear(z.size,20)
        self.assertNear(a.y,-.677*EM);self.assertNear(z.y,.686*EM)

    def test_l15_barless_fraction_has_no_rule_and_separated_children(self):
        b=layout(n('frac','',group(sym('1')),group(sym('2')),bar=False))
        a,z=glyphs(b);self.assertEqual(rules(b),[])
        self.assertNear(a.y,-.444*EM);self.assertNear(z.y,.345*EM)
        self.assertGreaterEqual(z.y-.64444*z.size-(a.y),3*.04*EM)

    def test_l16_fraction_custom_thickness_and_clearances(self):
        b=layout(n('frac','',group(sym('y')),group(sym('b')),bar=True,thickness=(2,'pt')))
        a,z=glyphs(b);bar=rules(b)[0]
        self.assertNear(bar.height,4)
        self.assertNear(bar.y,-7)
        self.assertGreaterEqual(bar.y-(a.y+MI['y'][0]*a.size),.04*EM-1e-8)
        self.assertGreaterEqual(z.y-MI['b'][1]*z.size-(bar.y+bar.height),.04*EM-1e-8)

    def test_l17_continued_fraction_source_strut_and_right_null_delimiter(self):
        b=layout(n('frac','',group(sym('1')),group(sym('2')),bar=True,style='display',continued=True))
        self.assertNear(b.width,.5*EM+.12*EM)
        self.assertGreaterEqual(b.height,8.5*EM/10)

    def test_l18_single_superscript_shift_and_font_independent_space(self):
        b=layout(scripts(sym('x'),group(sym('1'))))
        base,sup=glyphs(b)
        self.assertNear(sup.y,-.363*EM);self.assertNear(sup.size,.7*EM)
        self.assertNear(sup.x,MI['x'][4]*EM)
        self.assertNear(b.width,MI['x'][4]*EM+.5*.7*EM+.05*EM)

    def test_l19_single_subscript_does_not_follow_italic_correction(self):
        b=layout(scripts(sym('f'),sub=group(sym('i'))))
        base,sub=glyphs(b)
        self.assertNear(sub.x,MI['f'][4]*EM)
        self.assertNear(sub.y,max(.15*EM,MI['i'][1]*14-.8*.431*EM))

    def test_l20_simultaneous_scripts_follow_four_rule_gap_and_psi(self):
        # supsub.ts rule18e: psi correction belongs inside the gap-deficit branch.
        b=layout(scripts(sym('x'),group(sym('j')),group(sym('i'))))
        gs=glyphs(b);sup=next(g for g in gs if g.text=='j');sub=next(g for g in gs if g.text=='i')
        up=max(.363*EM,MI['j'][0]*14+.25*.431*EM);down=.247*EM
        if (up-MI['j'][0]*14)-(MI['i'][1]*14-down)<4*.04*EM:
            down=4*.04*EM-(up-MI['j'][0]*14)+MI['i'][1]*14
            psi=.8*.431*EM-(up-MI['j'][0]*14)
            if psi>0:up+=psi;down-=psi
        self.assertNear(sup.y,-up);self.assertNear(sub.y,down)

    def test_l21_cramped_scripts_do_not_apply_psi_without_gap_deficit(self):
        b=layout(n('style','text',group(scripts(sym('x'),group(sym('a')),group(sym('a')))),cramped=True))
        gs=glyphs(b);sup=min(gs,key=lambda g:g.y);sub=max(gs,key=lambda g:g.y)
        self.assertNear(sup.y,-.289*EM)
        self.assertNear(sub.y,.247*EM)

    def test_l22_display_operator_limits_above_and_below(self):
        base=n('operator','∑',symbol=True,limits=True,command='sum')
        b=layout(scripts(base,group(sym('n')),group(sym('i'))),Options(display_mode=True))
        gs=glyphs(b);op=next(g for g in gs if g.text=='∑');upper=next(g for g in gs if g.text=='n');lower=next(g for g in gs if g.text=='i')
        self.assertEqual(op.font,'Size2-Regular')
        shift=(1.05-.55001)*EM/2-.25*EM
        self.assertNear(upper.y,-1.05*EM+shift-max(.111*EM,.2*EM))
        self.assertNear(lower.y,.55001*EM+shift+max(.166*EM,.6*EM-MI['i'][1]*14)+MI['i'][1]*14)
        self.assertLess(upper.y,op.y);self.assertGreater(lower.y,op.y)

    def test_l23_nolimits_keeps_scripts_to_operator_right(self):
        op=n('operator','∑',symbol=True,limits=True)
        b=layout(scripts(op,group(sym('n')),group(sym('i')),limits=False),Options(display_mode=True))
        gs=glyphs(b);symbol=next(g for g in gs if g.text=='∑')
        for g in gs:
            if g is not symbol:self.assertGreaterEqual(g.x,1.44445*EM)

    def test_l24_smallint_and_display_integral_keep_source_identity(self):
        normal=layout(n('operator','∫',symbol=True,limits=False),Options(display_mode=True))
        small=layout(n('operator','∫',symbol=True,limits=False,small=True,command='smallint'),Options(display_mode=True))
        self.assertEqual(glyphs(normal)[0].font,'Size2-Regular')
        self.assertEqual(glyphs(small)[0].font,'Size1-Regular')

    def test_l25_radical_uses_source_surd_path_and_clipped_vinculum(self):
        b=layout(n('sqrt','',group(sym('x')),group()))
        self.assertEqual([g.text for g in glyphs(b)],['x'])
        self.assertEqual(len(paths(b)),1);p=paths(b)[0]
        self.assertIn('c-2.7,0,-7.17,-2.7,-13.5,-8',p.d)
        self.assertIn('H400000',p.d);self.assertIsNotNone(p.clip)
        self.assertNear(p.clip[2]*abs(p.scale_x),b.width)
        self.assertGreater(glyphs(b)[0].x,0)

    def test_l26_root_index_is_scriptscript_and_raised(self):
        b=layout(n('sqrt','',group(sym('x')),group(sym('3'))))
        index=next(g for g in glyphs(b) if g.text=='3');body=next(g for g in glyphs(b) if g.text=='x')
        self.assertNear(index.size,.5*EM);self.assertLess(index.y,body.y)

    def test_l27_tall_radical_selects_source_variable_vertical_segment(self):
        b=layout(n('sqrt','',group(n('rule',width=(1,'em'),height=(5,'em'),shift=(0,'em'))),group()))
        self.assertEqual(len(paths(b)),1)
        self.assertIn('h-12l-28-84',paths(b)[0].d)
        self.assertGreater(b.height,100)

    def test_l28_left_right_delimiters_enclose_tall_nucleus(self):
        body=group(n('rule',width=(1,'em'),height=(4,'em'),shift=(0,'em')))
        b=layout(n('delimiters','',body,left='(',right=')',middle=()))
        self.assertEqual(len(paths(b)),2)
        self.assertGreaterEqual(b.height,80)
        self.assertGreater(b.depth,0)
        self.assertTrue(all(p.scale_x==p.scale_y for p in paths(b)))

    def test_l29_stacked_vertical_delimiter_preserves_source_width(self):
        b=layout(n('delimiters','',group(n('rule',width=(1,'em'),height=(4,'em'),shift=(0,'em'))),left='|',right='.',middle=()))
        self.assertEqual(len(paths(b)),1)
        self.assertNear(rules(b)[0].x,.333*EM)

    def test_l30_sized_delimiter_uses_literal_size_font(self):
        for size in range(1,5):
            b=layout(n('sized_delimiter','(',size=size,atom='mopen'))
            self.assertEqual(glyphs(b)[0].font,f'Size{size}-Regular')
            self.assertNear(glyphs(b)[0].size,EM)

    def test_l31_hat_offset_includes_source_skew(self):
        b=layout(n('accent','hat',sym('x')))
        x,hat=glyphs(b)
        self.assertNear(hat.x,(MI['x'][4]*EM-.5*EM)/2+MI['x'][3]*EM)
        self.assertGreater(b.height,MI['x'][1]*EM)

    def test_l32_widehat_uses_source_paths_without_plain_text_surrogate(self):
        b=layout(n('accent','widehat',group(sym('x'),sym('a'),sym('b'))))
        self.assertEqual(len(paths(b)),1)
        self.assertEqual([g.text for g in glyphs(b)],['x','a','b'])
        self.assertGreater(paths(b)[0].scale_x,0)

    def test_l33_stretchy_arrow_keeps_heads_unscaled_and_clips_tail(self):
        b=layout(n('xarrow','xrightarrow',group(*(sym('x') for _ in range(10))),group(sym('i'))))
        p=paths(b)[0];self.assertNear(p.scale_x,EM/1000);self.assertNear(p.scale_y,EM/1000)
        self.assertIsNotNone(p.clip);self.assertGreater(p.clip[0],0)
        self.assertNear(b.width,10*MI['x'][4]*14+14)
        self.assertLess(min(g.y for g in glyphs(b) if g.text=='x'),-.25*EM)
        self.assertGreater(next(g.y for g in glyphs(b) if g.text=='i'),-.25*EM)

    def test_l34_overbrace_annotation_is_centered_above_not_right_script(self):
        brace=n('overunder','overbrace',group(sym('x'),sym('x')),group())
        b=layout(scripts(brace,group(sym('n'))))
        annotation=next(g for g in glyphs(b) if g.text=='n')
        body=[g for g in glyphs(b) if g.text=='x']
        self.assertLess(annotation.y,min(g.y for g in body))
        self.assertLess(annotation.x,max(g.x for g in body)+MI['x'][4]*EM)
        self.assertEqual(len(paths(b)),3)

    def test_l35_matrix_struts_row_pitch_axis_and_column_gap(self):
        row=n('row','',group(sym('1')),group(sym('2')))
        b=layout(n('array','',row,row,environment='matrix',cols=(),hlines=(),row_gaps=(),arraystretch=None))
        gs=glyphs(b)
        self.assertNear(gs[1].x-gs[0].x,.5*EM+EM)
        self.assertNear(gs[2].y-gs[0].y,1.2*EM)
        self.assertNear(b.height,1.2*EM+.25*EM)
        self.assertNear(b.depth,1.2*EM-.25*EM)

    def test_l36_array_column_alignment_is_not_monospaced_text(self):
        rows=(n('row','',group(sym('1')),group(sym('x'))),n('row','',group(sym('x')),group(sym('1'))))
        b=layout(n('array','',*rows,environment='array',cols=('r','l'),hlines=(),row_gaps=()))
        gs=glyphs(b)
        self.assertNear(gs[0].x-gs[2].x,(MI['x'][4]-.5)*EM)
        self.assertNear(gs[1].x,gs[3].x)

    def test_l37_arraystretch_and_positive_row_gap(self):
        row=n('row','',group(sym('1')))
        stretched=layout(n('array','',row,row,environment='matrix',cols=(),hlines=(),row_gaps=(),arraystretch=2.))
        self.assertNear(glyphs(stretched)[1].y-glyphs(stretched)[0].y,2.4*EM)
        gap=layout(n('array','',row,row,environment='matrix',cols=(),hlines=(),row_gaps=((1.,'em'),)))
        self.assertNear(glyphs(gap)[1].y-glyphs(gap)[0].y,(.84+.36+1)*EM)

    def test_l38_aligned_jot_and_alternating_column_gap(self):
        row=n('row','',*(group(sym('1')) for _ in range(4)))
        b=layout(n('array','',row,row,environment='aligned',cols=(),hlines=(),row_gaps=()))
        gs=glyphs(b)
        self.assertNear(gs[1].x-gs[0].x,.5*EM)
        self.assertNear(gs[2].x-gs[1].x,.5*EM+EM)
        self.assertNear(gs[4].y-gs[0].y,1.5*EM)

    def test_l39_array_real_horizontal_vertical_and_dashed_rules(self):
        row=n('row','',group(sym('1')),group(sym('2')))
        b=layout(n('array','',row,row,environment='array',cols=('|','c',':','r','|'),hlines=((0,'hline'),(1,'hdashline'),(2,'hline')),row_gaps=()))
        rs=rules(b);self.assertTrue(any(r.height<r.width for r in rs))
        self.assertTrue(any(r.height>r.width for r in rs))
        self.assertGreater(len(rs),8)
        self.assertTrue(all(r.width>0 and r.height>0 for r in rs))

    def test_l40_cases_has_real_brace_and_text_style_cells(self):
        rows=(n('row','',group(sym('x')),group(sym('1'))),n('row','',group(sym('a')),group(sym('2'))))
        b=layout(n('array','',*rows,environment='cases',cols=('l','l'),left='{',right='.',row_gaps=(),hlines=()))
        self.assertTrue(any(g.text in ('{','⎧','⎨','⎩') for g in glyphs(b)) or bool(paths(b)))
        self.assertNear(next(g.size for g in glyphs(b) if g.text=='x'),EM)
        self.assertNear(next(g.y for g in glyphs(b) if g.text=='a')-next(g.y for g in glyphs(b) if g.text=='x'),1.44*EM)

    def test_l41_font_families_use_literal_source_font_keys(self):
        for command,ch,font,width in (('mathrm','A','Main-Regular',.75),('mathbf','A','Main-Bold',.86944),('mathbb','R','AMS-Regular',.72222),('mathit','x','Main-Italic',.46389)):
            b=layout(n('font',command,group(sym(ch))))
            self.assertEqual(glyphs(b)[0].font,font)
            self.assertNear(b.width,width*EM)

    def test_l42_mathematical_unicode_original_selects_source_alphabet(self):
        for original,value,font in (('𝐀','A','Main-Bold'),('𝔸','A','AMS-Regular'),('𝒜','A','Script-Regular'),('𝚡','x','Typewriter-Regular')):
            b=layout(sym(value,original=original))
            self.assertEqual(glyphs(b)[0].font,font)
            self.assertEqual(glyphs(b)[0].text,value)

    def test_l43_text_font_nesting_and_embedded_math(self):
        b=layout(n('text','textbf',group(n('text','textit',group(sym('A',mode='text'))),sym('x',mode='math'))))
        a,x=glyphs(b)
        self.assertEqual(a.font,'Main-BoldItalic');self.assertEqual(x.font,'Math-Italic')

    def test_l44_phantom_variants_keep_only_requested_dimensions(self):
        for value,w,h,d in (('phantom',True,True,True),('hphantom',True,False,False),('vphantom',False,True,True)):
            b=layout(n('phantom',value,group(sym('y'))))
            self.assertEqual(b.commands,())
            self.assertNear(b.width,(MI['y'][4]+MI['y'][2])*EM if w else 0.)
            self.assertNear(b.height,MI['y'][1]*EM if h else 0.)
            self.assertNear(b.depth,MI['y'][0]*EM if d else 0.)

    def test_l45_smash_preserves_real_paint_and_independent_height_depth(self):
        b=layout(n('smash','',group(sym('y')),smash_height=True,smash_depth=False))
        self.assertNear(b.height,0);self.assertNear(b.depth,MI['y'][0]*EM)
        self.assertEqual([g.text for g in glyphs(b)],['y'])

    def test_l46_lap_keeps_zero_advance_and_signed_ink_offsets(self):
        width=MI['x'][4]*EM
        for kind,x in (('llap',-width),('clap',-width/2),('rlap',0.)):
            b=layout(n('lap',kind,group(sym('x'))))
            self.assertNear(b.width,0);self.assertNear(glyphs(b)[0].x,x)

    def test_l47_raise_and_vcenter_keep_baseline_geometry(self):
        raised=layout(n('raise','',group(sym('y')),dy=(2,'pt')))
        self.assertNear(glyphs(raised)[0].y,-4)
        centered=layout(n('vcenter','',group(sym('y'))))
        self.assertNear((centered.height-centered.depth)/2,.25*EM)

    def test_l48_rule_signed_height_depth_and_absolute_shift(self):
        b=layout(n('rule',width=(2,'em'),height=(1,'pt'),shift=(3,'pt')))
        self.assertNear(b.width,40);self.assertNear(b.height,8);self.assertNear(b.depth,-6)
        # Source .katex-rule min-height:1px paints its right border through
        # an extra content pixel; its logical signed extents remain TeX's.
        self.assertNear(rules(b)[0].y,-9);self.assertNear(rules(b)[0].height,3)

    def test_l49_reflect_flips_real_glyph_transform(self):
        b=layout(n('reflect','',group(sym('x'),sym('a'))))
        gs=glyphs(b);width=(MI['x'][4]+MI['a'][4])*EM
        self.assertNear(b.width,width);self.assertEqual([g.scale_x for g in gs],[-1.,-1.])
        self.assertNear(gs[0].x,width);self.assertNear(gs[1].x,width-MI['x'][4]*EM)

    def test_l50_overline_underline_source_three_rule_clearance(self):
        over=layout(n('line','overline',group(sym('x'))));under=layout(n('line','underline',group(sym('y'))))
        self.assertNear(rules(over)[0].y,-MI['x'][1]*EM-4*.04*EM)
        self.assertNear(rules(under)[0].y,MI['y'][0]*EM+3*.04*EM)
        self.assertNear(over.height,MI['x'][1]*EM+5*.04*EM)

    def test_l51_box_border_overlays_source_horizontal_padding(self):
        # enclose.ts boxpad + CSS border-box: horizontal padding .3em/side;
        # border is painted inward, not an additional .04em advance/side.
        b=layout(n('enclose','boxed',group(sym('x'))))
        self.assertNear(b.width,MI['x'][4]*EM+.6*EM)
        self.assertNear(b.height,MI['x'][1]*EM+(.3+.04)*EM)
        self.assertEqual(len(rules(b)),4)

    def test_l52_colorbox_background_and_fcolorbox_border_are_distinct(self):
        b=layout(n('enclose','fcolorbox',group(sym('x')),color='#ff0000',border_color='#0000ff'))
        rs=rules(b)
        self.assertEqual(rs[0].color,'#ff0000')
        self.assertEqual({r.color for r in rs[1:]},{'#0000ff'})
        self.assertEqual(glyphs(b)[0].color,'#000000')

    def test_l53_cancel_is_real_diagonal_path_without_dropping_subject(self):
        b=layout(n('enclose','xcancel',group(sym('x'))))
        self.assertEqual([g.text for g in glyphs(b)],['x'])
        self.assertEqual(len(paths(b)),2)
        self.assertTrue(all(p.stroke_width>0 for p in paths(b)))

    def test_l54_pmb_keeps_source_offset_duplicate(self):
        # FULL now represents the literal pmb.ts text-shadow blur as a pure
        # CommandGroup filter. The initial slice's omitted-blur evidence is
        # preserved; source offset and real shadow content remain required.
        b=layout(n('pmb','',group(sym('x'))))
        real=glyphs(b)[0];shadow=next(c for c in b.commands if isinstance(c,CommandGroup))
        self.assertEqual(shadow.filter,'blur(0.04px)')
        self.assertEqual([c.text for c in shadow.commands if isinstance(c,Glyph)],['x'])
        self.assertNear(shadow.x-real.x,.02*EM);self.assertNear(shadow.y-real.y,.01*EM)
        self.assertNear(b.width,MI['x'][4]*EM)

    def test_l55_linebreak_resets_x_and_retains_explicit_gap(self):
        b=layout(group(sym('x'),n('linebreak',gap=(1,'em')),sym('a')))
        x,a=glyphs(b);self.assertNear(a.x,0);self.assertGreaterEqual(a.y-x.y,2.2*EM)

    def test_l56_unknown_kind_font_and_missing_metric_fail_explicitly(self):
        # FULL source Parser/fontMetrics permits visible Unicode fallback;
        # missing a bundled character metric is no longer itself rejection.
        # A genuinely nonexistent font metric family still must fail, as in
        # fixed getCharacterMetrics, and an unknown AST kind stays invalid.
        missing_family=n('symbol','x',font='NotAnUpstreamFont',mode='math',atom='mord')
        for node,code in ((n('unknown_layout_kind'), 'UNSUPPORTED_LAYOUT_KIND'),(n('font','invented',group(sym('x'))),'UNSUPPORTED_FONT'),(missing_family,'MISSING_FONT_METRICS')):
            with self.subTest(code=code),self.assertRaises(ParseError) as caught:layout(node)
            self.assertEqual(caught.exception.code,code)

    def test_l57_depth_and_node_limits_apply_to_manually_supplied_ast(self):
        tree=group(group(group(sym('x'))))
        with self.assertRaises(ParseError) as caught:layout(tree,Options(max_depth=1))
        self.assertEqual(caught.exception.code,'MAX_DEPTH')
        with self.assertRaises(ParseError) as caught:layout(group(sym('x'),sym('a')),Options(max_nodes=2))
        self.assertEqual(caught.exception.code,'MAX_NODES')

    def test_l58_invalid_font_size_and_non_node_inputs_rejected(self):
        for size in (0,-1,math.inf,math.nan):
            with self.subTest(size=size),self.assertRaises(ValueError):layout(group(sym('x')),Options(font_size=size))
        with self.assertRaises(TypeError):layout('x')

    def test_l59_options_and_ast_are_not_mutated_by_layout(self):
        tree=group(sym('x'),n('color','#ff0000',group(sym('a'))));opts=Options(font_size=24)
        before_tree=repr(tree);before_opts=repr(opts);layout(tree,opts)
        self.assertEqual(repr(tree),before_tree);self.assertEqual(repr(opts),before_opts)

    def test_l60_empty_group_is_legitimate_but_not_unknown_success(self):
        b=layout(group());self.assertEqual((b.width,b.height,b.depth,b.commands),(0.,0.,0.,()))
        with self.assertRaises(ParseError):layout(n('unknown'))

    def test_l61_fraction_geometry_guard_rejects_flattening_and_missing_rule(self):
        def check(box):
            gs=glyphs(box);rs=rules(box)
            self.assertEqual(len(gs),2);self.assertEqual(len(rs),1)
            self.assertNear(gs[0].y,-.394*EM);self.assertNear(gs[1].y,.345*EM)
            self.assertNear(rs[0].y,-(.25+.04/2)*EM)
        b=layout(n('frac','',group(sym('1')),group(sym('2')),bar=True))
        check(b)
        flat=replace(b,commands=tuple(replace(c,y=0.) if isinstance(c,Glyph) else c for c in b.commands))
        missing=replace(b,commands=tuple(c for c in b.commands if not isinstance(c,Rule)))
        for faulty in (flat,missing):
            with self.subTest(fault='flattened' if faulty is flat else 'missing-bar'),self.assertRaises(AssertionError):check(faulty)

    def test_l62_stretchy_geometry_guard_rejects_unclipped_or_distorted_head(self):
        def check(box):
            ps=paths(box);self.assertEqual(len(ps),1);p=ps[0]
            self.assertIsNotNone(p.clip)
            self.assertNear(p.scale_x,EM/1000);self.assertNear(p.scale_y,EM/1000)
            self.assertNear(p.clip[2]*abs(p.scale_x),box.width)
        b=layout(n('xarrow','xrightarrow',group(sym('n')),group()))
        check(b)
        for change in ({'clip':None},{'scale_x':.0001}):
            faulty=replace(b,commands=tuple(replace(c,**change) if isinstance(c,Path) else c for c in b.commands))
            with self.subTest(change=change),self.assertRaises(AssertionError):check(faulty)

    def test_l63_array_separator_follows_postgap_before_next_pregap(self):
        # environments/array.ts: col -> postgap(.5em) -> zero-advance
        # separator(border .04em, margins -.02em) -> pregap(.5em) -> col.
        row1=n('row','',group(sym('1')),group(sym('2'),sym('2')))
        row2=n('row','',group(sym('3'),sym('3'),sym('3')),group(sym('4')))
        b=layout(n('array','',row1,row2,environment='array',cols=('c','|','r'),hlines=((1,'hline'),),row_gaps=()))
        vertical=[r for r in rules(b) if r.height>r.width][0]
        self.assertNear(b.width,(.5+1.5+.5+.5+1+.5)*EM)
        self.assertNear(vertical.x,(.5+1.5+.5-.04/2)*EM)
        threes=[g for g in glyphs(b) if g.text=='3']
        self.assertNear(vertical.x-(threes[-1].x+.5*EM),(.5-.04/2)*EM)
        self.assertNear(next(g.x for g in glyphs(b) if g.text=='2'),3*EM)

    def test_l64_array_separator_empty_delimiter_is_not_explicit_null(self):
        row=n('row','',group(sym('1')))
        absent=layout(n('array','',row,environment='matrix',cols=(),hlines=(),row_gaps=()))
        empty=layout(n('array','',row,environment='matrix',cols=(),hlines=(),row_gaps=(),left='',right=''))
        explicit=layout(n('array','',row,environment='matrix',cols=(),hlines=(),row_gaps=(),left='.',right='.'))
        self.assertNear(absent.width,.5*EM);self.assertNear(empty.width,.5*EM)
        self.assertNear(glyphs(empty)[0].x,0.)
        self.assertNear(explicit.width,.5*EM+2*.12*EM)

    def test_l65_array_separator_double_rules_have_source_double_rule_sep(self):
        row=n('row','',group(sym('1')),group(sym('2')))
        b=layout(n('array','',row,environment='array',cols=('c','|','|','c'),hlines=(),row_gaps=()))
        vertical=sorted((r for r in rules(b) if r.height>r.width),key=lambda r:r.x)
        self.assertEqual(len(vertical),2)
        self.assertNear(vertical[1].x-vertical[0].x,.2*EM)
        # Source CSS negative margins cancel each separator's own width;
        # only the explicit doubleRuleSep contributes horizontal advance.
        self.assertNear(b.width,(.5+.5+.5+.2+.5+.5+.5)*EM)


if __name__=='__main__':unittest.main()
