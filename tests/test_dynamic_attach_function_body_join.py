import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_dynamic_attach_function_body_join import build_function_body_join


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class FunctionBodyJoinTests(unittest.TestCase):
    def setUp(self):
        self.source = "c" * 64
        self.a, self.b = sha("alpha"), sha("beta")
        self.path = "scripts/frame_17/DoAction.as"
        self.path_hash = sha(self.path)
        self.assignments = {"source_sha256": self.source, "identifier_target_count": 2,
                            "identifier_occurrence_count": 2, "assignment_candidate_count": 1,
                            "sites": [{"identifier_sha256": self.a, "script_path_sha256": self.path_hash,
                                       "line": 10, "operator": "=", "lhs_class": "direct_assignment_candidate",
                                       "rhs_class": "function_expression_candidate", "runtime_binding_verified": False}]}
        self.references = {"source_sha256": self.source, "verified_script_count": 1,
                           "identifier_target_count": 2, "identifier_occurrence_count": 2,
                           "targets": [
                               {"identifier_sha256": self.a, "occurrence_count": 1,
                                "examples_truncated": False, "runtime_binding_verified": False,
                                "examples": [{"script_path": self.path, "line": 10,
                                              "kind": "assignment_target_candidate",
                                              "context": "outside_recognized_function", "scope_candidate": None}]},
                               {"identifier_sha256": self.b, "occurrence_count": 1,
                                "examples_truncated": False, "runtime_binding_verified": False,
                                "examples": [{"script_path": self.path, "line": 12,
                                              "kind": "member_property", "context": "function_body_reference",
                                              "scope_candidate": {"kind": "function_assignment",
                                                  "name_sha256": self.a, "start_line": 10, "end_line": 13,
                                                  "runtime_binding_verified": False}}]}]}
        self.joined = {"source_sha256": self.source, "identifier_target_count": 2,
                       "identifier_occurrence_count": 2, "dynamic_attach_count": 1,
                       "events": [{"runtime_binding_verified": False,
                                   "identifier_references": [
                                       {"identifier_sha256": self.a, "runtime_binding_verified": False},
                                       {"identifier_sha256": self.b, "runtime_binding_verified": False}]}]}

    def audit(self):
        return build_function_body_join(self.assignments, self.references, self.joined)

    def test_matches_function_body_member_reference(self):
        result = self.audit()
        self.assertEqual(result["function_assignment_candidate_count"], 1)
        self.assertEqual(result["function_assignments_with_cross_target_body_references"], 1)
        self.assertEqual(result["cross_target_member_property_count"], 1)
        self.assertEqual(result["sites"][0]["function_body_cross_target_references"][0]["reference_line"], 12)
        self.assertNotIn(self.path, str(result))

    def test_other_scope_is_not_claimed(self):
        self.references["targets"][1]["examples"][0]["scope_candidate"]["name_sha256"] = sha("other")
        self.assertEqual(self.audit()["cross_target_body_reference_count"], 0)

    def test_other_assignment_line_is_not_claimed(self):
        self.references["targets"][1]["examples"][0]["scope_candidate"]["start_line"] = 9
        self.assertEqual(self.audit()["cross_target_body_reference_count"], 0)

    def test_different_script_is_not_claimed(self):
        self.references["targets"][1]["examples"][0]["script_path"] = "scripts/other.as"
        self.assertEqual(self.audit()["cross_target_body_reference_count"], 0)

    def test_source_mismatch_rejected(self):
        self.joined["source_sha256"] = "d" * 64
        with self.assertRaises(ValueError): self.audit()

    def test_truncated_references_rejected(self):
        self.references["targets"][1]["examples_truncated"] = True
        with self.assertRaises(ValueError): self.audit()

    def test_unverified_runtime_claim_rejected(self):
        self.joined["events"][0]["runtime_binding_verified"] = True
        with self.assertRaises(ValueError): self.audit()

    def test_missing_assignment_reference_rejected(self):
        self.references["targets"][0]["examples"][0]["kind"] = "other_reference"
        with self.assertRaises(ValueError): self.audit()

    def test_duplicate_assignment_rejected(self):
        self.assignments["sites"].append(copy.deepcopy(self.assignments["sites"][0]))
        self.assignments["assignment_candidate_count"] = 2
        with self.assertRaises(ValueError): self.audit()

    def test_invalid_path_rejected(self):
        self.references["targets"][1]["examples"][0]["script_path"] = "scripts/../private.as"
        with self.assertRaises(ValueError): self.audit()

    def test_unverified_assignment_claim_rejected(self):
        self.assignments["sites"][0]["runtime_binding_verified"] = True
        with self.assertRaises(ValueError): self.audit()

    def test_wrong_operator_rejected(self):
        self.assignments["sites"][0]["operator"] = "+="
        with self.assertRaises(ValueError): self.audit()


if __name__ == "__main__":
    unittest.main()
