import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_as2_semantic_index import build_index, inspect_source


class AS2SemanticIndexTests(unittest.TestCase):
    def test_comments_and_strings_do_not_generate_evidence(self):
        source = b'''// function Fake() { hitTest() }
class Kyo_role extends RoleBase {
  function start() { Key.isDown(65); this.hitTest(target); }
  var ignored = "gotoAndPlay(2) function Fake2()";
  /* function Hidden() { attachMovie() } */
  function stop() { gotoAndStop(3); }
}
'''
        hints = inspect_source(source)
        self.assertEqual([x["name"] for x in hints["named_functions"]], ["start", "stop"])
        self.assertEqual([x["line"] for x in hints["named_functions"]], [3, 6])
        self.assertEqual(hints["declared_classes"][0]["name"], "Kyo_role")
        self.assertEqual(hints["extends_candidates"], ["RoleBase"])
        self.assertEqual(hints["marker_counts"]["keyboard"], 1)
        self.assertEqual(hints["marker_counts"]["hit_test"], 1)
        self.assertEqual(hints["marker_counts"]["timeline_jump"], 1)
        self.assertEqual(hints["marker_counts"]["sprite_attach"], 0)
        self.assertNotIn("Fake", str(hints))

    def test_role_linkage_is_metadata_only_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / "__Packages" / "Kyo_role.as"
            p.parent.mkdir(parents=True)
            raw = b"class Kyo_role { function attack() { this.hitTest(other); } }"
            p.write_bytes(raw)
            export = {
                "source_sha256": "a" * 64, "script_count": 1,
                "verified_noop_empty_count": 0, "unexpected_empty_count": 0,
                "files": [{"path": "scripts/__Packages/Kyo_role.as",
                           "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}]
            }
            assets = {"source_sha256": "a" * 64,
                      "character_class_candidates": [{"class_name": "Kyo",
                         "base_role_character_id": 123, "type2_role_character_id": None}]}
            result = build_index(root, export, assets)
            self.assertEqual(result["verified_script_count"], 1)
            self.assertTrue(result["role_script_candidates"][0]["export_present"])
            self.assertEqual(result["role_script_candidates"][0]["named_function_count"], 1)
            self.assertEqual(result["candidate_scripts"][0]["named_functions"][0]["name"], "attack")
            self.assertNotIn("this.hitTest(other)", str(result))
            p.write_bytes(raw + b"x")
            with self.assertRaisesRegex(ValueError, "hash/length mismatch"):
                build_index(root, export, assets)

    def test_source_mismatch_and_path_traversal_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            export = {"source_sha256": "a", "script_count": 1, "files": [
                {"path": "scripts/../../private.as", "size_bytes": 0,
                 "sha256": hashlib.sha256(b"").hexdigest()}]}
            assets = {"source_sha256": "b", "character_class_candidates": []}
            with self.assertRaisesRegex(ValueError, "SWF SHA-256 mismatch"):
                build_index(Path(directory), export, assets)
            assets["source_sha256"] = "a"
            with self.assertRaisesRegex(ValueError, "Invalid script relative path"):
                build_index(Path(directory), export, assets)

    def test_partial_critical_role_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "__Packages" / "role_corn" / "Role.as"
            path.parent.mkdir(parents=True)
            raw = b"x" * 144
            path.write_bytes(raw)
            export = {"source_sha256": "a", "script_count": 1,
                      "files": [{"path": "scripts/__Packages/role_corn/Role.as",
                                 "size_bytes": len(raw),
                                 "sha256": hashlib.sha256(raw).hexdigest()}]}
            assets = {"source_sha256": "a", "character_class_candidates": []}
            with self.assertRaisesRegex(ValueError, "unexpectedly short"):
                build_index(root, export, assets)
