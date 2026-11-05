"""Hand-written full-parser expectations from fixed KaTeX handlers/specs.

P2 only writes and compiles. No fixture expectations are candidate-generated.
"""
import unittest
import warnings
from py_katex.parser import parse
from py_katex.model import ParseError,MathWarning,Node


def tree(tex,**options):return parse(tex,strict='ignore',**options)
def walk(node):
    yield node
    for child in node.children:yield from walk(child)
def kinds(node,kind):return [n for n in walk(node) if n.kind==kind]
def glyphs(node):return (node.value if node.kind=='symbol' else '')+''.join(glyphs(c) for c in node.children)


class RawArgumentAndModeSourceTests(unittest.TestCase):
    def test_primitive_root_argument_cannot_begin_with_a_script_marker(self):
        # Parser.parseGroup('argument to sqrt') has no nucleus for ^ or _.
        for tex in (r'\sqrt^23',r'\sqrt_23'):
            with self.subTest(tex=tex),self.assertRaises(ParseError) as caught:tree(tex)
            self.assertEqual(caught.exception.position,5)

    def test_root_without_optional_index_expands_then_takes_one_primitive_group(self):
        result=tree(r'\def\probe{123}\sqrt\probe')
        self.assertEqual(glyphs(kinds(result,'sqrt')[0].children[0]),'1')
        self.assertEqual(glyphs(result),'123')
        self.assertEqual(len(kinds(tree(r'\sqrt\frac x y'),'frac')),1)
        with self.assertRaises(ParseError):tree(r'\sqrt\over2')

    def test_sized_delimiter_normalizes_one_braced_symbol(self):
        self.assertEqual(kinds(tree(r'\bigl{|}'),'sized_delimiter')[0].value,'|')
        with self.assertRaises(ParseError):tree(r'\bigl{ab}')

    def test_text_accent_primitive_preserves_literal_space(self):
        accent=kinds(tree(r"\text{\' }"),'accent')[0]
        self.assertEqual(accent.get('mode'),'text')
        self.assertEqual(accent.children[0].children[0].kind,'space')

    def test_emphasis_keeps_dynamic_font_shape_instead_of_forcing_italic(self):
        values=[n.value for n in kinds(tree(r'\textit{\emph{x \emph{y}}}'),'text')]
        self.assertEqual(values,['textit','emph','emph'])

    def test_ordinary_argument_expands_only_inside_its_scanned_boundary(self):
        result=tree(r'\def\probe{ab}\frac\probe c')
        frac=kinds(result,'frac')[0]
        self.assertEqual([glyphs(c) for c in frac.children],['ab','c'])

    def test_unbraced_function_cannot_steal_its_argument_from_next_parent_argument(self):
        with self.assertRaises(ParseError):tree(r'\frac\sqrt12')

    def test_primitive_script_allows_frac_but_requires_braces_around_sqrt(self):
        self.assertEqual(len(kinds(tree(r'x^\frac12'),'frac')),1)
        with self.assertRaises(ParseError):tree(r'x^\sqrt{2}')
        self.assertEqual(len(kinds(tree(r'x^{\sqrt{2}}'),'sqrt')),1)

    def test_optional_lookahead_does_not_expand_a_macro_into_an_opener(self):
        result=tree(r'\def\opener{[}\sqrt\opener x')
        root=kinds(result,'sqrt')[0]
        self.assertEqual(glyphs(root.children[0]),'[')
        self.assertFalse(root.get('index_provided'))

    def test_empty_optional_root_index_is_distinct_from_absent(self):
        self.assertTrue(kinds(tree(r'\sqrt[]{x}'),'sqrt')[0].get('index_provided'))
        self.assertFalse(kinds(tree(r'\sqrt{x}'),'sqrt')[0].get('index_provided'))

    def test_source_cfrac_has_no_optional_alignment_argument(self):
        result=tree(r'\cfrac[l]{1}{x}')
        frac=kinds(result,'frac')[0]
        self.assertEqual([glyphs(c) for c in frac.children],['[','l'])
        self.assertTrue(frac.get('continued'))
        self.assertIsNone(frac.get('align'))

    def test_hbox_command_resets_font_without_forcing_textstyle(self):
        group=tree(r'\hbox{x}').children[0]
        self.assertEqual(group.kind,'group')
        self.assertTrue(group.get('reset_font'))
        self.assertTrue(group.get('no_break'))

    def test_hbox_argument_type_for_fbox_and_raisebox_is_textstyle(self):
        for tex,parent in [(r'\fbox{x}','enclose'),(r'\raisebox{1pt}{x}','raise')]:
            with self.subTest(tex=tex):
                body=kinds(tree(tex),parent)[0].children[0]
                self.assertEqual((body.kind,body.value,body.get('reset_font')),('style','text',True))

    def test_text_math_parentheses_switch_and_restore_mode(self):
        result=tree(r'\text{a\(x_i\)b}')
        self.assertEqual([(n.value,n.get('mode')) for n in kinds(result,'symbol')],[('a','text'),('x','math'),('i','math'),('b','text')])

    def test_closing_math_delimiters_are_syntax_guards_even_without_throw_on_error(self):
        for tex in [r'\text{\)}',r'\text{\]}']:
            with self.subTest(tex=tex),self.assertRaises(ParseError):tree(tex,throw_on_error=False)

    def test_math_only_unicode_operators_are_not_accepted_in_text(self):
        with self.assertRaises(ParseError):tree('\u005ctext{\u2211}')

    def test_text_ligatures_are_source_sequences_not_ascii_glyphs(self):
        result=tree(r"\text{--- -- ``x''}")
        self.assertEqual(glyphs(result),'\u2014\u2013\u201cx\u201d')

    def test_dotless_i_and_j_under_unicode_accents(self):
        result=tree('i\u0301+j\u0302')
        self.assertEqual([glyphs(n) for n in kinds(result,'accent')],['\u0131','\u0237'])

    def test_cedilla_and_double_acute_unicode_text_are_supported(self):
        result=tree('\u005ctext{\u00e7\u0151}')
        self.assertEqual([n.value for n in kinds(result,'accent')],['cedilla','hungarumlaut'])
        self.assertEqual(glyphs(result),'co')

    def test_unknown_nonmath_unicode_is_marked_as_text_for_native_font_runs(self):
        result=tree('\u4e2d\u6587')
        self.assertTrue(all(n.get('mode')=='text' for n in kinds(result,'symbol')))


