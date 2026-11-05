"""Independent fixed-source macro-state and public-context expectations."""
import copy
import math
import unittest
from py_katex.parser import parse
from py_katex.macros import Macro,Token,MacroState,Expander
from py_katex.model import ParseError


def tree(tex,**options):return parse(tex,strict='ignore',**options)
def glyphs(node):return (node.value if node.kind=='symbol' else '')+''.join(glyphs(c) for c in node.children)
def walk(node):
    yield node
    for child in node.children:yield from walk(child)


class FullPersistentNamespaceTests(unittest.TestCase):
    def test_ordinary_macro_mapping_stays_immutable_under_native_contract(self):
        macros={r'\probe':'x'};before=copy.deepcopy(macros)
        self.assertEqual(glyphs(tree(r'\gdef\probe{y}\probe',macros=macros)),'y')
        self.assertEqual(macros,before)

    def test_explicit_state_persists_global_but_not_local_definitions(self):
        state=MacroState()
        tree(r'\def\localprobe{x}\gdef\globalprobe{y}',macro_state=state)
        self.assertEqual(glyphs(tree(r'\globalprobe',macro_state=state)),'y')
        with self.assertRaises(ParseError):tree(r'\localprobe',macro_state=state)

    def test_global_group_persists_top_level_definitions_in_explicit_state(self):
        state=MacroState()
        tree(r'\def\probe{x}',macro_state=state,global_group=True)
        self.assertEqual(glyphs(tree(r'\probe',macro_state=state)),'x')

    def test_state_does_not_implicitly_become_global_process_state(self):
        first=MacroState();second=MacroState()
        tree(r'\gdef\probe{x}',macro_state=first)
        with self.assertRaises(ParseError):tree(r'\probe',macro_state=second)
        with self.assertRaises(ParseError):tree(r'\probe')

    def test_global_assignment_survives_source_parse_error_but_local_undo_closes(self):
        state=MacroState()
        with self.assertRaises(ParseError):tree(r'\gdef\persistent{x}{\def\localprobe{y}',macro_state=state)
        self.assertEqual(glyphs(tree(r'\persistent',macro_state=state)),'x')
        with self.assertRaises(ParseError):tree(r'\localprobe',macro_state=state)

    def test_color_and_tag_internal_flags_are_cleaned_at_job_boundary(self):
        state=MacroState()
        tree(r'\color{red}x\tag{E}',macro_state=state,global_group=True,display_mode=True)
        self.assertTrue(all(name not in state.definitions for name in [r'\color',r'\current@color',r'\df@tag']))
        result=tree(r'x',macro_state=state,display_mode=True)
        self.assertFalse(any(n.kind=='tag' for n in walk(result)))

    def test_state_initial_string_definition_and_clear(self):
        state=MacroState({r'\probe':'x'})
        self.assertEqual(glyphs(tree(r'\probe',macro_state=state)),'x')
        state.clear()
        with self.assertRaises(ParseError):tree(r'\probe',macro_state=state)


