import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_placement_crosswalk import build_button_placement_crosswalk


def fixtures():
    sha = "a" * 64
    tag = {"tag_code": 34, "character_id": 7, "timeline": "main", "frame": 1, "offset_uncompressed": 10}
    place = {"tag_code": 26, "character_id_reference": 7, "timeline": "sprite:8", "frame": 2, "depth": 3, "offset_uncompressed": 20}
    manifest = {"source": {"sha256": sha}, "tag_counts_by_code": {"34": 1}, "tags": [tag, place]}
    buttons = {"source_sha256": sha, "define_button2_count": 1, "embedded_action_record_count": 1,
               "buttons": [{"character_id": 7, "timeline": "main", "frame_zero_based": 1,
                            "tag_offset_uncompressed": 10, "embedded_action_record_count": 1,
                            "embedded_action_records": [{"condition_flags": 8}]}]}
    timeline = {"source_sha256": sha, "timeline_count": 1, "timelines": [
        {"timeline": "sprite:8", "display_events": [{"kind": "place", "tag_code": 26,
            "character_id": 7, "frame": 2, "depth": 3, "offset_uncompressed": 20}]}]}
    return manifest, buttons, timeline


class ButtonPlacementCrosswalkTests(unittest.TestCase):
    def test_verified_nested_placement(self):
        report = build_button_placement_crosswalk(*fixtures())
        self.assertEqual(report["static_placement_count"], 1)
        self.assertEqual(report["nested_timeline_placement_count"], 1)
        self.assertEqual(report["action_bearing_buttons_with_static_placement"], 1)
        self.assertEqual(report["buttons"][0]["static_placements"][0]["depth"], 3)
        self.assertNotIn("script_body", str(report))

    def test_unplaced_button_is_reported_not_assumed_live(self):
        manifest, buttons, timeline = fixtures()
        timeline["timelines"][0]["display_events"] = []
        report = build_button_placement_crosswalk(manifest, buttons, timeline)
        self.assertEqual(report["buttons_without_static_placement"], 1)
        self.assertEqual(report["static_placement_count"], 0)

    def test_tampered_placement_depth_rejected(self):
        manifest, buttons, timeline = fixtures()
        timeline["timelines"][0]["display_events"][0]["depth"] = 9
        with self.assertRaisesRegex(ValueError, "placement tag provenance"):
            build_button_placement_crosswalk(manifest, buttons, timeline)

    def test_tampered_button_definition_rejected(self):
        manifest, buttons, timeline = fixtures()
        buttons["buttons"][0]["tag_offset_uncompressed"] = 99
        with self.assertRaisesRegex(ValueError, "definition provenance"):
            build_button_placement_crosswalk(manifest, buttons, timeline)

    def test_source_mismatch_rejected(self):
        manifest, buttons, timeline = fixtures()
        timeline["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "source provenance"):
            build_button_placement_crosswalk(manifest, buttons, timeline)

    def test_duplicate_button_id_rejected(self):
        manifest, buttons, timeline = fixtures()
        manifest["tags"].insert(1, {"tag_code": 34, "character_id": 7, "timeline": "main", "frame": 2, "offset_uncompressed": 11})
        manifest["tag_counts_by_code"]["34"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate DefineButton2"):
            build_button_placement_crosswalk(manifest, buttons, timeline)

    def test_duplicate_timeline_rejected(self):
        manifest, buttons, timeline = fixtures()
        timeline["timelines"].append(copy.deepcopy(timeline["timelines"][0]))
        timeline["timeline_count"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate or invalid timeline"):
            build_button_placement_crosswalk(manifest, buttons, timeline)

    def test_non_place_events_do_not_count(self):
        manifest, buttons, timeline = fixtures()
        timeline["timelines"][0]["display_events"].append({"kind": "remove", "character_id": 7})
        self.assertEqual(build_button_placement_crosswalk(manifest, buttons, timeline)["static_placement_count"], 1)

    def test_same_frame_label_and_script_co_location_is_metadata_only(self):
        manifest, buttons, timeline = fixtures()
        timeline["timelines"][0]["frame_labels"] = [{"frame": 2, "label": "do-not-publish"}]
        timeline["timelines"][0]["script_events"] = [{"frame": 2, "tag_code": 12}]
        report = build_button_placement_crosswalk(manifest, buttons, timeline)
        self.assertEqual(report["placement_same_frame_context_counts"]["both"], 1)
        self.assertEqual(report["raw_button_condition_flags_histogram"], {"0x0008": 1})
        self.assertNotIn("do-not-publish", str(report))

    def test_label_only_and_script_only_contexts(self):
        manifest, buttons, timeline = fixtures()
        line = timeline["timelines"][0]
        line["frame_labels"] = [{"frame": 2, "label": "private"}]
        self.assertEqual(build_button_placement_crosswalk(manifest, buttons, timeline)["placement_same_frame_context_counts"]["label_only"], 1)
        line["frame_labels"] = []
        line["script_events"] = [{"frame": 2, "tag_code": 12}]
        self.assertEqual(build_button_placement_crosswalk(manifest, buttons, timeline)["placement_same_frame_context_counts"]["script_only"], 1)

    def test_no_context_is_neither(self):
        report = build_button_placement_crosswalk(*fixtures())
        self.assertEqual(report["placement_same_frame_context_counts"]["neither"], 1)
        self.assertEqual(sum(report["placement_same_frame_context_counts"].values()), report["static_placement_count"])

    def test_invalid_condition_flags_rejected(self):
        manifest, buttons, timeline = fixtures()
        buttons["buttons"][0]["embedded_action_records"][0]["condition_flags"] = 65536
        with self.assertRaisesRegex(ValueError, "condition flags"):
            build_button_placement_crosswalk(manifest, buttons, timeline)


if __name__ == "__main__":
    unittest.main()