class SourceMeasurementsAndDeclarations(unittest.TestCase):
    def test_missing_size_and_unbraced_raise_retain_source_failure_boundaries(self):
        for tex in (r'\rule{1em}',r'\rule{1em}[2em]',r'\raisebox5pt{text}',r'\raisebox-5pt{text}'):
            with self.subTest(tex=tex),self.assertRaises(ParseError):tree(tex)

    def test_newline_size_optional_is_not_scanned_across_literal_space(self):
        result=tree(r'a\\ [b]')
        self.assertIsNone(kinds(result,'linebreak')[0].get('gap'))
        self.assertEqual(glyphs(result),'a[b]')

    def test_empty_matrix_alignment_is_not_the_absent_default(self):
        with self.assertRaises(ParseError):tree(r'\begin{matrix*}[]a\end{matrix*}')
        self.assertEqual(kinds(tree(r'\begin{matrix*}a\end{matrix*}'),'array')[0].get('cols'),('c',))
    def test_unanchored_source_size_regex_retains_first_valid_measurement(self):
        rule=kinds(tree(r'\rule{prefix1pttail}{2pt}'),'rule')[0]
        self.assertEqual(rule.get('width'),(1.,'pt'))

    def test_empty_mandatory_measurement_means_zero_but_empty_optional_rejects(self):
        self.assertEqual(kinds(tree(r'\rule{}{1pt}'),'rule')[0].get('width'),(0.,'pt'))
        with self.assertRaises(ParseError):tree(r'\rule[]{1pt}{1pt}')

    def test_smash_optional_letters_empty_and_unknown_are_source_flags(self):
        cases=[(None,True,True),('t',True,False),('b',False,True),('tb',True,True),('bt',True,True),('',False,False),('q',False,False),('tq',False,False)]
        for letters,height,depth in cases:
            with self.subTest(letters=letters):
                option='' if letters is None else '['+letters+']'
                node=kinds(tree('\\smash'+option+'{x}'),'smash')[0]
                self.assertEqual((node.get('smash_height'),node.get('smash_depth')),(height,depth))

    def test_genfrac_non_delimiter_arguments_are_ignored_as_source(self):
        frac=kinds(tree(r'\genfrac{a}{b}{}{0}{x}{y}'),'frac')[0]
        self.assertEqual((frac.get('left'),frac.get('right')),('',''))

    def test_color_argument_whitespace_is_not_silently_trimmed(self):
        for color in [' red','red ']:
            with self.subTest(color=color),self.assertRaises(ParseError):tree(r'\color{'+color+'}x')

    def test_color_is_text_color_option_does_not_consume_rest_of_formula(self):
        result=tree(r'\color{red}{x}y',color_is_text_color=True)
        color=kinds(result,'color')[0]
        self.assertEqual(glyphs(color),'x')
        self.assertEqual(glyphs(result),'xy')

    def test_current_color_is_retained_at_right_delimiter(self):
        node=kinds(tree(r'\left(x\color{red}y\right)'),'delimiters')[0]
        self.assertEqual(node.get('right_color'),'red')

    def test_font_declaration_breaks_at_infix_fraction(self):
        result=tree(r'{\rm x\over y}')
        frac=kinds(result,'frac')[0]
        self.assertEqual(glyphs(frac.children[0]),'x')
        self.assertEqual(glyphs(frac.children[1]),'y')
        self.assertEqual(glyphs(kinds(frac.children[0],'font')[0]),'x')


