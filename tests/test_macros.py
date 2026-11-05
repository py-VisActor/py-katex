"""KaTeX 0.18.11 Lexer/Namespace/MacroExpander and macro source assertions.

No expected expansion is generated from the Python candidate. P2: compile only.
"""
import copy
import unittest
from py_katex.macros import lex, Expander, Macro, Token
from py_katex.parser import parse
from py_katex.model import ParseError


def glyphs(node):
    return (node.value if node.kind=='symbol' else '')+''.join(glyphs(c) for c in node.children)


def expanded(gullet):
    output=[]
    while True:
        token=gullet.next()
        if token.text=='EOF':return output
        output.append(token.text)


class SourceLexerTests(unittest.TestCase):
    def test_control_word_consumes_trailing_space(self):
        tokens=lex(r'a \alpha  b')
        self.assertEqual([t.text for t in tokens],['a',' ',r'\alpha','b'])
        self.assertEqual([t.position for t in tokens],[0,1,2,10])

    def test_control_symbols_do_not_consume_following_space(self):
        self.assertEqual([t.text for t in lex(r'\% x\{y\}')],[r'\%',' ','x',r'\{','y',r'\}'])

    def test_comments_discard_newline_without_inserting_space(self):
        self.assertEqual([t.text for t in lex('a% hidden\r\nb% eof')],['a','b'])

    def test_whitespace_collapses_and_escaped_space_has_own_token(self):
        self.assertEqual([t.text for t in lex('a\r\n\t b\\ \t c')],['a',' ','b',r'\ ','c'])

    def test_combining_marks_are_in_same_source_token(self):
        self.assertEqual([t.text for t in lex('a\u0301b')],['a\u0301','b'])

    def test_wide_character_uses_python_codepoint_position(self):
        tokens=lex('\U0001d538+x')
        self.assertEqual([t.position for t in tokens],[0,1,2])

    def test_control_word_includes_at_sign(self):
        self.assertEqual([t.text for t in lex(r'\@firstoftwo{a}{b}')],[r'\@firstoftwo','{','a','}','{','b','}'])

    def test_verb_is_single_token_even_with_percent_and_braces(self):
        text=r'\verb|\foo{%}|'
        self.assertEqual([t.text for t in lex(text)],[text])

    def test_lexical_invalid_characters_and_bare_backslash_reject(self):
        for source in ['\\','\x00','\x1f','\ud800','\ue000']:
            with self.subTest(source=repr(source)),self.assertRaises(ParseError):lex(source)

    def test_unterminated_verb_rejects(self):
        with self.assertRaises(ParseError):lex(r'\verb|unclosed')


