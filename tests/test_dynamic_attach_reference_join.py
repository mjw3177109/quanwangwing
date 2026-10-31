import copy
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_dynamic_attach_reference_join import build_dynamic_attach_reference_join

SHA = "a" * 64
ID = "b" * 64
SCRIPT = "c" * 64
ARG = "d" * 64
PATH = "scripts/frame_17/DoAction.as"


def fixture():
    p = {"source_sha256": SHA, "verified_script_count": 2, "verified_script_bytes": 200,
         "dynamic_argument_count": 1, "argument_shape_counts": {"concatenation": 1},
         "events": [{"script_path": PATH, "script_sha256": SCRIPT, "line": 73,
                     "argument_sha256": ARG, "argument_shape": "concatenation",
                     "runtime_binding_verified": False, "concatenation_components": [
                         {"position": 0, "kind": "literal_unmatched"},
                         {"position": 1, "kind": "identifier", "identifier_sha256": ID}]}]}
    refs = {"source_sha256": SHA, "verified_script_count": 2, "verified_script_bytes": 200,
            "identifier_target_count": 1, "identifier_occurrence_count": 3,
            "targets": [{"identifier_sha256": ID, "runtime_binding_verified": False,
                         "occurrence_count": 3, "same_script_before_count": 0,
                         "same_script_at_or_after_count": 1, "other_script_count": 2,
                         "scope_context_counts": {"outside_recognized_function": 3},
                         "attach_sites": [{"script_path": PATH, "line": 73, "component_position": 1}]}]}
    roles = {"source_sha256": SHA, "role_variant_count": 1,
             "entries": [{"verified_role_script_sha256": "e" * 64}]}
    return p, refs, roles


class DynamicAttachReferenceJoinTests(unittest.TestCase):
    def test_join_and_no_plaintext_paths(self):
        result = build_dynamic_attach_reference_join(*fixture())
        self.assertEqual(result["dynamic_attach_count"], 1)
        self.assertEqual(result["identifier_occurrence_count"], 3)
        self.assertEqual(result["calls_in_verified_role_scripts"], 0)
        self.assertNotIn(PATH, str(result))
        self.assertEqual(result["events"][0]["script_path_sha256"], hashlib.sha256(PATH.encode()).hexdigest())
    def test_role_script_hash_classification(self):
        p, r, roles = fixture()
        roles["entries"][0]["verified_role_script_sha256"] = SCRIPT
        self.assertEqual(build_dynamic_attach_reference_join(p, r, roles)["calls_in_verified_role_scripts"], 1)
    def test_source_hash_mismatch(self):
        p, r, roles = fixture()
        r["source_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            build_dynamic_attach_reference_join(p, r, roles)
    def test_script_bytes_mismatch(self):
        p, r, roles = fixture()
        r["verified_script_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            build_dynamic_attach_reference_join(p, r, roles)
    def test_missing_identifier(self):
        p, r, roles = fixture()
        r["targets"] = []
        r["identifier_target_count"] = 0
        with self.assertRaisesRegex(ValueError, "Missing hashed identifier"):
            build_dynamic_attach_reference_join(p, r, roles)
    def test_attach_site_tampering(self):
        p, r, roles = fixture()
        r["targets"][0]["attach_sites"][0]["line"] = 74
        with self.assertRaisesRegex(ValueError, "attach-site mismatch"):
            build_dynamic_attach_reference_join(p, r, roles)
    def test_occurrence_mismatch(self):
        p, r, roles = fixture()
        r["targets"][0]["other_script_count"] = 1
        with self.assertRaisesRegex(ValueError, "occurrence accounting"):
            build_dynamic_attach_reference_join(p, r, roles)
    def test_runtime_binding_claim_rejected(self):
        p, r, roles = fixture()
        r["targets"][0]["runtime_binding_verified"] = True
        with self.assertRaisesRegex(ValueError, "unverified identifier"):
            build_dynamic_attach_reference_join(p, r, roles)
    def test_duplicate_site_rejected(self):
        p, r, roles = fixture()
        p["events"].append(copy.deepcopy(p["events"][0]))
        p["dynamic_argument_count"] = 2
        p["argument_shape_counts"]["concatenation"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate or verified"):
            build_dynamic_attach_reference_join(p, r, roles)
    def test_missing_role_hash_rejected(self):
        p, r, roles = fixture()
        roles["entries"][0].pop("verified_role_script_sha256")
        with self.assertRaisesRegex(ValueError, "role script hash"):
            build_dynamic_attach_reference_join(p, r, roles)


if __name__ == "__main__":
    unittest.main()