class FullArrayAndTagSourceTests(unittest.TestCase):
    def test_display_only_ams_environments_reject_inline_context(self):
        for env in ['align','align*','gather','gather*','split','equation','equation*','alignat','CD']:
            header='{1}' if env=='alignat' else ''
            tex='\\begin{'+env+'}'+header+'x\\end{'+env+'}'
            with self.subTest(env=env),self.assertRaises(ParseError):tree(tex)

    def test_each_cell_has_its_own_local_namespace(self):
        with self.assertRaises(ParseError):tree(r'\begin{matrix}\def\localprobe{x}\localprobe&\localprobe\end{matrix}')
        self.assertEqual(glyphs(tree(r'\begin{matrix}\gdef\globalprobe{x}\globalprobe&\globalprobe\end{matrix}')),'xx')

    def test_top_level_tag_parentheses_and_star(self):
        for command,expected in [(r'\tag','(E)'),(r'\tag*','E')]:
            node=kinds(tree('x'+command+'{E}',display_mode=True),'tag')[0]
            self.assertEqual([glyphs(c) for c in node.children],['x',expected])

    def test_tag_rejects_duplicate_or_inline_context(self):
        with self.assertRaises(ParseError):tree(r'x\tag{A}\tag{B}',display_mode=True)
        with self.assertRaises(ParseError):tree(r'x\tag{A}')

    def test_automatic_manual_and_suppressed_row_tags(self):
        result=tree(r'\begin{align}a&=b\\c&=d\nonumber\\e&=f\tag{E}\end{align}',display_mode=True)
        array=kinds(result,'array')[0];tags=array.get('tags')
        self.assertEqual(len(tags),3)
        self.assertIs(tags[0],True);self.assertIs(tags[1],False)
        self.assertIsInstance(tags[2],Node);self.assertEqual(glyphs(tags[2]),'(E)')

    def test_starred_ams_rows_allow_manual_but_do_not_auto_number(self):
        array=kinds(tree(r'\begin{align*}a&=b\\c&=d\tag{D}\end{align*}',display_mode=True),'array')[0]
        self.assertIs(array.get('tags')[0],False)
        self.assertEqual(glyphs(array.get('tags')[1]),'(D)')

    def test_regular_array_tag_remains_a_formula_tag(self):
        result=tree(r'\begin{matrix}x\tag{T}\end{matrix}',display_mode=True)
        self.assertEqual(len(kinds(result,'tag')),1)
        self.assertIsNone(kinds(result,'array')[0].get('tags'))

    def test_alignat_explicit_column_limit_and_source_gaps(self):
        array=kinds(tree(r'\begin{alignedat}{1}a&=b\end{alignedat}'),'array')[0]
        self.assertEqual(array.get('cols'),('r','l'))
        self.assertEqual(array.get('col_separation'),'alignat')
        with self.assertRaises(ParseError):tree(r'\begin{alignedat}{1}a&b&c\end{alignedat}')

    def test_subarray_only_l_c_and_first_row_single_column(self):
        for tex in [r'\begin{subarray}{r}x\end{subarray}',r'\begin{subarray}{cc}x\end{subarray}',r'\begin{subarray}{c}x&y\end{subarray}']:
            with self.subTest(tex=tex),self.assertRaises(ParseError):tree(tex)

    def test_row_gap_space_after_cr_disables_optional_scanning(self):
        array=kinds(tree(r'\begin{matrix}a\\ [2pt]b\end{matrix}'),'array')[0]
        self.assertIsNone(array.get('row_gaps')[0])
        self.assertEqual(glyphs(array.children[1]),'[2pt]b')

    def test_cd_arrows_and_fixed_terminal_empty_row(self):
        result=tree(r'\begin{CD}A@>f>g>B\\@VhVkV@AlAmA\\C@<n<o<D\end{CD}',display_mode=True)
        array=kinds(result,'array')[0]
        self.assertEqual([len(row.children) for row in array.children],[3,3,3,0])
        self.assertEqual([node.value for node in kinds(result,'cdarrow')],['>','V','A','<'])
        self.assertEqual(array.get('col_separation'),'CD')

    def test_cd_unlabelled_symbols_equal_pipe_and_dot(self):
        for marker in '=|.':
            with self.subTest(marker=marker):self.assertEqual(kinds(tree(r'\begin{CD}A@'+marker+r'B\end{CD}',display_mode=True),'cdarrow')[0].value,marker)

    def test_cd_invalid_marker_or_missing_label_terminator_rejects(self):
        for tex in [r'\begin{CD}A@X B\end{CD}',r'\begin{CD}A@>f>B\end{CD}']:
            with self.subTest(tex=tex),self.assertRaises(ParseError):tree(tex,display_mode=True)


