import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_dynamic_attach_return_evidence import build_return_evidence


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


class DynamicAttachReturnEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.source_sha = "a" * 64
        self.path = "scripts/fixture.as"
        self.owner = sha("privateOwner")
        self.other = sha("privateOther")

    def fixture(self, source):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        file_path = root / self.path
        file_path.parent.mkdir(parents=True)
        raw = source.encode("utf-8")
        file_path.write_bytes(raw)
        path_hash = sha(self.path)
        export = {
            "source_sha256": self.source_sha, "script_count": 1,
            "total_bytes": len(raw), "unexpected_empty_count": 0,
            "files": [{"path": self.path, "size_bytes": len(raw), "sha256": sha_bytes(raw)}],
        }
        refs = {
            "source_sha256": self.source_sha, "verified_script_count": 1,
            "verified_script_bytes": len(raw), "identifier_target_count": 2,
            "identifier_occurrence_count": 3,
            "targets": [
                {"identifier_sha256": self.owner, "occurrence_count": 1,
                 "examples_truncated": False, "runtime_binding_verified": False,
                 "examples": [{"script_path": self.path, "line": 1,
                               "kind": "assignment_target_candidate",
                               "context": "outside_recognized_function", "scope_candidate": None}]},
                {"identifier_sha256": self.other, "occurrence_count": 2,
                 "examples_truncated": False, "runtime_binding_verified": False,
                 "examples": [
                     {"script_path": self.path, "line": 3, "kind": "member_property",
                      "context": "function_body_reference",
                      "scope_candidate": {"kind": "function_assignment", "name_sha256": self.owner,
                          "start_line": 1, "end_line": 5, "runtime_binding_verified": False}},
                     {"script_path": self.path, "line": 4, "kind": "member_property",
                      "context": "function_body_reference",
                      "scope_candidate": {"kind": "function_assignment", "name_sha256": self.owner,
                          "start_line": 1, "end_line": 5, "runtime_binding_verified": False}},
                 ]},
            ],
        }
        assignments = {
            "source_sha256": self.source_sha, "identifier_target_count": 2,
            "identifier_occurrence_count": 3, "assignment_candidate_count": 1,
            "rhs_class_counts": {"function_expression_candidate": 1},
            "sites": [{"identifier_sha256": self.owner, "script_path_sha256": path_hash,
                       "line": 1, "lhs_class": "direct_assignment_candidate",
                       "operator": "=", "rhs_class": "function_expression_candidate",
                       "runtime_binding_verified": False}],
        }
        joined = {
            "source_sha256": self.source_sha, "verified_script_count": 1,
            "identifier_target_count": 2, "identifier_occurrence_count": 3,
            "function_assignment_candidate_count": 1,
            "sites": [{"identifier_sha256": self.owner, "script_path_sha256": path_hash,
                       "assignment_line": 1,
                       "function_body_cross_target_references": [
                           {"other_identifier_sha256": self.other, "reference_line": 3,
                            "reference_kind": "member_property", "function_end_line": 5},
                           {"other_identifier_sha256": self.other, "reference_line": 4,
                            "reference_kind": "member_property", "function_end_line": 5},
                       ],
                       "runtime_binding_verified": False}],
        }
        return tmp, root, export, assignments, refs, joined

    def run_fixture(self, source):
        tmp, root, export, assignments, refs, joined = self.fixture(source)
        self.addCleanup(tmp.cleanup)
        return build_return_evidence(root, export, assignments, refs, joined)

    def test_return_shapes_and_cross_target_refs(self):
        source = (
            'var privateOwner = function() {\n'
            '  var localValue = "secretLabel";\n'
            '  if (flag) { return localValue + this.privateOther; }\n'
            '  return this.privateOther;\n'
            '};\n'
        )
        result = self.run_fixture(source)
        self.assertEqual(result["function_assignment_count"], 1)
        self.assertEqual(result["parse_status_counts"], {"parsed": 1})
        self.assertEqual(result["return_count_total"], 2)
        self.assertEqual(result["cross_target_return_reference_count"], 2)
        self.assertEqual(result["return_kind_counts"]["binary_or_assignment_expression"], 1)
        self.assertEqual(result["return_kind_counts"]["member_reference"], 1)
        self.assertFalse(result["runtime_binding_verified"])
        self.assertFalse(result["execution_verified"])

    def test_nested_function_return_is_excluded(self):
        source = (
            'var privateOwner = function() {\n'
            '  var inner = function() { return "nestedSecret"; };\n'
            '  return this.privateOther;\n'
            '};\n'
        )
        tmp, root, export, assignments, refs, joined = self.fixture(source)
        self.addCleanup(tmp.cleanup)
        refs["targets"][1]["occurrence_count"] = 1
        refs["identifier_occurrence_count"] = 2
        refs["targets"][1]["examples"] = [{
            "script_path": self.path, "line": 3, "kind": "member_property",
            "context": "function_body_reference",
            "scope_candidate": {"kind": "function_assignment", "name_sha256": self.owner,
                                "start_line": 1, "end_line": 4, "runtime_binding_verified": False},
        }]
        assignments["identifier_occurrence_count"] = 2
        joined["identifier_occurrence_count"] = 2
        joined["sites"][0]["function_body_cross_target_references"] = [{
            "other_identifier_sha256": self.other, "reference_line": 3,
            "reference_kind": "member_property", "function_end_line": 4,
        }]
        result = build_return_evidence(root, export, assignments, refs, joined)
        self.assertEqual(result["return_count_total"], 1)
        self.assertEqual(result["cross_target_return_reference_count"], 1)

    def test_comments_and_string_contents_do_not_create_returns(self):
        source = (
            'var privateOwner = function() {\n'
            '  /* return this.privateOther; */\n'
            '  var note = "return this.privateOther;";\n'
            '  return this.privateOther;\n'
            '};\n'
        )
        tmp, root, export, assignments, refs, joined = self.fixture(source)
        self.addCleanup(tmp.cleanup)
        refs["targets"][1]["occurrence_count"] = 1
        refs["identifier_occurrence_count"] = 2
        refs["targets"][1]["examples"] = [{
            "script_path": self.path, "line": 4, "kind": "member_property",
            "context": "function_body_reference",
            "scope_candidate": {"kind": "function_assignment", "name_sha256": self.owner,
                                "start_line": 1, "end_line": 5, "runtime_binding_verified": False},
        }]
        assignments["identifier_occurrence_count"] = 2
        joined["identifier_occurrence_count"] = 2
        joined["sites"][0]["function_body_cross_target_references"] = [{
            "other_identifier_sha256": self.other, "reference_line": 4,
            "reference_kind": "member_property", "function_end_line": 5,
        }]
        result = build_return_evidence(root, export, assignments, refs, joined)
        self.assertEqual(result["return_count_total"], 1)
        self.assertEqual(result["cross_target_return_reference_count"], 1)

    def test_plaintext_source_and_identifiers_are_not_emitted(self):
        source = (
            'var privateOwner = function() {\n'
            '  return this.privateOther + "secretLabel";\n'
            '};\n'
        )
        tmp, root, export, assignments, refs, joined = self.fixture(source)
        self.addCleanup(tmp.cleanup)
        refs["targets"][1]["occurrence_count"] = 1
        refs["identifier_occurrence_count"] = 2
        refs["targets"][1]["examples"] = [{
            "script_path": self.path, "line": 2, "kind": "member_property",
            "context": "function_body_reference",
            "scope_candidate": {"kind": "function_assignment", "name_sha256": self.owner,
                                "start_line": 1, "end_line": 4, "runtime_binding_verified": False},
        }]
        assignments["identifier_occurrence_count"] = 2
        joined["identifier_occurrence_count"] = 2
        joined["sites"][0]["function_body_cross_target_references"] = [{
            "other_identifier_sha256": self.other, "reference_line": 2,
            "reference_kind": "member_property", "function_end_line": 4,
        }]
        result = build_return_evidence(root, export, assignments, refs, joined)
        serialized = json.dumps(result)
        self.assertNotIn("privateOwner", serialized)
        self.assertNotIn("privateOther", serialized)
        self.assertNotIn("secretLabel", serialized)
        self.assertNotIn(self.path, serialized)

    def test_source_sha_mismatch_fails_closed(self):
        tmp, root, export, assignments, refs, joined = self.fixture(
            'var privateOwner = function() { return this.privateOther; };\n')
        self.addCleanup(tmp.cleanup)
        joined["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SWF source SHA-256 mismatch"):
            build_return_evidence(root, export, assignments, refs, joined)

    def test_export_hash_mismatch_fails_closed(self):
        tmp, root, export, assignments, refs, joined = self.fixture(
            'var privateOwner = function() { return this.privateOther; };\n')
        self.addCleanup(tmp.cleanup)
        export["files"][0]["sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "AS2 source hash/length mismatch"):
            build_return_evidence(root, export, assignments, refs, joined)

    def test_function_end_line_mismatch_fails_closed(self):
        source = 'var privateOwner = function() {\n  return this.privateOther;\n};\n'
        tmp, root, export, assignments, refs, joined = self.fixture(source)
        self.addCleanup(tmp.cleanup)
        refs["targets"][1]["examples"][0]["scope_candidate"]["end_line"] = 5
        joined["sites"][0]["function_body_cross_target_references"][0]["function_end_line"] = 5
        result = build_return_evidence(root, export, assignments, refs, joined)
        self.assertEqual(result["parse_status_counts"], {"unresolved_function_range": 1})
        self.assertEqual(result["return_count_total"], 0)

    def test_missing_assignment_origin_fails_closed(self):
        tmp, root, export, assignments, refs, joined = self.fixture(
            'var privateOwner = function() { return this.privateOther; };\n'
        )
        self.addCleanup(tmp.cleanup)
        refs["targets"][0]["examples"][0]["kind"] = "other_reference"
        with self.assertRaisesRegex(ValueError, "Function assignment lacks exact hashed source reference"):
            build_return_evidence(root, export, assignments, refs, joined)

    def test_unbalanced_function_is_reported_unresolved_not_promoted(self):
        source = 'var privateOwner = function() {\n  return this.privateOther;\n'
        tmp, root, export, assignments, refs, joined = self.fixture(source)
        self.addCleanup(tmp.cleanup)
        refs["targets"][1]["occurrence_count"] = 1
        refs["identifier_occurrence_count"] = 2
        refs["targets"][1]["examples"] = [{
            "script_path": self.path, "line": 2, "kind": "member_property",
            "context": "function_body_reference",
            "scope_candidate": {"kind": "function_assignment", "name_sha256": self.owner,
                                "start_line": 1, "end_line": 2, "runtime_binding_verified": False},
        }]
        assignments["identifier_occurrence_count"] = 2
        joined["identifier_occurrence_count"] = 2
        joined["sites"][0]["function_body_cross_target_references"] = [{
            "other_identifier_sha256": self.other, "reference_line": 2,
            "reference_kind": "member_property", "function_end_line": 2,
        }]
        result = build_return_evidence(root, export, assignments, refs, joined)
        self.assertEqual(result["parse_status_counts"], {"unresolved_function_range": 1})
        self.assertEqual(result["return_count_total"], 0)


if __name__ == "__main__":
    unittest.main()
