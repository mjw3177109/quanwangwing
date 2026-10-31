import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_role_call_scope_join import build_join


class RoleCallScopeJoinTests(unittest.TestCase):
    def fixture(self):
        sha = "a" * 64
        digest = "b" * 64
        identity = {"character_candidate": "Kyo", "variant": "base"}
        crosswalk = {
            "source_sha256": sha, "role_variant_count": 1,
            "roles": [{**identity, "verified_as2_script_path": "scripts/Kyo.as",
                       "verified_as2_script_sha256": digest,
                       "function_scope_candidate_count": 2,
                       "function_scope_candidates": [
                           {"name": "privateOriginalFunction", "kind": "function_assignment", "start_line": 5, "end_line": 20},
                           {"name": "privateNestedFunction", "kind": "named_function", "start_line": 10, "end_line": 16},
                       ]}],
        }
        calls = {
            "source_sha256": sha, "role_variant_count": 1, "call_candidate_count": 3,
            "roles": [{**identity, "verified_as2_script_path": "scripts/Kyo.as",
                       "verified_as2_script_sha256": digest, "call_candidate_count": 3,
                       "calls": [
                           {"line": 7, "method": "gotoAndPlay", "receiver_kind": "this_direct", "argument_kind": "string_literal"},
                           {"line": 12, "method": "gotoAndStop", "receiver_kind": "this_direct", "argument_kind": "dynamic_or_unresolved"},
                           {"line": 25, "method": "gotoAndPlay", "receiver_kind": "this_direct", "argument_kind": "integer_literal"},
                       ]}],
        }
        return crosswalk, calls

    def test_unique_overlap_and_outside_are_accounted(self):
        crosswalk, calls = self.fixture()
        result = build_join(crosswalk, calls)
        self.assertEqual(result["scope_relation_counts"], {"unique": 1, "overlapping": 1, "outside": 1})
        self.assertEqual(result["scope_kind_counts"], {"function_assignment": 1, "unresolved": 2})
        self.assertEqual([c["scope_candidate_count"] for c in result["roles"][0]["calls"]], [1, 2, 0])
        self.assertNotIn("privateOriginalFunction", json.dumps(result))
        self.assertNotIn("privateNestedFunction", json.dumps(result))

    def test_source_and_role_script_provenance_must_match(self):
        crosswalk, calls = self.fixture()
        calls["source_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_join(crosswalk, calls)
        calls["source_sha256"] = crosswalk["source_sha256"]
        calls["roles"][0]["verified_as2_script_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "provenance"):
            build_join(crosswalk, calls)

    def test_invalid_scope_and_line_fail_closed(self):
        crosswalk, calls = self.fixture()
        crosswalk["roles"][0]["function_scope_candidates"][0]["end_line"] = 1
        with self.assertRaisesRegex(ValueError, "Invalid lexical"):
            build_join(crosswalk, calls)
        crosswalk, calls = self.fixture()
        calls["roles"][0]["calls"][0]["line"] = 0
        with self.assertRaisesRegex(ValueError, "Invalid callsite"):
            build_join(crosswalk, calls)

    def test_duplicate_or_missing_role_fails_closed(self):
        crosswalk, calls = self.fixture()
        calls["roles"].append(copy.deepcopy(calls["roles"][0]))
        calls["role_variant_count"] = 2
        calls["call_candidate_count"] = 6
        with self.assertRaisesRegex(ValueError, "Role coverage"):
            build_join(crosswalk, calls)
        crosswalk, calls = self.fixture()
        calls["roles"][0]["variant"] = "type2"
        with self.assertRaisesRegex(ValueError, "unknown role"):
            build_join(crosswalk, calls)

    def test_call_count_mismatch_fails_closed(self):
        crosswalk, calls = self.fixture()
        calls["call_candidate_count"] = 4
        with self.assertRaisesRegex(ValueError, "accounting"):
            build_join(crosswalk, calls)


if __name__ == "__main__":
    unittest.main()
