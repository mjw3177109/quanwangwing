import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from as2_scope_evidence import extract_function_scope_evidence
from build_as2_semantic_index import inspect_source

NAMED = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(")
ASSIGNED = re.compile(
    r"(?<![\w$])(?P<target>[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*){0,12})"
    r"\s*=\s*function\s*(?:[A-Za-z_$][\w$]*\s*)?\("
)
MARKERS = {
    "keyboard": re.compile(r"\bKey\s*\.\s*isDown\b"),
    "hit_test": re.compile(r"\bhitTest\s*\("),
    "timeline_jump": re.compile(r"\bgotoAndPlay\s*\("),
}


def scan(masked):
    return extract_function_scope_evidence(masked, NAMED, ASSIGNED, MARKERS)


class AS2ScopeEvidenceTests(unittest.TestCase):
    def test_nested_functions_attribute_to_innermost(self):
        source = """Key.isDown(1);
function outer(x) {
 Key.isDown(2);
 function inner() { this.hitTest(a); }
 gotoAndPlay(3);
}
"""
        out = scan(source)
        scopes = {x["name"]: x for x in out["function_scopes"]}
        self.assertEqual(scopes["outer"]["marker_counts"],
                         {"keyboard": 1, "timeline_jump": 1})
        self.assertEqual(scopes["inner"]["marker_counts"], {"hit_test": 1})
        self.assertEqual(scopes["inner"]["marker_lines"], {"hit_test": [4]})
        self.assertEqual(out["unscoped_marker_counts"], {"keyboard": 1})
        self.assertEqual(out["unmatched_function_candidates"], 0)

    def test_assignment_named_expression_and_return_type(self):
        source = (
            "Role.prototype.attack = function named(x:Number):Void { Key.isDown(1); };\n"
            "this.onEnterFrame = function() { gotoAndPlay(2); };"
        )
        out = scan(source)
        self.assertEqual(
            [(s["name"], s["kind"]) for s in out["function_scopes"]],
            [("Role.prototype.attack", "prototype_method"),
             ("this.onEnterFrame", "event_callback")]
        )
        self.assertEqual(out["function_scopes"][0]["marker_counts"], {"keyboard": 1})
        self.assertEqual(out["function_scopes"][1]["marker_counts"], {"timeline_jump": 1})

    def test_no_body_is_unmatched_not_assumed(self):
        out = scan("function missing(x);\nfunction real() { hitTest(a); }")
        self.assertEqual(out["unmatched_function_candidates"], 1)
        self.assertEqual(len(out["function_scopes"]), 1)
        self.assertEqual(out["function_scopes"][0]["name"], "real")

    def test_metadata_does_not_contain_body_or_arguments(self):
        out = scan("function attack() { Key.isDown(987654); }")
        self.assertNotIn("987654", str(out))
        self.assertNotIn("Key.isDown", str(out))

    def test_comments_and_strings_are_masked_by_caller(self):
        source = b'''// function Fake() { Key.isDown(1); }
function real() { var s = "function Hidden() { hitTest(x); }"; Key.isDown(2); }
'''
        out = inspect_source(source)
        self.assertEqual([s["name"] for s in out["function_scopes"]], ["real"])
        self.assertEqual(out["function_scopes"][0]["marker_counts"], {"keyboard": 1})
        self.assertEqual(out["unscoped_marker_counts"], {})


if __name__ == "__main__":
    unittest.main()
