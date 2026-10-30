import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_runtime_attach_evidence import build_attach_evidence
from build_attach_argument_provenance import build_dynamic_argument_evidence


def fixture(root, source):
    rel = "scripts/__Packages/role_corn/Role.as"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source)
    sha = "f" * 64
    index = {
        "source_sha256": sha, "script_count": 1,
        "unexpected_empty_count": 0,
        "files": [{"path": rel, "size_bytes": len(source),
                   "sha256": hashlib.sha256(source).hexdigest()}],
    }
    assets = {"source_sha256": sha, "export_assets": [
        {"name": "__Packages.Kyo_role", "character_id": 77},
        {"name": "otherClip", "character_id": 88},
    ]}
    crosswalk = {"source_sha256": sha, "role_variant_count": 1,
                 "roles": [{"export_assets_character_id": 77}]}
    semantic = {"source_sha256": sha, "candidate_scripts": [{
        "path": rel, "function_scopes": [
            {"name": "spawn", "kind": "named_function",
             "start_line": 1, "end_line": 20},
        ],
    }]}
    attach = build_attach_evidence(root, index, assets, crosswalk, semantic)
    return index, attach, assets


class DynamicAttachTests(unittest.TestCase):
    def build(self, root, source):
        index, attach, assets = fixture(root, source)
        return build_dynamic_argument_evidence(root, index, attach, assets)

    def test_identifier_with_prior_export_literal_assignment(self):
        source = (b'var roleName = "__Packages.Kyo_role";\n'
                  b'clip.attachMovie(roleName, "instance", 1);\n')
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), source)
            self.assertEqual(result["dynamic_argument_count"], 1)
            event = result["events"][0]
            self.assertEqual(event["argument_shape"], "identifier")
            self.assertEqual(event["lexical_assignment_candidates"][0]["rhs_kind"], "literal_export_match")
            self.assertEqual(event["lexical_assignment_candidates"][0]["matched_export_assets"][0]["character_id"], 77)
            self.assertFalse(event["runtime_binding_verified"])
            self.assertNotIn("roleName", str(result))

    def test_unknown_literal_is_hashed(self):
        source = b'var target = "notPublic";\nattachMovie(target, "a", 1);'
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), source)
            entry = result["events"][0]["lexical_assignment_candidates"][0]
            self.assertEqual(entry["rhs_kind"], "literal_unmatched")
            self.assertEqual(len(entry["unmatched_literal_sha256"]), 64)
            self.assertNotIn("notPublic", str(result))

    def test_function_call_first_argument_with_nested_comma(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'attachMovie(resolve(name, 2), "a", 1);')
            self.assertEqual(result["argument_shape_counts"], {"call_expression": 1})

    def test_member_expression(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'attachMovie(state.roleName, "a", 1);')
            self.assertEqual(result["events"][0]["argument_shape"], "member_reference")

    def test_concatenation_expression(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'attachMovie(prefix + suffix, "a", 1);')
            self.assertEqual(result["events"][0]["argument_shape"], "concatenation")

    def test_comments_and_string_pseudo_calls_ignored(self):
        source = (b'// attachMovie(foo, "x", 1)\n'
                  b'var s = "attachMovie(bar, 1)";\n'
                  b'function attachMovie(a, b, c) {}\n')
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), source)
            self.assertEqual(result["attach_call_candidate_count"], 0)
            self.assertEqual(result["dynamic_argument_count"], 0)

    def test_escaped_literal_remains_opaque(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'attachMovie("\\x4b", "a", 1);')
            self.assertEqual(result["events"][0]["argument_shape"], "opaque_literal_or_empty")

    def test_tampered_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, attach, assets = fixture(root, b'attachMovie(roleName, "a", 1);')
            index["files"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash/length mismatch"):
                build_dynamic_argument_evidence(root, index, attach, assets)

    def test_mismatched_report_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, attach, assets = fixture(root, b'attachMovie(roleName, "a", 1);')
            attach["classification_counts"] = {"literal_export_match": 1}
            with self.assertRaisesRegex(ValueError, "classification counts mismatch"):
                build_dynamic_argument_evidence(root, index, attach, assets)

    def test_duplicate_script_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, attach, assets = fixture(root, b'attachMovie(roleName, "a", 1);')
            index["files"].append(dict(index["files"][0]))
            index["script_count"] = 2
            with self.assertRaisesRegex(ValueError, "Duplicate or invalid"):
                build_dynamic_argument_evidence(root, index, attach, assets)


if __name__ == "__main__":
    unittest.main()
