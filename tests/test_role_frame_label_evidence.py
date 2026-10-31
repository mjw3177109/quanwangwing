import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_role_frame_label_evidence import build_evidence
from build_role_timeline_call_evidence import scan_calls


class RoleFrameLabelEvidenceTests(unittest.TestCase):
    def fixture(self, root, source):
        path = "scripts/__Packages/Kyo_role.as"
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(source)
        digest = hashlib.sha256(source).hexdigest()
        sha = "a" * 64
        role = {"character_candidate": "Kyo", "variant": "base"}
        export = {"source_sha256": sha, "script_count": 1, "files": [
            {"path": path, "size_bytes": len(source), "sha256": digest}]}
        crosswalk = {"source_sha256": sha, "role_variant_count": 1, "roles": [
            {**role, "verified_as2_script_path": path, "verified_as2_script_sha256": digest,
             "verified_as2_script_size_bytes": len(source), "export_assets_character_id": 42,
             "sprite_timeline": {"sprite_character_id": 42}}]}
        calls = scan_calls(source)
        call_index = {"source_sha256": sha, "role_variant_count": 1,
                      "call_candidate_count": len(calls),
                      "argument_kind_counts": {"string_literal": sum(
                          c["argument_kind"] == "string_literal" for c in calls)},
                      "roles": [{**role, "verified_as2_script_path": path,
                                 "verified_as2_script_sha256": digest,
                                 "call_candidate_count": len(calls), "calls": calls}]}
        timeline = {"source_sha256": sha, "timeline_count": 2, "timelines": [
            {"timeline": "sprite:42", "frame_labels": [
                {"label": "idle", "frame": 1}, {"label": "repeat", "frame": 2},
                {"label": "repeat", "frame": 3}]},
            {"timeline": "sprite:55", "frame_labels": [{"label": "elsewhere", "frame": 4}]}]}
        return export, crosswalk, call_index, timeline

    def test_matches_without_exposing_labels(self):
        source = (b'this.gotoAndStop("idle"); this.gotoAndPlay("repeat"); '
                  b'this.gotoAndStop("elsewhere"); this.gotoAndPlay("missing"); '
                  b'this.gotoAndStop("a\\\"b"); this.gotoAndStop(frame);')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_evidence(root, *self.fixture(root, source))
            self.assertEqual(result["call_candidate_count"], 6)
            self.assertEqual(result["string_literal_call_count"], 5)
            self.assertEqual(result["frame_label_match_categories"], {
                "own_unique_candidate": 1, "own_ambiguous_candidate": 1,
                "other_only_candidate": 1, "not_found": 1, "escaped_or_unparsed": 1})
            self.assertFalse(any(c["runtime_binding_verified"] for c in result["roles"][0]["calls"]))
            serialized = json.dumps(result)
            for label in ("idle", "repeat", "elsewhere", "missing", 'a\\"b'):
                self.assertNotIn(label, serialized)

    def test_mismatched_hash_or_callsite_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = list(self.fixture(root, b'this.gotoAndPlay("idle");'))
            args[1]["roles"][0]["verified_as2_script_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "hash/length"):
                build_evidence(root, *args)
            args = list(self.fixture(root, b'this.gotoAndPlay("idle");'))
            args[2]["roles"][0]["calls"][0]["line"] = 999
            with self.assertRaisesRegex(ValueError, "Callsite provenance"):
                build_evidence(root, *args)

    def test_duplicate_timeline_and_source_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = list(self.fixture(root, b'this.gotoAndPlay("idle");'))
            args[3]["timelines"][1]["timeline"] = "sprite:42"
            with self.assertRaisesRegex(ValueError, "duplicate timeline"):
                build_evidence(root, *args)
            args = list(self.fixture(root, b'this.gotoAndPlay("idle");'))
            args[3]["source_sha256"] = "c" * 64
            with self.assertRaisesRegex(ValueError, "source SHA-256"):
                build_evidence(root, *args)

    def test_no_string_calls_keeps_zero_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_evidence(root, *self.fixture(root, b'this.gotoAndPlay(frame);'))
            self.assertEqual(result["string_literal_call_count"], 0)
            self.assertEqual(sum(result["frame_label_match_categories"].values()), 0)