class FullDefinitionBoundaryTests(unittest.TestCase):
    def test_macro_prefix_expands_alias_before_matching_definition(self):
        self.assertEqual(glyphs(tree(r'\def\DEF{\def}\global\DEF\foo{x}\foo')),'x')

    def test_let_open_brace_can_supply_primitive_root_group(self):
        self.assertEqual(glyphs(tree(r'\let\foo{\sqrt\foo1}')),'1')

    def test_futurelet_captures_third_token_and_reinserts_middle_and_third(self):
        self.assertEqual(glyphs(tree(r'\futurelet\probe\relax x\probe')),'xx')

    def test_futurelet_captures_macro_meaning_before_middle_redefines_it(self):
        tex=r'\def\a{x}\def\change{\def\a{y}}\futurelet\saved\change\a\saved'
        self.assertEqual(glyphs(tree(tex)),'yx')

    def test_global_futurelet_and_global_let_survive_group(self):
        self.assertEqual(glyphs(tree(r'{\global\futurelet\saved\relax x}\saved')),'xx')
        self.assertEqual(glyphs(tree(r'{\global\let\saved=x}\saved')),'x')

    def test_prefix_combinations_global_long_preserve_definition_scope(self):
        self.assertEqual(glyphs(tree(r'{\long\global\long\def\probe{x}}\probe')),'x')

    def test_def_hash_before_left_brace_is_copied_to_replacement_end(self):
        self.assertEqual(glyphs(tree(r'\def\probe#1#{#1}\probe x{y}')),'xy')
        self.assertEqual(glyphs(tree(r'\def\probe#{x}\probe{y}')),'xy')

    def test_def_delimited_arguments_preserve_source_brace_matching(self):
        self.assertEqual(glyphs(tree(r'\def\probe#1,#2;{#2+#1}\probe {a+b},c;')),'c+a+b')

    def test_string_macro_parameter_count_requires_contiguous_numbers(self):
        # _getExpansion infers while #1,#2,... occur, not maximum digit.
        with self.assertRaises(ParseError):tree(r'\probe ab',macros={r'\probe':'#2'})

    def test_newcommand_dynamic_expands_during_edef_context(self):
        self.assertEqual(glyphs(tree(r'\edef\saved{\newcommand\probe{x}}\probe')),'x')

    def test_newcommand_definition_must_see_all_function_and_text_symbol_names(self):
        for command in [r'\limits',r'\textdollar',r'\sqrt']:
            with self.subTest(command=command),self.assertRaises(ParseError):tree(r'\newcommand'+command+'{x}')

    def test_newcommand_ten_arguments_and_whitespace_count(self):
        self.assertEqual(glyphs(tree(r'\newcommand\probe[ 10 ]{#1}\probe 0123456789')),'0')

    def test_source_noexpand_difference_normal_parse_versus_edef(self):
        self.assertEqual(glyphs(tree(r'\def\a{x}\noexpand\a')),'')
        self.assertEqual(glyphs(tree(r'\def\a{x}\edef\b{\noexpand\a}\def\a{y}\b')),'y')

    def test_let_unexpandable_alias_not_expanded_inside_edef(self):
        self.assertEqual(glyphs(tree(r'\let\probe=x\edef\saved{\probe}\def\probe{y}\saved')),'y')

    def test_let_can_capture_a_builtin_dynamic_macro_function(self):
        self.assertEqual(glyphs(tree(r'\let\maker=\newcommand\maker\probe{x}\probe')),'x')

    def test_braket_replaces_all_bars_but_set_only_the_first(self):
        braket=tree(r'\Braket{x|y|z}')
        delimiter=next(n for n in walk(braket) if n.kind=='delimiters')
        self.assertEqual(len(delimiter.get('middle')),2)
        one=tree(r'\Set{x|y|z}')
        delimiter=next(n for n in walk(one) if n.kind=='delimiters')
        self.assertEqual(len(delimiter.get('middle')),1)

    def test_braket_double_bars_and_previous_active_bar_restore(self):
        result=tree(r'\def|{q}\Braket{x||y}|')
        delimiter=next(n for n in walk(result) if n.kind=='delimiters')
        self.assertEqual(delimiter.get('middle'),('|',))
        self.assertTrue(glyphs(result).endswith('q'))

    def test_reentrant_active_bar_in_internal_braket_middle_hits_expansion_budget(self):
        # macros.ts braketHelper installs | before expanding its middle body.
        with self.assertRaises(ParseError) as caught:
            tree(r'\bra@ket{\left\langle}{\middle|}{\middle\Vert}{\right\rangle}{x|y}',max_expand=50)
        self.assertEqual(caught.exception.code,'MAX_EXPAND')