class SourceMacroDefinitionTests(unittest.TestCase):
    def test_user_macros_substitute_numbered_balanced_arguments(self):
        self.assertEqual(glyphs(parse(r'\pair{a+b}{c}',macros={r'\pair':r'#2+#1'})),'c+a+b')

    def test_user_macros_do_not_mutate_input_mapping(self):
        macros={r'\foo':'x'};before=copy.deepcopy(macros)
        self.assertEqual(glyphs(parse(r'\foo',macros=macros)),'x')
        self.assertEqual(macros,before)

    def test_nested_macro_expansion_is_lazy_and_numbered(self):
        self.assertEqual(glyphs(parse(r'\outer{a}',macros={r'\outer':r'\inner{#1}',r'\inner':r'#1+#1'})),'a+a')

    def test_empty_macro_is_defined_not_missing(self):
        self.assertEqual(glyphs(parse(r'a\emptyMacro b',macros={r'\emptyMacro':''})),'ab')

    def test_def_local_namespace_restores_outer_definition(self):
        self.assertEqual(glyphs(parse(r'\def\foo{a}{\def\foo{b}\foo}\foo')),'ba')

    def test_def_does_not_escape_group_when_previously_undefined(self):
        with self.assertRaises(ParseError):parse(r'{\def\foo{a}}\foo')

    def test_gdef_survives_group_but_not_another_request(self):
        self.assertEqual(glyphs(parse(r'{\gdef\foo{b}}\foo')),'b')
        with self.assertRaises(ParseError):parse(r'\foo')

    def test_global_definition_overrides_all_nested_undo_levels(self):
        text=r'\def\foo{a}{\def\foo{b}{\gdef\foo{c}}\foo}\foo'
        self.assertEqual(glyphs(parse(text)),'cc')

    def test_explicit_global_prefix_and_long_prefix(self):
        self.assertEqual(glyphs(parse(r'{\global\def\foo{a}}\foo')),'a')
        self.assertEqual(glyphs(parse(r'\long\def\foo#1{#1}\foo{x}')),'x')

    def test_def_replacement_is_not_expanded_until_invocation(self):
        self.assertEqual(glyphs(parse(r'\def\a{x}\def\b{\a}\def\a{y}\b')),'y')

    def test_edef_expands_replacement_at_definition_time(self):
        self.assertEqual(glyphs(parse(r'\def\a{x}\edef\b{\a}\def\a{y}\b')),'x')

    def test_xdef_has_expansion_and_global_scope(self):
        self.assertEqual(glyphs(parse(r'\def\a{x}{\xdef\b{\a}}\def\a{y}\b')),'x')

    def test_def_delimited_parameters_include_nested_groups(self):
        self.assertEqual(glyphs(parse(r'\def\foo#1,#2;{#2+#1}\foo {a+b},c;')),'c+a+b')

    def test_def_literal_parameter_prefix_must_match(self):
        self.assertEqual(glyphs(parse(r'\def\foo a#1;{#1}\foo ax;')),'x')
        with self.assertRaises(ParseError):parse(r'\def\foo a#1;{#1}\foo bx;')

    def test_def_parameters_must_be_sequential_and_at_most_nine(self):
        for tex in [r'\def\foo#2{x}',r'\def\foo#0{x}',r'\def\foo#1#3{x}',r'\def\foo#1#2#3#4#5#6#7#8#9#10{x}']:
            with self.subTest(tex=tex),self.assertRaises(ParseError):parse(tex)

    def test_macro_argument_missing_or_unbalanced_rejects(self):
        for tex in [r'\def\foo#1{#1}\foo',r'\def\foo#1{#1}\foo{x']:
            with self.subTest(tex=tex),self.assertRaises(ParseError):parse(tex)

    def test_newcommand_renewcommand_and_providecommand(self):
        tex=r'\newcommand{\foo}[1]{#1+x}\foo{a}\renewcommand{\foo}[1]{#1+y}\foo{b}\providecommand{\foo}{z}\foo{c}'
        self.assertEqual(glyphs(parse(tex)),'a+xb+yc+y')

    def test_newcommand_optional_count_allows_surrounding_whitespace(self):
        self.assertEqual(glyphs(parse(r'\newcommand{\foo}[ 2 ]{#2#1}\foo ab')),'ba')

    def test_source_newcommand_count_ten_consumes_ten_arguments(self):
        # Pinned katex-spec.ts explicitly accepts [10], unlike def parameter numbering.
        self.assertEqual(glyphs(parse(r'\newcommand\foo[10]{#1^2}\foo 0123456789')),'02')

    def test_source_def_can_define_noncontrol_active_tokens(self):
        self.assertEqual(glyphs(parse(r'\def0{x}0')),'x')
        self.assertEqual(glyphs(parse(r'\def~{x}~')),'x')

    def test_newcommand_and_renewcommand_existence_validation(self):
        for tex in [r'\newcommand{\frac}{x}',r'\newcommand{\alpha}{x}',r'\renewcommand{\notDefinedYet}{x}']:
            with self.subTest(tex=tex),self.assertRaises(ParseError):parse(tex)

    def test_newcommand_optional_default_is_source_unsupported(self):
        # macros.ts explicitly has TODO for optional default arguments.
        with self.assertRaises(ParseError):parse(r'\newcommand{\foo}[1][x]{#1}\foo')

    def test_let_captures_existing_macro_meaning(self):
        self.assertEqual(glyphs(parse(r'\def\a{x}\let\b=\a\def\a{y}\b')),'x')

    def test_let_captures_primitive_function_without_late_macro_expansion(self):
        tree=parse(r'\let\foo=\frac\def\frac{x}\foo12')
        self.assertEqual(tree.children[0].kind,'frac')
        self.assertEqual(glyphs(tree),'12')

    def test_explicit_begingroup_and_endgroup_scope(self):
        self.assertEqual(glyphs(parse(r'\def\a{x}\begingroup\def\a{y}\a\endgroup\a')),'yx')

    def test_environment_namespace_restores_local_definitions(self):
        self.assertEqual(glyphs(parse(r'\def\a{x}\begin{matrix}\def\a{y}\a\end{matrix}\a')),'yx')

    def test_invalid_macro_configuration_types_reject(self):
        for macros in [{r'\a':1},{1:'x'}]:
            with self.subTest(macros=macros),self.assertRaises(ParseError):parse('x',macros=macros)


