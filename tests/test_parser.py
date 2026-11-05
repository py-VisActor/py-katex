"""Independent source expectations: KaTeX 0.18.11 Parser/functions/specs.

Written after P1 freeze; not executed during P2. Helpers only inspect AST values,
never derive expected results by calling the implementation under test.
"""
from dataclasses import FrozenInstanceError
import unittest

from py_katex.parser import parse
from py_katex.model import ParseError


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def glyphs(node):
    return ''.join(n.value for n in walk(node) if n.kind=='symbol')


def nodes(node, kind):
    return [n for n in walk(node) if n.kind==kind]


class SourceAtomsAndModes(unittest.TestCase):
    def test_empty_input_and_empty_group(self):
        self.assertEqual((parse('').kind,parse('').children),('group',()))
        self.assertEqual(glyphs(parse('{}')),'')

    def test_math_whitespace_comments_and_nested_group_order(self):
        self.assertEqual(glyphs(parse(' a {b{c}} % hidden\r\n + d ')),'abc+d')

    def test_symbol_table_atom_classes_are_source_categories(self):
        tree=parse(r'a+\alpha=\beta,(x)')
        actual=[(n.value,n.get('atom')) for n in nodes(tree,'symbol')]
        self.assertEqual(actual,[('a','mord'),('+','mbin'),('\u03b1','mord'),('=','mrel'),('\u03b2','mord'),(',','mpunct'),('(','mopen'),('x','mord'),(')','mclose')])

    def test_source_ams_relation_symbol_is_not_plain_control_text(self):
        node=nodes(parse(r'\leqslant'),'symbol')[0]
        self.assertEqual((node.value,node.get('font'),node.get('atom')),('\u2a7d','ams','mrel'))

    def test_source_wide_alphabet_original_identity_survives_replacement(self):
        for char in ['\U0001d538','\U0001d400','\U0001d49c']:
            with self.subTest(char=char):
                symbol=nodes(parse(char),'symbol')[0]
                self.assertEqual(symbol.get('original'),char)

    def test_unicode_combining_and_precomposed_accents(self):
        for text in ['a\u0301','\u00e1']:
            with self.subTest(text=text):
                node=nodes(parse(text),'accent')[0]
                self.assertEqual((node.value,glyphs(node)),('acute','a'))

    def test_unicode_source_position_is_codepoint_not_utf16(self):
        tree=parse('\U0001d538'+r'+\alpha')
        positions=[n.position for n in nodes(tree,'symbol')]
        self.assertEqual(positions,[0,1,2])

    def test_unterminated_group_reports_error(self):
        for text in ['{x','x}','{{x}']:
            with self.subTest(text=text),self.assertRaises(ParseError):parse(text)

    def test_undefined_control_does_not_succeed_as_literal_text(self):
        with self.assertRaises(ParseError) as caught:parse(r'a+\thisCommandDoesNotExist')
        self.assertEqual(caught.exception.position,2)

    def test_text_mode_retains_spaces_and_literal_font_group(self):
        tree=parse(r'\text{a b}')
        text=nodes(tree,'text')[0]
        self.assertEqual(text.value,'text')
        self.assertEqual(glyphs(text),'ab')
        self.assertEqual(len(nodes(text,'space')),1)
        self.assertTrue(all(n.get('mode')=='text' for n in nodes(text,'symbol')))

    def test_text_mode_rejects_math_fraction_command(self):
        with self.assertRaises(ParseError):parse(r'\text{a\frac12}')

    def test_source_function_mode_flags_cover_roots_and_math_fonts(self):
        for tex in [r'\text{\sqrt{x}}',r'\text{\mathbf{x}}',r'\text{\sum}']:
            with self.subTest(tex=tex),self.assertRaises(ParseError):parse(tex)
        # Old font declarations are source allowedInText=true.
        self.assertEqual(glyphs(parse(r'\text{\bf x}')),'x')

    def test_embedded_math_in_text_switches_symbol_mode_back(self):
        tree=parse(r'\text{a $x^2$ b}')
        self.assertEqual([(n.value,n.get('mode')) for n in nodes(tree,'symbol')],[('a','text'),('x','math'),('2','math'),('b','text')])

    def test_verb_preserves_control_characters_without_expansion(self):
        tree=parse(r'\verb|a\unknown{x}%|')
        self.assertEqual(glyphs(tree),r'a\unknown{x}%')
        self.assertEqual(nodes(tree,'text')[0].value,'texttt')

    def test_verb_star_shows_spaces(self):
        self.assertEqual(glyphs(parse(r'\verb*|a b|')),'a\u2423b')

    def test_unknown_environment_and_mismatched_closing_environment(self):
        for text in [r'\begin{notAnEnvironment}x\end{notAnEnvironment}',r'\begin{matrix}x\end{array}']:
            with self.subTest(text=text),self.assertRaises(ParseError):parse(text)


