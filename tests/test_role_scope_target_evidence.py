import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_role_scope_target_evidence import build_evidence, classify_target


class RoleScopeTargetEvidenceTests(unittest.TestCase):
    def fixture(self):
        role = {"character_candidate": "Kyo", "variant": "base"}
        sha, script = "a" * 64, "b" * 64
        crosswalk = {"source_sha256": sha, "role_variant_count": 1,
                     "roles": [{**role, "verified_as2_script_path": "scripts/Kyo.as",
                                "verified_as2_script_sha256": script,
                                "export_assets_character_id": 123,
                                "sprite_timeline": {"sprite_character_id": 123},
                                "function_scope_candidate_count": 2,
                                "function_scope_candidates": [
                                    {"name": "this.privateMethod", "kind": "function_assignment", "start_line": 5, "end_line": 15},
                                    {"name": "Role.prototype.privateAction", "kind": "prototype_method", "start_line": 18, "end_line": 30},
                                ]}]}
        joined = {"source_sha256": sha, "role_variant_count": 1, "call_candidate_count": 3,
                  "roles": [{**role, "verified_as2_script_sha256": script,
                             "call_candidate_count": 3, "calls": [
                                 {"line": 9, "method": "gotoAndPlay", "receiver_kind": "this_direct",
                                  "scope_relation": "unique", "scope_candidate_count": 1,
                                  "scope_kind": "function_assignment"},
                                 {"line": 20, "method": "gotoAndStop", "receiver_kind": "member_chain_or_expression",
                                  "scope_relation": "unique", "scope_candidate_count": 1,
                                  "scope_kind": "prototype_method"},
                                 {"line": 50, "method": "gotoAndPlay", "receiver_kind": "this_direct",
                                  "scope_relation": "outside", "scope_candidate_count": 0,
                                  "scope_kind": "unresolved"},
                             ]}]}
        return crosswalk, joined

    def test_classify_shapes(self):
        self.assertEqual(classify_target("this.a", "function_assignment"), ("this_member", 2))
        self.assertEqual(classify_target("_root.p.a", "function_assignment"), ("root_member", 3))
        self.assertEqual(classify_target("_parent.a", "event_callback"), ("parent_member", 2))
        self.assertEqual(classify_target("K.prototype.move", "prototype_method"), ("prototype_member", 3))
        self.assertEqual(classify_target("obj.fn", "function_assignment"), ("other_member", 2))
        self.assertEqual(classify_target("_global.Kyo_role", "function_assignment"), ("global_member", 2))
        self.assertEqual(classify_target("_loc2_.move", "function_assignment"), ("ffdec_local_member", 2))
        self.assertEqual(classify_target("local", "named_function"), ("bare_identifier", 1))
        with self.assertRaises(ValueError):
            classify_target("bad target!", "function_assignment")

    def test_join_and_no_original_names_leak(self):
        a, b = self.fixture()
        out = build_evidence(a, b)
        self.assertEqual(out["call_candidate_count"], 3)
        self.assertEqual(out["scope_target_kind_counts"]["this_member"], 1)
        self.assertEqual(out["scope_target_kind_counts"]["prototype_member"], 1)
        self.assertEqual(out["scope_target_kind_counts"]["unresolved"], 1)
        self.assertEqual(sum(x["count"] for x in out["receiver_target_pair_counts"]), 3)
        self.assertFalse(any(c["runtime_binding_verified"] for c in out["roles"][0]["calls"]))
        self.assertNotIn("privateMethod", json.dumps(out))
        self.assertNotIn("privateAction", json.dumps(out))

    def test_mismatched_source_or_script_fails(self):
        a, b = self.fixture()
        b["source_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_evidence(a, b)
        a, b = self.fixture()
        b["roles"][0]["verified_as2_script_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "provenance"):
            build_evidence(a, b)

    def test_scope_and_symbol_mismatch_fail(self):
        a, b = self.fixture()
        b["roles"][0]["calls"][0]["scope_candidate_count"] = 0
        with self.assertRaisesRegex(ValueError, "relation mismatch"):
            build_evidence(a, b)
        a, b = self.fixture()
        a["roles"][0]["sprite_timeline"]["sprite_character_id"] = 456
        with self.assertRaisesRegex(ValueError, "Sprite ID"):
            build_evidence(a, b)

    def test_duplicate_and_count_mismatch_fail(self):
        a, b = self.fixture()
        b["call_candidate_count"] = 4
        with self.assertRaisesRegex(ValueError, "accounting"):
            build_evidence(a, b)
        a, b = self.fixture()
        a["roles"].append(copy.deepcopy(a["roles"][0]))
        a["role_variant_count"] = 2
        b["roles"].append(copy.deepcopy(b["roles"][0]))
        b["role_variant_count"] = 2
        b["call_candidate_count"] = 6
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_evidence(a, b)


if __name__ == "__main__":
    unittest.main()
