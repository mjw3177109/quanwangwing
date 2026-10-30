import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_runtime_attach_evidence import build_attach_evidence


def fixtures(root, source=b'this.attachMovie("__Packages.Kyo_role", "k", 1);'):
    rel = "scripts/__Packages/role_corn/Role.as"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source)
    sha = "f" * 64
    index = {"source_sha256": sha, "script_count": 1, "unexpected_empty_count": 0,
             "files": [{"path": rel, "size_bytes": len(source),
                        "sha256": hashlib.sha256(source).hexdigest()}]}
    assets = {"source_sha256": sha, "export_assets": [
        {"name": "__Packages.Kyo_role", "character_id": 77},
        {"name": "otherClip", "character_id": 88},
    ]}
    crosswalk = {"source_sha256": sha, "role_variant_count": 1,
                 "roles": [{"export_assets_character_id": 77}]}
    semantic = {"source_sha256": sha, "candidate_scripts": [
        {"path": rel, "function_scopes": [
            {"name": "spawn", "kind": "named_function", "start_line": 1, "end_line": 3}
        ]}
    ]}
    return index, assets, crosswalk, semantic


class AttachEvidenceTests(unittest.TestCase):
    def build(self, root, source):
        return build_attach_evidence(root, *fixtures(root, source))

    def test_matches_export_assets_and_role_id(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'this.attachMovie("__Packages.Kyo_role", "k", 1);')
            self.assertEqual(result["attach_call_candidate_count"], 1)
            self.assertEqual(result["matched_role_candidate_count"], 1)
            e = result["events"][0]
            self.assertEqual(e["classification"], "literal_export_match")
            self.assertEqual(e["matched_export_assets"][0]["character_id"], 77)
            self.assertEqual(e["function_scope_candidate"]["name"], "spawn")

    def test_unknown_literal_is_hashed_not_exposed(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'attachMovie("privateSecret", "a", 1);')
            self.assertEqual(result["classification_counts"], {"literal_unmatched": 1})
            self.assertNotIn("privateSecret", str(result))
            self.assertEqual(len(result["events"][0]["unmatched_literal_sha256"]), 64)

    def test_dynamic_argument_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'clip.attachMovie(roleName, "a", 1);')
            self.assertEqual(result["classification_counts"], {"dynamic_or_unresolved": 1})
            self.assertEqual(result["matched_role_candidate_count"], 0)

    def test_comments_strings_and_declaration_are_not_calls(self):
        source = (b'// attachMovie("otherClip", "x", 1)\n'
                  b'var s = "attachMovie(123)";\n'
                  b'function attachMovie(name, id, depth) {}\n'
                  b'/* attachMovie("otherClip", "x", 1) */\n')
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), source)
            self.assertEqual(result["attach_call_candidate_count"], 0)

    def test_source_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, assets, crosswalk, semantic = fixtures(root)
            index["files"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash/length mismatch"):
                build_attach_evidence(root, index, assets, crosswalk, semantic)

    def test_cross_index_swf_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, assets, crosswalk, semantic = fixtures(root)
            semantic["source_sha256"] = "e" * 64
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                build_attach_evidence(root, index, assets, crosswalk, semantic)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, assets, crosswalk, semantic = fixtures(root)
            index["files"][0]["path"] = "scripts/../secret.as"
            with self.assertRaisesRegex(ValueError, "invalid AS2 export path"):
                build_attach_evidence(root, index, assets, crosswalk, semantic)

    def test_escaped_literal_is_not_misidentified(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'attachMovie("__Packages.\\x4byo_role", "k", 1);')
            self.assertEqual(result["classification_counts"], {"dynamic_or_unresolved": 1})

    def test_multiple_calls_preserve_line_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.build(Path(d), b'attachMovie("otherClip", "a", 1);\nattachMovie(name, "b", 2);')
            self.assertEqual([e["line"] for e in result["events"]], [1, 2])
            self.assertEqual(result["attach_call_candidate_count"], 2)


if __name__ == "__main__":
    unittest.main()