class SourceContextMacroTests(unittest.TestCase):
    def test_first_second_and_ifnextchar_context_branches(self):
        self.assertEqual(glyphs(parse(r'\@firstoftwo{a}{b}\@secondoftwo{c}{d}')),'ad')
        self.assertEqual(glyphs(parse(r'\@ifnextchar x{a}{b} x')),'ax')
        self.assertEqual(glyphs(parse(r'\@ifnextchar x{a}{b} y')),'by')

    def test_text_or_math_uses_current_mode(self):
        self.assertEqual(glyphs(parse(r'\TextOrMath{a}{b}\text{\TextOrMath{c}{d}}')),'bc')

    def test_expandafter_expands_second_token_before_first(self):
        tex=r'\def\a{x}\def\b#1{#1}\expandafter\b\a'
        self.assertEqual(glyphs(parse(tex)),'x')

    def test_noexpand_prevents_edef_replacement_expansion(self):
        tex=r'\def\a{x}\edef\b{\noexpand\a}\def\a{y}\b'
        self.assertEqual(glyphs(parse(tex)),'y')

    def test_noexpand_normal_parse_relaxes_but_edef_preserves_original_token(self):
        self.assertEqual(glyphs(parse(r'\def\a{x}\noexpand\a')),'')
        self.assertEqual(glyphs(parse(r'\def\a{x}\xdef\b{\a\noexpand\a}\def\a{y}\b')),'xy')

    def test_unexpandable_let_alias_survives_edef_with_late_name_lookup(self):
        # Exact semantics asserted by pinned katex-spec.ts let section.
        self.assertEqual(glyphs(parse(r'\let\foo=x\edef\bar{\foo}\def\foo{y}\bar')),'y')
        self.assertEqual(glyphs(parse(r'\let\foo=x\noexpand\foo')),'x')

    def test_char_decimal_octal_hex_and_backtick(self):
        # Use separate source literals to avoid a Python quote escaping artifact.
        for source in [r'\char65',"\\char'101",r'\char"41',r'\char`A']:
            with self.subTest(source=source):self.assertEqual(glyphs(parse(source)),'A')

    def test_literal_hash_in_builtin_color_macro_is_not_parameter(self):
        tree=parse(r'\blue{x}')
        color=next(n for n in tree.children if n.kind=='color')
        self.assertEqual(color.value,'#6495ed')

    def test_source_static_aliases_have_nonliteral_symbol_results(self):
        # Fixed __parse diagnostic: HTML visual branch overlays \@not on '=';
        # only its separate MathML branch contains the single U+2260 character.
        # symbols.ts gives \@not Main glyph U+E020; retain that real font glyph.
        tree=parse(r'\ne\Alpha\R')
        self.assertEqual(glyphs(tree),'\ue020=AR')
        def descendants(node):
            yield node
            for child in node.children:yield from descendants(child)
        self.assertEqual([n.value for n in descendants(tree) if n.kind=='lap'],['rlap'])

    def test_dots_selects_centered_for_binary_and_low_for_comma(self):
        self.assertIn('\u22ef',glyphs(parse(r'a\dots+b')))
        self.assertIn('\u2026',glyphs(parse(r'a\dots,b')))

    def test_terminal_context_commands_have_no_static_output(self):
        self.assertEqual(glyphs(parse(r'a\message{hidden}\errmessage{hidden}\show\alpha b')),'ab')

    def test_recursive_and_mutually_recursive_expansion_budgets(self):
        cases=[(r'\foo',{r'\foo':r'\foo'}),(r'\a',{r'\a':r'\b',r'\b':r'\a'})]
        for tex,macros in cases:
            with self.subTest(tex=tex):
                with self.assertRaises(ParseError) as caught:parse(tex,macros=macros,max_expand=12)
                self.assertEqual(caught.exception.code,'MAX_EXPAND')

    def test_macro_expansion_budget_includes_context_helpers(self):
        with self.assertRaises(ParseError) as caught:parse(r'\@firstoftwo{x}{y}',max_expand=0)
        self.assertEqual(caught.exception.code,'MAX_EXPAND')

    def test_queue_budget_limits_exponential_replacement(self):
        with self.assertRaises(ParseError) as caught:
            g=Expander(r'\a',macros={r'\a':r'\b\b',r'\b':'x'*100},max_tokens=50)
            expanded(g)
        self.assertEqual(caught.exception.code,'MAX_TOKENS')

    def test_macro_invocation_and_substitution_keep_original_source_positions(self):
        tree=parse(r'\foo{x}',macros={r'\foo':'a#1'})
        self.assertEqual([(c.value,c.position) for c in tree.children],[('a',0),('x',5)])

    def test_scope_removal_is_not_confused_with_an_empty_macro(self):
        g=Expander('');g.define(r'\a',Macro(tuple(lex('x'))));g.begin();g.define(r'\a',Macro(()))
        g.push([Token(r'\a')]);self.assertEqual(expanded(g),[])
        g.end_group();g.push([Token(r'\a')]);self.assertEqual(expanded(g),['x'])


if __name__=='__main__':unittest.main()