class TrustStrictAndErrorSourceTests(unittest.TestCase):
    def test_untrusted_command_is_visible_and_does_not_hide_rest_of_formula(self):
        result=tree(r'a+\href{javascript:bad()}{b}+c',trust=False)
        refused=kinds(result,'unsupported')
        self.assertEqual([n.value for n in refused],[r'\href'])
        self.assertTrue(refused[0].get('rejected'))
        self.assertEqual(glyphs(result),'a++c')

    def test_python_trust_callback_receives_validated_url_protocol(self):
        calls=[]
        def trust(context):calls.append(context);return context.get('protocol')=='https'
        result=tree(r'\href{HTTPS://example.invalid/x}{x}',trust=trust)
        self.assertEqual(glyphs(result),'x')
        self.assertEqual(calls[0]['command'],r'\href')
        self.assertEqual(calls[0]['protocol'],'https')

    def test_encoded_or_invalid_protocol_is_rejected_before_callback(self):
        calls=[]
        result=tree(r'\href{javascript&#58;bad}{x}',trust=lambda c:calls.append(c) or True)
        self.assertEqual(calls,[])
        self.assertEqual(kinds(result,'unsupported')[0].value,r'\href')

    def test_html_data_escaped_comma_and_expanded_raw_style(self):
        result=tree(r'\def\shade{blue}\htmlStyle{color:\shade}{x}\htmlData{a=x{,}y,b=z=q}{y}',trust=True)
        html=kinds(result,'html')
        self.assertEqual(dict(html[0].get('attributes')),{'style':'color:blue'})
        self.assertEqual(dict(html[1].get('attributes')),{'data-a':'x,y','data-b':'z=q'})

    def test_image_dimensions_unitless_bp_alt_and_url_percent(self):
        image=kinds(tree(r'\includegraphics[width=12,height=1em,totalheight=2em]{https://example.invalid/a%20b.png}',trust=True),'image')[0]
        self.assertEqual(image.get('width'),(12.,'bp'))
        self.assertEqual(image.get('alt'),'a%20b')
        self.assertEqual(image.get('height'),(1.,'em'))
        self.assertEqual(image.get('totalheight'),(2.,'em'))

    def test_unknown_command_no_throw_preserves_formula_and_error_color(self):
        result=tree(r'a+\unknownprobe+b',throw_on_error=False,error_color='#123456')
        node=kinds(result,'unsupported')[0]
        self.assertEqual((node.value,node.get('color')),(r'\unknownprobe','#123456'))
        self.assertEqual(glyphs(result),'a++b')
        with self.assertRaises(ParseError):tree(r'{a',throw_on_error=False)

    def test_nonvisual_htmlmathml_alternative_is_still_parsed_and_validated(self):
        # parseArguments parses both groups before htmlmathml's handler chooses
        # an output branch. Static HTML selection cannot skip source errors.
        with self.assertRaises(ParseError):tree(r'\html@mathml{x}{\unknownprobe}')

    def test_strict_html_extension_error_precedes_trust_callback(self):
        calls=[]
        with self.assertRaises(ParseError):parse(r'\htmlStyle{color:red}{x}',strict='error',trust=lambda c:calls.append(c) or True)
        self.assertEqual(calls,[])

    def test_strict_warn_ignore_error_and_python_callback(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always');parse('\u00e1',strict='warn')
        self.assertTrue(any(issubclass(w.category,MathWarning) and 'unicodeTextInMathMode' in str(w.message) for w in caught))
        with self.assertRaises(ParseError):parse('\u00e1',strict='error')
        calls=[]
        parse('\u00e1',strict=lambda code,message,token:calls.append((code,token.position)) or 'ignore')
        self.assertEqual(calls[0],('unicodeTextInMathMode',0))

    def test_strict_report_false_callback_failure_selects_no_newline(self):
        def strict(*args):raise RuntimeError('caller')
        result=parse(r'a\\b',display_mode=True,strict=strict)
        self.assertEqual(kinds(result,'linebreak'),[])
        self.assertEqual(glyphs(result),'ab')

    def test_strict_report_true_callback_failure_propagates(self):
        def strict(*args):raise RuntimeError('caller')
        with self.assertRaisesRegex(RuntimeError,'caller'):parse('\u00e1',strict=strict)

    def test_lexical_and_parser_errors_also_report_utf16_positions(self):
        for tex,position,utf16 in [('\U0001d538'+'\\',1,2),('\U0001d538'+r'\unknownprobe',1,2)]:
            with self.subTest(tex=tex):
                with self.assertRaises(ParseError) as caught:tree(tex)
                self.assertEqual((caught.exception.position,caught.exception.utf16_position),(position,utf16))

    def test_unknown_control_error_token_length_is_source_control_word_length(self):
        with self.assertRaises(ParseError) as caught:tree(r'x\unknownprobe')
        self.assertEqual(caught.exception.length,len(r'\unknownprobe'))


if __name__=='__main__':unittest.main()
