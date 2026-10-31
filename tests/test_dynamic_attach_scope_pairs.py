import copy
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_dynamic_attach_scope_pairs import build_scope_pairs

A, B, SOURCE = "a" * 64, "b" * 64, "c" * 64
PATH, OTHER = "scripts/frame_17/DoAction.as", "scripts/Other.as"


def example(path, line, scope=None):
    return {"script_path": path, "line": line,
            "context": "function_body_reference" if scope else "outside_recognized_function",
            "scope_candidate": scope, "kind": "other_reference"}


def fixture():
    refs = {"source_sha256": SOURCE, "verified_script_count": 2,
            "verified_script_bytes": 100, "identifier_target_count": 2,
            "identifier_occurrence_count": 4, "targets": [
                {"identifier_sha256": A, "occurrence_count": 2,
                 "runtime_binding_verified": False, "examples_truncated": False,
                 "examples": [example(PATH, 73), example(OTHER, 10)]},
                {"identifier_sha256": B, "occurrence_count": 2,
                 "runtime_binding_verified": False, "examples_truncated": False,
                 "examples": [example(PATH, 74), example(OTHER, 13)]}]}
    join = {"source_sha256": SOURCE, "identifier_target_count": 2,
            "identifier_occurrence_count": 4, "dynamic_attach_count": 1,
            "events": [{"runtime_binding_verified": False,
                        "identifier_references": [
                            {"identifier_sha256": A, "runtime_binding_verified": False},
                            {"identifier_sha256": B, "runtime_binding_verified": False}]}]}
    return refs, join


class ScopePairTests(unittest.TestCase):
    def test_proximity_and_privacy(self):
        d = build_scope_pairs(*fixture())
        self.assertEqual((d["shared_script_count"], d["shared_scripts_with_gap_at_most_2"],
                          d["shared_scripts_with_gap_at_most_5"]), (2, 1, 2))
        self.assertNotIn(PATH, str(d))
        self.assertTrue(all(not x["runtime_binding_verified"] for x in d["pairs"]))

    def test_matching_function_candidate(self):
        refs, join = fixture()
        scope = {"name_sha256": "d" * 64, "start_line": 70, "end_line": 80,
                 "kind": "named_function", "runtime_binding_verified": False}
        refs["targets"][0]["examples"][0] = example(PATH, 73, scope)
        refs["targets"][1]["examples"][0] = example(PATH, 74, dict(scope))
        self.assertEqual(build_scope_pairs(refs, join)["shared_scripts_with_same_function_candidate"], 1)

    def test_source_mismatch(self):
        r, j = fixture()
        j["source_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            build_scope_pairs(r, j)

    def test_truncated_rejected(self):
        r, j = fixture()
        r["targets"][0]["examples_truncated"] = True
        with self.assertRaisesRegex(ValueError, "Incomplete bounded"):
            build_scope_pairs(r, j)

    def test_missing_example_rejected(self):
        r, j = fixture()
        r["targets"][0]["examples"].pop()
        with self.assertRaisesRegex(ValueError, "Incomplete bounded"):
            build_scope_pairs(r, j)

    def test_traversal_rejected(self):
        r, j = fixture()
        r["targets"][0]["examples"][0]["script_path"] = "scripts/../secret.as"
        with self.assertRaisesRegex(ValueError, "private script path"):
            build_scope_pairs(r, j)

    def test_scope_bounds_rejected(self):
        r, j = fixture()
        r["targets"][0]["examples"][0] = example(PATH, 73, {
            "name_sha256": "d" * 64, "start_line": 1, "end_line": 5,
            "kind": "named_function", "runtime_binding_verified": False})
        with self.assertRaisesRegex(ValueError, "scope bounds"):
            build_scope_pairs(r, j)

    def test_runtime_claim_rejected(self):
        r, j = fixture()
        j["events"][0]["identifier_references"][0]["runtime_binding_verified"] = True
        with self.assertRaisesRegex(ValueError, "runtime identifier"):
            build_scope_pairs(r, j)

    def test_target_coverage_rejected(self):
        r, j = fixture()
        j["events"][0]["identifier_references"].pop()
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            build_scope_pairs(r, j)

    def test_total_mismatch_rejected(self):
        r, j = fixture()
        r["identifier_occurrence_count"] += 1
        with self.assertRaisesRegex(ValueError, "total mismatch"):
            build_scope_pairs(r, j)


if __name__ == "__main__":
    unittest.main()