class FullMacroExpansionObjectAndCallbackTests(unittest.TestCase):
    def test_native_macro_forward_order_and_source_dictionary_reverse_order(self):
        native=Macro((Token('a'),Token('b')))
        declared={'tokens':[{'text':'b'},{'text':'a'}],'numArgs':0}
        for definition in [native,declared]:
            with self.subTest(definition=definition):self.assertEqual(glyphs(tree(r'\probe',macros={r'\probe':definition})),'ab')

    def test_source_dictionary_numbered_arguments_and_delimiters(self):
        definition={'tokens':[Token('1'),Token('#'),Token('+'),Token('2'),Token('#')],'numArgs':2,'delimiters':[[],[','],[';']]}
        self.assertEqual(glyphs(tree(r'\probe a,b;',macros={r'\probe':definition})),'b+a')

    def test_expansion_object_unexpandable_is_preserved_during_edef(self):
        definition={'tokens':[Token('x')],'numArgs':0,'unexpandable':True}
        self.assertEqual(glyphs(tree(r'\edef\saved{\probe}\def\probe{y}\saved',macros={r'\probe':definition})),'y')

    def test_callback_may_return_string_native_macro_or_expansion_dictionary(self):
        for value in ['ab',Macro((Token('a'),Token('b'))),{'tokens':[Token('b'),Token('a')],'numArgs':0}]:
            with self.subTest(value=value):self.assertEqual(glyphs(tree(r'\probe',macros={r'\probe':lambda context,value=value:value})),'ab')

    def test_consume_args_returns_source_reverse_stack_order(self):
        seen=[]
        def callback(context):
            args=context.consumeArgs(2);seen.extend([[t.text for t in arg] for arg in args])
            return {'tokens':args[1]+[Token('+')]+args[0],'numArgs':0}
        self.assertEqual(glyphs(tree(r'\probe{ab}{cd}',macros={r'\probe':callback})),'ab+cd')
        self.assertEqual(seen,[['b','a'],['d','c']])

    def test_delimited_consume_arg_retains_leading_space_after_control_symbol(self):
        seen=[]
        def callback(context):
            arg=context.consumeArg([',']);seen.extend(t.text for t in arg.tokens);return 'x'
        self.assertEqual(glyphs(tree(r'\? a,',macros={r'\?':callback})),'x')
        self.assertEqual(seen,['a',' '])

    def test_future_is_unexpanded_and_expand_after_future_performs_one_step(self):
        seen=[]
        def callback(context):
            seen.append(context.future().text);seen.append(context.expandAfterFuture().text);return ''
        self.assertEqual(glyphs(tree(r'\probe\later',macros={r'\probe':callback,r'\later':'xy'})),'xy')
        self.assertEqual(seen,[r'\later','x'])

    def test_expand_once_distinguishes_empty_success_from_false(self):
        seen=[]
        def callback(context):seen.append(context.expandOnce());return ''
        self.assertEqual(glyphs(tree(r'\probe\blank x',macros={r'\probe':callback,r'\blank':''})),'x')
        self.assertEqual(seen,[0]);self.assertIsNot(seen[0],False)

    def test_expand_once_reports_number_of_replacement_tokens(self):
        seen=[]
        def callback(context):seen.append(context.expandOnce());return ''
        self.assertEqual(glyphs(tree(r'\probe\later',macros={r'\probe':callback,r'\later':'xy'})),'xy')
        self.assertEqual(seen,[2])

    def test_expand_tokens_accepts_reverse_input_and_returns_forward_output(self):
        def callback(context):return ''.join(t.text for t in context.expandTokens([Token('b'),Token('a')]))
        self.assertEqual(glyphs(tree(r'\probe',macros={r'\probe':callback})),'ab')

    def test_pop_token_does_not_expand_and_push_token_precedes_remaining_input(self):
        seen=[]
        def callback(context):
            token=context.popToken();seen.append(token.text);context.pushToken(token);return 'a'
        self.assertEqual(glyphs(tree(r'\probe\later',macros={r'\probe':callback,r'\later':'x'})),'ax')
        self.assertEqual(seen,[r'\later'])

    def test_push_tokens_uses_source_reverse_stack_convention(self):
        def callback(context):context.pushTokens([Token('b'),Token('a')]);return ''
        self.assertEqual(glyphs(tree(r'\probe',macros={r'\probe':callback})),'ab')

    def test_consume_spaces_does_not_eat_next_nonspace_token(self):
        seen=[]
        def callback(context):context.consumeSpaces();seen.append(context.future().text);return ''
        self.assertEqual(glyphs(tree(r'\?   x',macros={r'\?':callback})),'x')
        self.assertEqual(seen,['x'])

    def test_expand_next_token_recurses_and_removes_first_expanded_token(self):
        seen=[]
        def callback(context):token=context.expandNextToken();seen.append(token.text);return token.text
        self.assertEqual(glyphs(tree(r'\probe\later',macros={r'\probe':callback,r'\later':r'\last',r'\last':'xy'})),'xy')
        self.assertEqual(seen,['x'])

    def test_expand_macro_as_text_and_undefined_macro(self):
        seen=[]
        def callback(context):
            seen.extend([context.expandMacroAsText(r'\later'),context.expandMacro(r'\notDefinedProbe')]);return ''
        tree(r'\probe',macros={r'\probe':callback,r'\later':'xy'})
        self.assertEqual(seen,['xy',None])

    def test_is_defined_and_is_expandable_use_source_symbol_function_and_primitive_rules(self):
        seen=[]
        def callback(context):
            seen.extend([context.isDefined(r'\textdollar'),context.isDefined(r'\limits'),context.isExpandable(r'\frac'),context.isExpandable(r'\def'),context.isDefined(r'\notDefinedProbe')]);return ''
        tree(r'\probe',macros={r'\probe':callback})
        self.assertEqual(seen,[True,True,True,False,False])

    def test_namespace_context_get_set_local_and_global_definitions(self):
        seen=[]
        def callback(context):
            context.macros.beginGroup();context.macros.set(r'\localprobe','x');seen.append(context.macros.get(r'\localprobe'))
            context.macros.set(r'\globalprobe','y',True);context.macros.endGroup()
            seen.append(context.macros.get(r'\localprobe'));return ''
        self.assertEqual(glyphs(tree(r'\probe\globalprobe',macros={r'\probe':callback})),'y')
        self.assertEqual(seen,['x',None])

    def test_namespace_exposes_registered_builtin_dynamic_macro_definitions(self):
        seen=[]
        def callback(context):seen.extend([context.macros.has(r'\newcommand'),callable(context.macros.get(r'\newcommand'))]);return ''
        tree(r'\probe',macros={r'\probe':callback})
        self.assertEqual(seen,[True,True])

    def test_callback_sees_math_or_text_mode(self):
        seen=[]
        def callback(context):seen.append(context.mode);return 'x'
        tree(r'\probe\text{\probe}',macros={r'\probe':callback})
        self.assertEqual(seen,['math','text'])

    def test_callback_exception_propagates_without_becoming_empty_success(self):
        def callback(context):raise RuntimeError('macro caller')
        with self.assertRaisesRegex(RuntimeError,'macro caller'):tree(r'\probe',macros={r'\probe':callback})

    def test_callback_is_evaluated_before_source_expansion_count_check(self):
        seen=[]
        def callback(context):seen.append('called');return 'x'
        with self.assertRaises(ParseError):tree(r'\probe',macros={r'\probe':callback},max_expand=0)
        self.assertEqual(seen,['called'])

    def test_callback_result_and_declared_token_budgets_are_validated(self):
        for value in [None,12,lambda context:'x',{'tokens':12},{'tokens':[object()]},{'tokens':[],'numArgs':-1}]:
            with self.subTest(value=value),self.assertRaises(ParseError):tree(r'\probe',macros={r'\probe':lambda context,value=value:value})


