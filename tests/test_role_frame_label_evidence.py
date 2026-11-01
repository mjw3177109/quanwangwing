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

    def test_static_placement_graph_direct_nested_and_unreachable(self):
        source = (b'this.gotoAndPlay("idle"); this.gotoAndPlay("elsewhere"); '
                  b'this.gotoAndPlay("deep"); this.gotoAndPlay("stray"); '
                  b'this.gotoAndPlay("missing");')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = list(self.fixture(root, source))
            timeline = args[3]
            timeline["timelines"][0]["display_events"] = [
                {"kind": "place", "character_id": 55},
                {"kind": "place", "character_id": 999}]  # Non-Sprite reference
            timeline["timelines"][1]["display_events"] = [
                {"kind": "place", "character_id": 77},
                {"kind": "place", "character_id": 42}]  # Cycle must terminate
            timeline["timelines"].extend([
                {"timeline": "sprite:77", "frame_labels": [{"label": "deep", "frame": 2}]},
                {"timeline": "sprite:99", "frame_labels": [{"label": "stray", "frame": 1}]}])
            timeline["timeline_count"] = 4
            result = build_evidence(root, *args)
            self.assertEqual(result["static_placement_relation_counts"], {
                "own_timeline": 1, "direct_child_candidate": 1,
                "nested_descendant_candidate": 1, "other_unreachable_static": 1,
                "no_matching_label": 1, "escaped_or_unparsed": 0})
            calls = result["roles"][0]["calls"]
            self.assertEqual([c["minimum_static_placement_hops"] for c in calls],
                             [0, 1, 2, None, None])
            self.assertEqual(calls[2]["statically_reachable_timeline_count"], 1)
            self.assertFalse(any(c["runtime_binding_verified"] for c in calls))
            for label in ("idle", "elsewhere", "deep", "stray", "missing"):
                self.assertNotIn(label, json.dumps(result))

    def test_static_placement_rejects_invalid_character_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = list(self.fixture(root, b'this.gotoAndPlay("elsewhere");'))
            args[3]["timelines"][0]["display_events"] = [
                {"kind": "place", "character_id": -55}]
            with self.assertRaisesRegex(ValueError, "PlaceObject character ID"):
                build_evidence(root, *args)

    def test_other_label_without_static_path_is_not_runtime_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_evidence(root, *self.fixture(
                root, b'this.gotoAndPlay("elsewhere");'))
            self.assertEqual(result["frame_label_match_categories"]["other_only_candidate"], 1)
            self.assertEqual(result["static_placement_relation_counts"]["other_unreachable_static"], 1)
            self.assertIsNone(result["roles"][0]["calls"][0]["minimum_static_placement_hops"])
            self.assertFalse(result["roles"][0]["calls"][0]["runtime_binding_verified"])


    def test_original_label_target_timeline_kinds_are_distinct_and_private(self):
        source = (b'this.gotoAndPlay("idle"); this.gotoAndStop("elsewhere"); '
                  b'this.gotoAndPlay("mainonly"); this.gotoAndStop("not_here"); '
                  b'this.gotoAndStop("a\\\"b");')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = list(self.fixture(root, source))
            args[3]["timelines"].append({"timeline": "main", "frame_labels": [
                {"label": "elsewhere", "frame": 1},
                {"label": "mainonly", "frame": 2}]})
            args[3]["timeline_count"] = 3
            result = build_evidence(root, *args)
            self.assertEqual(result["target_timeline_kind_counts"], {
                "main_only": 1, "sprite_only": 1, "main_and_sprite": 1,
                "other_or_mixed": 0, "no_match": 1, "escaped_or_unparsed": 1})
            calls = result["roles"][0]["calls"]
            self.assertEqual([c["target_timeline_kind"] for c in calls],
                             ["sprite_only", "main_and_sprite", "main_only",
                              "no_match", "escaped_or_unparsed"])
            self.assertEqual([c["matching_main_timeline_count"] for c in calls],
                             [0, 1, 1, 0, 0])
            self.assertEqual([c["matching_sprite_timeline_count"] for c in calls],
                             [1, 1, 0, 0, 0])
            self.assertFalse(any(c["runtime_binding_verified"] for c in calls))
            output = json.dumps(result)
            for original_label in ("idle", "elsewhere", "mainonly", "not_here"):
                self.assertNotIn(original_label, output)

    def test_duplicate_frame_labels_do_not_duplicate_candidate_timelines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_evidence(root, *self.fixture(
                root, b'this.gotoAndPlay("repeat");'))
            row = result["roles"][0]["calls"][0]
            self.assertEqual(row["matching_timeline_count"], 1)
            self.assertEqual(row["matching_sprite_timeline_count"], 1)
            self.assertEqual(row["own_timeline_label_occurrences"], 2)
            self.assertEqual(row["target_timeline_kind"], "sprite_only")

    def test_unrecognized_timeline_namespace_remains_unresolved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = list(self.fixture(root, b'this.gotoAndPlay("legacy");'))
            args[3]["timelines"].append({"timeline": "custom:9",
                                         "frame_labels": [{"label": "legacy", "frame": 1}]})
            args[3]["timeline_count"] = 3
            result = build_evidence(root, *args)
            row = result["roles"][0]["calls"][0]
            self.assertEqual(row["target_timeline_kind"], "other_or_mixed")
            self.assertEqual(row["matching_other_timeline_count"], 1)
            self.assertFalse(row["runtime_binding_verified"])
