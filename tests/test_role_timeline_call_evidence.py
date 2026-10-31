import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_role_timeline_call_evidence import scan_calls, build_evidence


class RoleTimelineCallTests(unittest.TestCase):
    def test_scan_calls_masks_comments_strings_and_preserves_numeric_frame(self):
        raw = b'''// gotoAndPlay(999)
var x = "gotoAndStop(888)";
function attack() { this.gotoAndPlay(12); this.gotoAndStop("idle"); }
/* gotoAndStop(999) */
this.gotoAndPlay(frame + 1);
function gotoAndPlay(n) { }
'''
        calls = scan_calls(raw)
        self.assertEqual([(x["method"], x["argument_kind"], x["literal_frame_candidate"])
                          for x in calls],
                         [("gotoAndPlay", "integer_literal", 12),
                          ("gotoAndStop", "string_literal", None),
                          ("gotoAndPlay", "dynamic_or_unresolved", None)])
        self.assertEqual([x["line"] for x in calls], [3, 3, 5])
        self.assertNotIn("idle", str(calls))

    def test_escaped_string_and_zero_frame_remain_lexical(self):
        calls = scan_calls(b'this.gotoAndStop("a\\\"b"); gotoAndPlay(0);')
        self.assertEqual(calls[0]["argument_kind"], "string_literal")
        self.assertEqual(calls[1]["literal_frame_candidate"], 0)

    def fixture(self, root):
        path = "scripts/__Packages/Kyo_role.as"
        source = b"this.gotoAndPlay(5); this.gotoAndStop(label);"
        p = root / path
        p.parent.mkdir(parents=True)
        p.write_bytes(source)
        digest = hashlib.sha256(source).hexdigest()
        sha = "a" * 64
        export = {"source_sha256": sha, "script_count": 1, "files": [
            {"path": path, "size_bytes": len(source), "sha256": digest}]}
        crosswalk = {"source_sha256": sha, "role_variant_count": 1, "roles": [
            {"character_candidate": "Kyo", "variant": "base", "verified_as2_script_path": path,
             "verified_as2_script_sha256": digest, "verified_as2_script_size_bytes": len(source)}]}
        return export, crosswalk, p

    def test_hash_verified_role_crosswalk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export, crosswalk, _ = self.fixture(root)
            result = build_evidence(root, export, crosswalk)
            self.assertEqual(result["call_candidate_count"], 2)
            self.assertEqual(result["argument_kind_counts"],
                             {"integer_literal": 1, "string_literal": 0, "dynamic_or_unresolved": 1})
            self.assertEqual(result["roles"][0]["calls"][0]["literal_frame_candidate"], 5)
            self.assertNotIn("this.gotoAndPlay", str(result))

    def test_source_and_hash_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export, crosswalk, path = self.fixture(root)
            crosswalk["source_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                build_evidence(root, export, crosswalk)
            crosswalk["source_sha256"] = export["source_sha256"]
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash/length mismatch"):
                build_evidence(root, export, crosswalk)

    def test_rejects_duplicate_roles_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export, crosswalk, _ = self.fixture(root)
            crosswalk["roles"].append(dict(crosswalk["roles"][0]))
            crosswalk["role_variant_count"] = 2
            with self.assertRaisesRegex(ValueError, "Duplicate role variant"):
                build_evidence(root, export, crosswalk)
            crosswalk["roles"].pop()
            crosswalk["role_variant_count"] = 1
            export["files"].append(dict(export["files"][0]))
            export["script_count"] = 2
            with self.assertRaisesRegex(ValueError, "duplicate FFDec export"):
                build_evidence(root, export, crosswalk)


if __name__ == "__main__":
    unittest.main()