class SourceScriptsAndFractions(unittest.TestCase):
    def test_subscript_superscript_order_independent(self):
        for text in ['x_i^2','x^2_i']:
            with self.subTest(text=text):
                node=nodes(parse(text),'scripts')[0]
                self.assertEqual(tuple(glyphs(c) for c in node.children),('x','2','i'))

    def test_scripts_on_empty_base(self):
        node=nodes(parse('^2_3'),'scripts')[0]
        self.assertEqual(tuple(glyphs(c) for c in node.children),('','2','3'))

    def test_repeated_primes_and_following_superscript_combine(self):
        node=nodes(parse("x'''^2"),'scripts')[0]
        self.assertEqual(glyphs(node.children[1]),'\u2032\u2032\u20322')

    def test_duplicate_explicit_scripts_and_missing_argument_reject(self):
        for text in ['x^2^3','x_i_j','x^','x_']:
            with self.subTest(text=text),self.assertRaises(ParseError):parse(text)

    def test_unicode_script_runs_use_normal_glyphs(self):
        node=nodes(parse('x\u2081\u2082\u00b2\u207a'),'scripts')[0]
        self.assertEqual(tuple(glyphs(c) for c in node.children),('x','2+','12'))

    def test_source_unicode_script_replaces_prior_matching_script(self):
        # Parser.ts Unicode branch assigns subscript without duplicate check.
        node=nodes(parse('x_1\u2082'),'scripts')[0]
        self.assertEqual(glyphs(node.children[2]),'2')

    def test_unicode_superscript_replaces_explicit_but_explicit_duplicate_still_rejects(self):
        node=nodes(parse('x^1\u00b2'),'scripts')[0]
        self.assertEqual(glyphs(node.children[1]),'2')
        with self.assertRaises(ParseError):parse('x\u00b2^3')

    def test_fraction_numerators_denominators_and_style(self):
        for command,style in [('frac','auto'),('dfrac','display'),('tfrac','text')]:
            with self.subTest(command=command):
                node=nodes(parse('\\'+command+'{a+b}{c}'),'frac')[0]
                self.assertEqual(tuple(glyphs(c) for c in node.children),('a+b','c'))
                self.assertEqual((node.get('bar'),node.get('style')),(True,style))

    def test_primitive_fraction_arguments_are_single_tokens(self):
        tree=parse(r'\frac12+3')
        node=nodes(tree,'frac')[0]
        self.assertEqual(tuple(glyphs(c) for c in node.children),('1','2'))
        self.assertEqual(glyphs(tree),'12+3')

    def test_binomial_has_parentheses_and_no_bar(self):
        node=nodes(parse(r'\binom nk'),'frac')[0]
        self.assertEqual((node.get('bar'),node.get('left'),node.get('right')),(False,'(',')'))

    def test_infix_fraction_scope_and_brace_brack_choose(self):
        table=[('over',True,'',''),('atop',False,'',''),('choose',False,'(',')'),('brace',False,'{','}'),('brack',False,'[',']')]
        for name,bar,left,right in table:
            with self.subTest(name=name):
                node=nodes(parse('{a\\'+name+' b}'),'frac')[0]
                self.assertEqual((node.get('bar'),node.get('left'),node.get('right')),(bar,left,right))
                self.assertEqual(tuple(glyphs(c) for c in node.children),('a','b'))

    def test_multiple_infix_fractions_in_same_group_reject(self):
        with self.assertRaises(ParseError):parse(r'{a\over b\over c}')

    def test_above_zero_thickness_omits_fraction_bar(self):
        node=nodes(parse(r'{a\above0pt b}'),'frac')[0]
        self.assertFalse(node.get('bar'))
        self.assertEqual(node.get('thickness'),(0.,'pt'))

    def test_genfrac_empty_thickness_means_default_and_zero_means_no_bar(self):
        for thickness,bar in [('',True),('0pt',False),('0.6pt',True)]:
            with self.subTest(thickness=thickness):
                node=nodes(parse(r'\genfrac{(}{)}{'+thickness+r'}{1}{a}{b}'),'frac')[0]
                self.assertEqual((node.get('bar'),node.get('style'),node.get('left'),node.get('right')),(bar,'text','(',')'))

    def test_cfrac_continued_flag_and_alignment(self):
        node=nodes(parse(r'\cfrac[l]{1}{x}'),'frac')[0]
        self.assertEqual((node.get('continued'),node.get('align'),node.get('style')),(True,None,'display'))
        self.assertEqual([glyphs(c) for c in node.children],['[','l'])

    def test_sqrt_optional_index_is_not_part_of_radicand(self):
        node=nodes(parse(r'\sqrt[3]{x+1}'),'sqrt')[0]
        self.assertEqual(tuple(glyphs(c) for c in node.children),('x+1','3'))
        self.assertEqual(glyphs(nodes(parse(r'\sqrt{x}'),'sqrt')[0].children[1]),'')