class FullMacroBudgetAndValidationTests(unittest.TestCase):
    def test_zero_fractional_infinite_and_negative_clamped_max_expand(self):
        self.assertEqual(glyphs(tree('x',max_expand=0)),'x')
        self.assertEqual(glyphs(tree(r'\probe',macros={r'\probe':'x'},max_expand=1.5)),'x')
        self.assertEqual(glyphs(tree(r'\probe',macros={r'\probe':r'\later',r'\later':'x'},max_expand=math.inf)),'x')
        with self.assertRaises(ParseError):tree(r'\probe',macros={r'\probe':'x'},max_expand=-2)

    def test_node_and_depth_bounds_remain_when_expansion_limit_is_infinite(self):
        with self.assertRaises(ParseError):tree('x'*50,max_expand=math.inf,max_nodes=5)
        with self.assertRaises(ParseError):tree('{'*30+'x'+'}'*30,max_expand=math.inf,max_depth=8)

    def test_edef_output_counts_prevent_exponential_expansion(self):
        with self.assertRaises(ParseError) as caught:tree(r'\edef0{x}\edef0{00}\edef0{00}\edef0{00}\edef0{00}',max_expand=20)
        self.assertEqual(caught.exception.code,'MAX_EXPAND')

    def test_invalid_macro_state_or_nonnumeric_threshold_is_explicit(self):
        for options in [{'macro_state':{}},{'max_expand':math.nan},{'max_expand':True},{'max_expand':'Infinity'}]:
            with self.subTest(options=options),self.assertRaises(ParseError):tree('x',**options)


if __name__=='__main__':unittest.main()
