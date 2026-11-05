"""Full source registration denominator plus P3-produced independent semantics.

The oracle is mandatory: no native-generated expected values and no skips.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

from py_katex.parser import parse
from py_katex.model import Node, ParseError

ROOT=Path(__file__).resolve().parents[1]
FIXTURE_PATH=Path(__file__).with_name('full-parser-cases.json')
FIXTURES=json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))


def native_children(node):
    result=list(node.children)
    if node.kind=='array':result.extend(x for x in (node.get('tags') or ()) if isinstance(x,Node))
    return result


def semantic_glyphs(node):
    if node.kind=='symbol':return node.value
    if node.kind=='unsupported':return node.value
    if node.kind=='operator' and node.value:return node.value
    return ''.join(semantic_glyphs(child) for child in native_children(node))


FEATURES=frozenset(('frac','sqrt','array','image','html','tag','kern','rule','mathchoice','font','enclose','smash','phantom','reflect','pmb','space','linebreak'))
AST_KINDS=frozenset(('group','symbol','atom','scripts','frac','sqrt','operator','delimiters','sized_delimiter','font','text','style','size','mathchoice','color','space','kern','linebreak','accent','line','overunder','xarrow','phantom','smash','lap','rule','raise','vcenter','reflect','pmb','enclose','array','row','tag','html','image','cdarrow','cdlabel','unsupported','error'))


def projection(tree):
    features={};arrays=[];fractions=[];images=[];operators=[];fonts=[]
    def visit(node):
        if node.kind not in AST_KINDS:raise AssertionError('Unknown native AST kind cannot masquerade as empty successful semantics: '+node.kind)
        if node.kind in FEATURES:features[node.kind]=features.get(node.kind,0)+1
        if node.kind=='array':arrays.append([len(row.children) for row in node.children])
        if node.kind=='font':fonts.append(node.value)
        if node.kind=='frac':fractions.append({'bar':node.get('bar'),'style':node.get('style','auto')})
        if node.kind=='operator':operators.append({'glyphs':''.join(c for c in semantic_glyphs(node) if not c.isspace()),'symbol':bool(node.get('symbol')),'limits':bool(node.get('limits')),'alwaysHandle':bool(node.get('always_handle_supsub')),'small':bool(node.get('small'))})
        if node.kind=='image':images.append({'src':node.get('src',node.value),'alt':node.get('alt'),'width':node.get('width'),'height':node.get('height'),'totalheight':node.get('totalheight')})
        for child in native_children(node):visit(child)
    visit(tree)
    return {'glyphs':''.join(c for c in semantic_glyphs(tree) if not c.isspace()),'features':features,'arrays':arrays,'fractions':fractions,'images':images,'operators':operators,'fonts':fonts}


def native_options(case):
    source=case['settings']
    return dict(display_mode=source.get('displayMode',False),strict=source.get('strict','warn'),trust=source.get('trust',False),max_expand=source.get('maxExpand',1000),macros=case.get('macros'))


class FullRegistryInventoryTests(unittest.TestCase):
    def test_complete_locked_registration_and_macro_denominators(self):
        expected={'functions':312,'environments':33,'macros':339}
        self.assertEqual({k:len(v) for k,v in FIXTURES['coverage'].items()},expected)
        self.assertEqual(len(FIXTURES['cases']),684)
        self.assertEqual(FIXTURES['denominator']['registered'],345)

    def test_no_registration_dropped_or_replaced_by_native_inventory(self):
        source=json.loads((ROOT/'references/full-runtime-registry.json').read_text(encoding='utf-8'))
        for category in ('functions','environments','macros'):
            self.assertEqual(set(FIXTURES['coverage'][category]),set(source[category]))

    def test_each_entry_has_concrete_unique_case_and_legitimate_context(self):
        by_id={case['id']:case for case in FIXTURES['cases']}
        self.assertEqual(len(by_id),684)
        for category,mappings in FIXTURES['coverage'].items():
            for name,ids in mappings.items():
                with self.subTest(category=category,name=name):
                    self.assertTrue(ids)
                    for id in ids:
                        case=by_id[id]
                        self.assertEqual((case['registryCategory'],case['registryName']),(category,name))
                        self.assertTrue(case['tex'])
                        self.assertIn(case['context'],('legal_formula','actual_consumer','source_error_only','legal_environment','legal_macro_context'))

    def test_intrinsically_error_only_source_registration_is_explicit(self):
        guards=[case for case in FIXTURES['cases'] if case['context']=='source_error_only']
        self.assertEqual([c['registryName'] for c in guards],[r'\]'])
        self.assertFalse(guards[0]['expectedAccepted'])

    def test_all_twenty_dynamic_macro_names_have_argument_contexts(self):
        cases=[c for c in FIXTURES['cases'] if c['registryCategory']=='macros' and c['sourceType']=='function']
        self.assertEqual(len(cases),20)
        self.assertTrue(all(c['tex']!=c['registryName'] for c in cases))


class FullRegistryFixedSourceOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('PY_KATEX_FULL_ORACLE')
        if not path:raise RuntimeError('P3 must generate source oracle and set PY_KATEX_FULL_ORACLE; candidate-derived expectations are forbidden')
        cls.oracle=json.loads(Path(path).read_text(encoding='utf-8'))
        if cls.oracle['fixtureSha256']!=hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest():raise RuntimeError('Source oracle belongs to a different fixture candidate')
        cls.expected={case['id']:case for case in cls.oracle['cases']}

    def check_category(self,category):
        for case in FIXTURES['cases']:
            if case['registryCategory']!=category:continue
            with self.subTest(id=case['id'],command=case['registryName']):
                expected=self.expected[case['id']]
                self.assertEqual(expected['accepted'],case['expectedAccepted'],msg='Independent source rejected positive fixture; classify fixture/source anomaly, do not call this native compatibility')
                if not expected['accepted']:
                    with self.assertRaises(ParseError):parse(case['tex'],**native_options(case))
                    continue
                actual=parse(case['tex'],**native_options(case))
                self.assertEqual(actual.kind,'group')
                self.assertTrue(actual.children,msg='A nonempty legal source registry context must produce retained AST nodes')
                got=projection(actual);want=expected['semantics']
                self.assertEqual(got['glyphs'],want['glyphs'])
                self.assertEqual(got['features'],want['features'])
                self.assertEqual(got['arrays'],want['arrays'])
                self.assertEqual(got['fonts'],want['fonts'])
                self.assertEqual([x['bar'] for x in got['fractions']],[x['bar'] for x in want['fractions']])
                if case['sourceType'] in ('op','operatorname') or case['registryName']==r'\operatorname':self.assertEqual(got['operators'],want['operators'])
                if want['images']:
                    for native,source in zip(got['images'],want['images']):
                        self.assertEqual((native['src'],native['alt']),(source['src'],source['alt']))
                        for key in ('width','height','totalheight'):
                            self.assertEqual(tuple(native[key]),(source[key]['number'],source[key]['unit']))

    def test_all_312_functions_in_source_context_have_expected_semantics(self):self.check_category('functions')
    def test_all_33_environments_have_source_rows_and_semantics(self):self.check_category('environments')
    def test_all_339_macros_have_source_expansion_semantics(self):self.check_category('macros')

    def test_source_oracle_registry_and_case_count_match_frozen_inputs(self):
        self.assertEqual(self.oracle['registry'],{'functions':312,'environments':33,'macros':339})
        self.assertEqual(set(self.expected),{case['id'] for case in FIXTURES['cases']})
        self.assertEqual(self.oracle['unexpectedFixtureAcceptance'],[])


if __name__=='__main__':unittest.main()