class SourceFunctionsAndArrays(unittest.TestCase):
    def test_large_operators_limits_and_integrals(self):
        for command,value,limits in [('sum','\u2211',True),('prod','\u220f',True),('int','\u222b',False)]:
            with self.subTest(command=command):
                node=nodes(parse('\\'+command+'_a^b'),'operator')[0]
                self.assertEqual((node.value,node.get('limits'),node.get('symbol')),(value,limits,True))

    def test_smallint_preserves_identity(self):
        node=nodes(parse(r'\smallint'),'operator')[0]
        self.assertEqual((node.value,node.get('small')),('\u222b',True))

    def test_limit_controls_only_follow_operators(self):
        for command,expected in [('limits',True),('nolimits',False)]:
            node=nodes(parse('\\sum\\'+command+'_a^b'),'scripts')[0]
            self.assertIs(node.get('limits'),expected)
        with self.assertRaises(ParseError):parse(r'x\limits')

    def test_operatorname_mathop_and_builtin_operator(self):
        node=nodes(parse(r'\operatorname*{argmax}_x'),'operator')[0]
        self.assertEqual((glyphs(node),node.get('limits'),node.get('always_handle_supsub')),('argmax',False,True))
        self.assertFalse(nodes(parse(r'\mathop{x+y}'),'operator')[0].get('roman'))
        self.assertEqual(nodes(parse(r'\sin x'),'operator')[0].value,'sin')

    def test_delimiter_segments_middle_and_null_delimiter(self):
        node=nodes(parse(r'\left. a\middle|b\right\rangle'),'delimiters')[0]
        self.assertEqual((node.get('left'),node.get('right'),node.get('middle')),('.', '\u27e9',('|',)))
        self.assertEqual([glyphs(c) for c in node.children],['a','b'])

    def test_sized_delimiters_sizes_and_atom_classes(self):
        for command,size,atom in [('bigl',1,'mopen'),('Biggr',4,'mclose'),('biggm',3,'mrel')]:
            node=nodes(parse('\\'+command+'('),'sized_delimiter')[0]
            self.assertEqual((node.value,node.get('size'),node.get('atom')),('(',size,atom))

    def test_invalid_or_unpaired_delimiters_reject(self):
        for text in [r'\left x a\right)',r'\left(a',r'\right)',r'\middle|']:
            with self.subTest(text=text),self.assertRaises(ParseError):parse(text)

    def test_font_families_keep_source_font_names(self):
        for name in ['mathrm','mathbf','mathbb','mathcal','mathscr','mathfrak','mathsf','mathtt','boldsymbol']:
            node=nodes(parse('\\'+name+'{AB}'),'font')[0]
            self.assertEqual((node.value,glyphs(node)),(name,'AB'))

    def test_declaration_style_and_color_end_at_group_boundary(self):
        tree=parse(r'{\scriptstyle a}{\color{red}b}c')
        self.assertEqual((nodes(tree,'style')[0].value,glyphs(nodes(tree,'style')[0])),('script','a'))
        self.assertEqual((nodes(tree,'color')[0].value,glyphs(nodes(tree,'color')[0])),('red','b'))
        self.assertEqual(glyphs(tree),'abc')

    def test_source_color_grammar_hex_alpha_and_unprefixed_hex(self):
        for source,expected in [('ABCDEF','#ABCDEF'),('#abcd','#abcd'),('#12345678','#12345678'),('red','red')]:
            with self.subTest(source=source):self.assertEqual(nodes(parse(r'\textcolor{'+source+'}{x}'),'color')[0].value,expected)
        with self.assertRaises(ParseError):parse(r'\textcolor{url(bad)}{x}')

    def test_source_dimensions_are_parsed_separately_from_following_letters(self):
        tree=parse(r'\kern1emx\mkern-3mu y')
        self.assertEqual([n.get('width') for n in nodes(tree,'kern')],[(1.,'em'),(-3.,'mu')])
        self.assertEqual(glyphs(tree),'xy')

    def test_dimension_units_and_invalid_unit(self):
        for unit in ['em','ex','mu','pt','mm','cm','in','bp','pc','dd','cc','nd','nc','sp','px']:
            with self.subTest(unit=unit):self.assertEqual(nodes(parse(r'\kern{2'+unit+'}'),'kern')[0].get('width'),(2.,unit))
        self.assertEqual(nodes(parse(r'\kern{2invalid}'),'kern')[0].get('width'),(2.,'in'))
        with self.assertRaises(ParseError):parse(r'\kern{2zz}')

    def test_accent_line_brace_and_annotation_family(self):
        self.assertEqual(nodes(parse(r'\widehat{x}'),'accent')[0].value,'widehat')
        self.assertEqual(nodes(parse(r'\underline{x}'),'line')[0].value,'underline')
        self.assertEqual(nodes(parse(r'\overbrace{x+y}^n'),'overunder')[0].value,'overbrace')
        node=nodes(parse(r'\underset{a}{b}'),'overunder')[0]
        self.assertEqual(tuple(glyphs(c) for c in node.children),('b','a'))

    def test_extensible_arrow_has_separate_above_and_below(self):
        node=nodes(parse(r'\xrightarrow[b]{a}'),'xarrow')[0]
        self.assertEqual((node.value,tuple(glyphs(c) for c in node.children)),('xrightarrow',('a','b')))

    def test_phantom_smash_lap_rule_raise_and_enclose_family(self):
        tree=parse(r'\phantom{x}\smash[t]{y}\mathrlap{z}\rule[1pt]{2em}{3pt}\raisebox{2pt}{a}\cancel{b}')
        self.assertEqual(nodes(tree,'phantom')[0].value,'phantom')
        self.assertEqual((nodes(tree,'smash')[0].get('smash_height'),nodes(tree,'smash')[0].get('smash_depth')),(True,False))
        self.assertEqual(nodes(tree,'lap')[0].value,'rlap')
        rule=nodes(tree,'rule')[0]
        self.assertEqual((rule.get('width'),rule.get('height'),rule.get('shift')),((2.,'em'),(3.,'pt'),(1.,'pt')))
        self.assertEqual(nodes(tree,'raise')[0].get('dy'),(2.,'pt'))
        self.assertEqual(nodes(tree,'enclose')[0].value,'cancel')

    def test_fcolorbox_argument_order_is_border_then_background(self):
        node=nodes(parse(r'\fcolorbox{red}{blue}{x}'),'enclose')[0]
        self.assertEqual((node.get('border_color'),node.get('color')),('red','blue'))

    def test_boxed_source_macro_keeps_math_body_inside_text_box(self):
        tree=parse(r'\boxed{x^2}')
        self.assertEqual(nodes(tree,'enclose')[0].value,'fbox')
        self.assertEqual(glyphs(nodes(tree,'scripts')[0].children[0]),'x')

    def test_mathchoice_retains_all_four_style_alternatives(self):
        node=nodes(parse(r'\mathchoice{a}{b}{c}{d}'),'mathchoice')[0]
        self.assertEqual([glyphs(c) for c in node.children],['a','b','c','d'])

    def test_matrix_row_cell_order_and_delimiter_variants(self):
        table=[('matrix','',''),('pmatrix','(',')'),('bmatrix','[',']'),('Bmatrix','{','}'),('vmatrix','|','|'),('Vmatrix','\u2016','\u2016')]
        for env,left,right in table:
            with self.subTest(env=env):
                node=nodes(parse('\\begin{'+env+r'}a&b\\c&d\end{'+env+'}'),'array')[0]
                self.assertEqual([[glyphs(c) for c in row.children] for row in node.children],[['a','b'],['c','d']])
                self.assertEqual((node.get('left'),node.get('right')),(left,right))

    def test_array_alignments_vertical_horizontal_rules_and_row_gap(self):
        node=nodes(parse(r'\begin{array}{l|r}\hline a&b\\[2pt]c&d\end{array}'),'array')[0]
        self.assertEqual(node.get('cols'),('l','|','r'))
        self.assertEqual(node.get('row_gaps'),((2.,'pt'),))
        self.assertEqual(node.get('hlines'),((0,'hline'),))

    def test_matrix_star_and_cases_alignment(self):
        node=nodes(parse(r'\begin{pmatrix*}[r]a&b\end{pmatrix*}'),'array')[0]
        self.assertEqual(node.get('cols'),('r',))
        node=nodes(parse(r'\begin{cases}x&y\end{cases}'),'array')[0]
        self.assertEqual((node.get('cols'),node.get('left'),node.get('right')),(('l','l'),'{','.'))

    def test_nested_environments_keep_rows_separate(self):
        tree=parse(r'\begin{matrix}\begin{pmatrix}a\\b\end{pmatrix}&c\end{matrix}')
        arrays=nodes(tree,'array')
        self.assertEqual([a.get('environment') for a in arrays],['matrix','pmatrix'])
        self.assertEqual([len(a.children) for a in arrays],[1,2])

    def test_align_gather_equation_family_environment_identity(self):
        for env in ['aligned','align','align*','split','gathered','gather','gather*','equation','equation*','smallmatrix','subarray']:
            prefix='{c}' if env=='subarray' else ''
            with self.subTest(env=env):self.assertEqual(nodes(parse('\\begin{'+env+'}'+prefix+'x\\end{'+env+'}',display_mode=True),'array')[0].get('environment'),env)

    def test_split_and_equation_reject_extra_alignment_tabs(self):
        for text in [r'\begin{equation}a&b\end{equation}',r'\begin{split}a&b&c\end{split}']:
            with self.subTest(text=text),self.assertRaises(ParseError):parse(text)

    def test_source_array_excess_columns_are_nonfatal_without_strict_mode(self):
        # array.ts only throws for singleRow/colSeparationType; normal array
        # calls handleStrict for this case, whose default is a warning.
        array=nodes(parse(r'\begin{array}{c}a&b\end{array}'),'array')[0]
        self.assertEqual([glyphs(c) for c in array.children[0].children],['a','b'])

    def test_explicit_arraystretch_macro_is_retained(self):
        node=nodes(parse(r'\def\arraystretch{1.5}\begin{matrix}a\\b\end{matrix}'),'array')[0]
        self.assertEqual(node.get('arraystretch'),1.5)
        with self.assertRaises(ParseError):parse(r'\def\arraystretch{-1}\begin{matrix}a\end{matrix}')

    def test_top_level_newline_is_a_static_break(self):
        node=nodes(parse(r'a\\[1ex]b'),'linebreak')[0]
        self.assertEqual(node.get('gap'),(1.,'ex'))

    def test_reflection_pmb_and_vcenter_do_not_become_plain_groups(self):
        tree=parse(r'\mathreflectbox{x}\pmb{y}\vcenter{z}')
        self.assertEqual([n.kind for n in tree.children],['reflect','pmb','vcenter'])


