import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_as2_semantic_index import mask_comments_strings
from as2_reference_scopes import lexical_function_scopes, scope_context


class ReferenceScopeTests(unittest.TestCase):
    def context(self, source, needle, occurrence=0):
        masked = mask_comments_strings(source)
        start = -1
        for _ in range(occurrence + 1):
            start = masked.index(needle, start + 1)
        return scope_context(masked, lexical_function_scopes(masked),
                             start, start + len(needle))

    def test_named_function_parameter_and_body(self):
        source = 'function load(suffix:String) { return suffix; }'
        param = self.context(source, 'suffix')
        body = self.context(source, 'suffix', 1)
        self.assertEqual(param['context'], 'parameter_declaration_candidate')
        self.assertEqual(body['context'], 'function_body_reference')
        self.assertEqual(param['scope_candidate']['name_sha256'],
                         hashlib.sha256(b'load').hexdigest())
        self.assertNotIn('load', str(param))

    def test_assigned_function_and_nested_scope(self):
        source = 'obj.load = function(suffix) { function inner(suffix) { return suffix; } return suffix; };'
        outer = self.context(source, 'suffix')
        inner = self.context(source, 'suffix', 1)
        self.assertEqual(outer['context'], 'parameter_declaration_candidate')
        self.assertEqual(inner['context'], 'parameter_declaration_candidate')
        self.assertNotEqual(outer['scope_candidate']['name_sha256'],
                            inner['scope_candidate']['name_sha256'])
        self.assertEqual(self.context(source, 'suffix', 2)['context'], 'function_body_reference')

    def test_outside_function_and_masked_string(self):
        source = 'var suffix = "suffix"; // suffix\nfunction f(x) { return x; }'
        self.assertEqual(self.context(source, 'suffix')['context'],
                         'outside_recognized_function')

    def test_return_type_and_multiline_signature(self):
        source = 'x = function(\n suffix : Number, other\n):Void { suffix++; };'
        self.assertEqual(self.context(source, 'suffix')['context'],
                         'parameter_declaration_candidate')
        self.assertEqual(self.context(source, 'suffix', 1)['context'],
                         'function_body_reference')

    def test_unmatched_function_is_not_proven_scope(self):
        source = 'function broken(suffix) { return suffix;'
        self.assertEqual(self.context(source, 'suffix')['context'],
                         'outside_recognized_function')

    def test_comment_braces_do_not_break_scope(self):
        source = 'function f(suffix) { /* } */ return suffix; }'
        self.assertEqual(self.context(source, 'suffix', 1)['context'],
                         'function_body_reference')


if __name__ == '__main__':
    unittest.main()
