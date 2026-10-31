import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from bisect import bisect_right

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_as2_semantic_index import mask_comments_strings
from build_attach_identifier_references import TOKEN, _kind
from build_dynamic_attach_assignment_sites import build_assignment_sites

SOURCE = "c" * 64
SCRIPT = """var alpha = 'sensitive_string_123';
alpha = new Thing();
obj.alpha += 1;
alpha == 2;
var beta = alpha;
attachMovie(alpha + beta, 'clip', 2);
// beta = should_not_count;
"""


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AssignmentAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rel = "scripts/frame_17/DoAction.as"
        file = self.root / self.rel
        file.parent.mkdir(parents=True)
        file.write_text(SCRIPT, encoding="utf-8")
        raw = file.read_bytes()
        self.index = {
            "source_sha256": SOURCE, "script_count": 1, "total_bytes": len(raw),
            "unexpected_empty_count": 0,
            "files": [{"path": self.rel, "size_bytes": len(raw),
                       "sha256": hashlib.sha256(raw).hexdigest()}],
        }
        masked = mask_comments_strings(SCRIPT)
        newlines = [i for i, c in enumerate(masked) if c == "\n"]
        examples = {"alpha": [], "beta": []}
        for match in TOKEN.finditer(masked):
            name = match.group(1)
            if name in examples:
                examples[name].append({"script_path": self.rel,
                    "line": bisect_right(newlines, match.start() - 1) + 1,
                    "kind": _kind(masked, match.start(), match.end())})
        self.refs = {"source_sha256": SOURCE, "verified_script_count": 1,
            "verified_script_bytes": len(raw), "identifier_target_count": 2,
            "identifier_occurrence_count": sum(map(len, examples.values())),
            "targets": [{"identifier_sha256": sha(name), "occurrence_count": len(rows),
                         "examples_truncated": False, "runtime_binding_verified": False,
                         "examples": rows} for name, rows in examples.items()]}

    def audit(self):
        return build_assignment_sites(self.root, self.index, self.refs)

    def test_classifies_assignments_without_exposing_source(self):
        result = self.audit()
        self.assertEqual(result["assignment_candidate_count"], 4)
        self.assertEqual(result["lhs_class_counts"], {
            "direct_assignment_candidate": 1, "member_property_candidate": 1,
            "variable_initializer_candidate": 2})
        self.assertEqual(result["identifier_occurrence_count"], self.refs["identifier_occurrence_count"])
        self.assertEqual({s["operator"] for s in result["sites"]}, {"=", "+="})
        self.assertIn("constructor_candidate", result["rhs_class_counts"])
        self.assertNotIn("sensitive_string_123", str(result))
        self.assertNotIn(self.rel, str(result))
        self.assertNotIn("alpha", str(result))
        self.assertTrue(all(s["runtime_binding_verified"] is False for s in result["sites"]))

    def test_source_sha_mismatch_rejected(self):
        self.index["source_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "source SHA-256 mismatch"):
            self.audit()

    def test_source_bytes_modified_rejected(self):
        (self.root / self.rel).write_text(SCRIPT + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            self.audit()

    def test_truncated_examples_rejected(self):
        self.refs["targets"][0]["examples_truncated"] = True
        with self.assertRaisesRegex(ValueError, "Incomplete lexical examples"):
            self.audit()

    def test_missing_example_rejected(self):
        self.refs["targets"][0]["examples"].pop()
        with self.assertRaisesRegex(ValueError, "Incomplete lexical examples"):
            self.audit()

    def test_reference_line_mismatch_rejected(self):
        self.refs["targets"][0]["examples"][0]["line"] += 1
        with self.assertRaisesRegex(ValueError, "position/kind mismatch"):
            self.audit()

    def test_runtime_claim_rejected(self):
        self.refs["targets"][0]["runtime_binding_verified"] = True
        with self.assertRaisesRegex(ValueError, "unverified binding claim"):
            self.audit()

    def test_script_path_traversal_rejected(self):
        self.refs["targets"][0]["examples"][0]["script_path"] = "scripts/../secret.as"
        with self.assertRaisesRegex(ValueError, "private script path"):
            self.audit()

    def test_duplicate_export_path_rejected(self):
        self.index["files"].append(copy.deepcopy(self.index["files"][0]))
        self.index["script_count"] = 2
        self.index["total_bytes"] *= 2
        self.refs["verified_script_count"] = 2
        self.refs["verified_script_bytes"] *= 2
        with self.assertRaisesRegex(ValueError, "Duplicate or invalid script path"):
            self.audit()

    def test_byte_accounting_rejected(self):
        self.index["total_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "Verified script coverage mismatch"):
            self.audit()

    def test_equality_not_assignment(self):
        result = self.audit()
        self.assertNotIn(4, [s["line"] for s in result["sites"]])


if __name__ == "__main__":
    unittest.main()