class NativeSafetyAndBudgetContract(unittest.TestCase):
    def test_href_discards_navigation_and_preserves_static_label(self):
        tree=parse(r'\href{javascript:bad()}{x^2}',trust=False)
        self.assertEqual(nodes(tree,'unsupported')[0].value,r'\href')
        self.assertTrue(nodes(tree,'unsupported')[0].get('rejected'))
        self.assertEqual(glyphs(parse(r'\href{https://example.invalid}{x^2}',trust=True)),'x2')
        self.assertFalse(any('javascript' in repr(n.attrs) for n in walk(tree)))

    def test_url_is_typewriter_static_text(self):
        tree=parse(r'\url{https://example.invalid/a}',trust=True)
        self.assertEqual(glyphs(tree),'https://example.invalid/a')
        self.assertEqual(nodes(tree,'text')[0].value,'texttt')

    def test_visual_htmlmathml_macro_selects_visual_branch_without_host(self):
        self.assertEqual(glyphs(parse(r'\html@mathml{a}{b}')),'a')

    def test_valid_source_commands_outside_native_contract_fail_explicitly(self):
        retained=[(r'\htmlClass{foo}{x}','html'),(r'\htmlStyle{color:red}{x}','html'),(r'\includegraphics{x.png}','image'),(r'\begin{CD}A\end{CD}','array'),(r'\Braket{x|y}','delimiters'),(r'\tag{1}x','tag')]
        for tex,kind in retained:
            with self.subTest(tex=tex):self.assertTrue(nodes(parse(tex,trust=True,display_mode=True,strict='ignore'),kind))

    def test_depth_and_node_budgets_raise_named_parse_errors(self):
        for tex,kwargs,code in [('{'*20+'x'+'}'*20,{'max_depth':8},'MAX_DEPTH'),('abcde',{'max_nodes':3},'MAX_NODES')]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ParseError) as caught:parse(tex,**kwargs)
                self.assertEqual(caught.exception.code,code)

    def test_invalid_limits_and_input_are_explicit(self):
        for kwargs in [{'max_nodes':-1},{'max_depth':True},{'max_expand':float('nan')}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ParseError):parse('x',**kwargs)
        with self.assertRaises(ParseError):parse(None)
        self.assertEqual(glyphs(parse('x',max_expand=1.5)),'x')

    def test_results_are_immutable_and_requests_are_isolated(self):
        first=parse('x');second=parse('y')
        self.assertEqual((glyphs(first),glyphs(second)),('x','y'))
        with self.assertRaises(FrozenInstanceError):first.kind='wrong'


if __name__=='__main__':unittest.main()
