import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_role_label_attach_join import build_join
from build_role_frame_label_evidence import build_evidence
from build_role_timeline_call_evidence import scan_calls


class RoleLabelAttachJoinTests(unittest.TestCase):
    def fixture(self, root):
        raw = (b'this.gotoAndPlay("idle"); this.gotoAndStop("other"); '
               b'this.gotoAndPlay("loose"); this.gotoAndStop("absent");')
        path = "scripts/__Packages/Kyo_role.as"
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        sha = "a" * 64
        role = {"character_candidate": "Kyo", "variant": "base"}
        export = {"source_sha256": sha, "script_count": 1,
                  "total_bytes": len(raw), "unexpected_empty_count": 0,
                  "files": [{"path": path, "size_bytes": len(raw), "sha256": digest}]}
        crosswalk = {"source_sha256": sha, "role_variant_count": 1, "roles": [
            {**role, "verified_as2_script_path": path,
             "verified_as2_script_sha256": digest,
             "verified_as2_script_size_bytes": len(raw),
             "export_assets_character_id": 42,
             "sprite_timeline": {"sprite_character_id": 42}}]}
        parsed = scan_calls(raw)
        calls = {"source_sha256": sha, "role_variant_count": 1,
                 "call_candidate_count": len(parsed),
                 "argument_kind_counts": {"string_literal": len(parsed)},
                 "roles": [{**role, "verified_as2_script_path": path,
                            "verified_as2_script_sha256": digest,
                            "call_candidate_count": len(parsed), "calls": parsed}]}
        timeline = {"source_sha256": sha, "timeline_count": 3, "timelines": [
            {"timeline": "sprite:42", "frame_labels": [{"label": "idle", "frame": 1}]},
            {"timeline": "sprite:55", "frame_labels": [{"label": "other", "frame": 2}]},
            {"timeline": "sprite:66", "frame_labels": [{"label": "loose", "frame": 1}]}]}
        frame = build_evidence(root, export, crosswalk, calls, timeline)
        assets = {"source_sha256": sha, "exported_symbol_count": 2,
                  "assets": [{"character_id": cid, "category": "sprite"}
                             for cid in (42, 55, 66)],
                  "export_assets": [
                      {"character_id": 42, "name": "__Packages.Kyo_role"},
                      {"character_id": 55, "name": "fight_mc"}]}
        attach = {"source_sha256": sha, "verified_script_count": 1,
                  "verified_script_bytes": len(raw), "attach_call_candidate_count": 1,
                  "classification_counts": {"literal_export_match": 1},
                  "events": [{"classification": "literal_export_match",
                              "matched_export_assets": [
                                  {"name": "fight_mc", "character_id": 55,
                                   "role_candidate": False}]}]}
        return [export, crosswalk, calls, frame, timeline, assets, attach]

    def test_all_four_candidate_classes_and_no_original_labels_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_join(root, *self.fixture(root))
            self.assertEqual(result["classification_counts"], {
                "no_sprite_label_candidate": 1,
                "sprite_not_exported": 1,
                "exported_no_literal_attach": 1,
                "literal_attach_overlap": 1})
            self.assertEqual(result["literal_attach_sprite_symbol_count"], 1)
            rows = result["roles"][0]["calls"]
            self.assertEqual([r["exported_candidate_sprite_count"] for r in rows],
                             [1, 1, 0, 0])
            self.assertFalse(any(r["runtime_binding_verified"] for r in rows))
            payload = json.dumps(result)
            for secret in ("idle", "other", "loose", "absent", "fight_mc",
                           "__Packages.Kyo_role", '"candidate_sprite_id"'):
                self.assertNotIn(secret, payload)

    def test_mismatched_swf_or_spoofed_attach_target_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.fixture(root)
            args[6]["source_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "source SHA-256"):
                build_join(root, *args)
            args = self.fixture(root)
            args[6]["events"][0]["matched_export_assets"][0]["character_id"] = 66
            with self.assertRaisesRegex(ValueError, "symbol provenance"):
                build_join(root, *args)

    def test_tampered_role_script_and_callsite_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.fixture(root)
            (root / "scripts/__Packages/Kyo_role.as").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash/length"):
                build_join(root, *args)
            args = self.fixture(root)
            args[3]["roles"][0]["calls"][0]["line"] = 99
            with self.assertRaisesRegex(ValueError, "callsite provenance"):
                build_join(root, *args)

    def test_non_sprite_export_and_dynamic_argument_do_not_prove_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.fixture(root)
            args[5]["assets"][1]["category"] = "shape"
            with self.assertRaisesRegex(ValueError, "lacks Sprite definition"):
                build_join(root, *args)
            args = self.fixture(root)
            args[6]["events"] = [{"classification": "dynamic_or_unresolved",
                                  "matched_export_assets": []}]
            args[6]["classification_counts"] = {"dynamic_or_unresolved": 1}
            result = build_join(root, *args)
            self.assertEqual(result["unresolved_attach_call_count"], 1)
            self.assertEqual(result["classification_counts"]["literal_attach_overlap"], 0)


if __name__ == "__main__":
    unittest.main()
