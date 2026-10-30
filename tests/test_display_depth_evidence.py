import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_display_depth_evidence import build_display_depth_evidence

def fixture():
    def tag(code, frame, offset, **kwargs):
        return {"timeline": "main", "tag_code": code, "frame": frame,
                "offset_uncompressed": offset, **kwargs}
    return {"source": {"sha256": "a" * 64}, "stage": {"frame_count": 3}, "tags": [
        tag(4, 0, 20, depth=2, character_id_reference=7),
        tag(26, 0, 30, depth=2, move=True),
        tag(1, 0, 40),
        tag(70, 1, 50, depth=2, move=True, character_id_reference=8),
        tag(26, 1, 60, depth=4, move=True),
        tag(1, 1, 70),
        tag(28, 2, 80, depth=2),
        tag(5, 2, 90, depth=4, character_id_reference=99),
        tag(1, 2, 100),
        tag(0, 3, 110),
    ]}

class DisplayDepthEvidenceTests(unittest.TestCase):
    def test_depth_states_and_unresolved_modify(self):
        r = build_display_depth_evidence(fixture())
        frames = r["timelines"][0]["frames"]
        self.assertEqual(frames[0]["active_depths"], [{"depth": 2, "character_id": 7}])
        self.assertEqual(frames[1]["active_depths"], [{"depth": 2, "character_id": 8}, {"depth": 4, "character_id": None}])
        self.assertEqual(frames[2]["active_depths"], [])
        self.assertEqual(r["display_event_count"], 6)
        self.assertEqual(r["anomaly_counts"], {"modify_missing_depth": 1})
    def test_detects_overwrite_without_move(self):
        m = fixture()
        m["tags"].insert(1, {"timeline": "main", "tag_code": 26, "frame": 0,
                             "offset_uncompressed": 25, "depth": 2,
                             "move": False, "character_id_reference": 9})
        r = build_display_depth_evidence(m)
        self.assertEqual(r["anomaly_counts"], {"modify_missing_depth": 1, "placement_over_existing_depth": 1})
        self.assertEqual(r["timelines"][0]["frames"][0]["active_depths"][0]["character_id"], 9)
    def test_remove_mismatch_is_reported(self):
        m = fixture()
        m["tags"][7]["character_id_reference"] = 1
        self.assertEqual(build_display_depth_evidence(m)["anomaly_counts"], {"modify_missing_depth": 1})
        m["tags"][6]["tag_code"] = 5
        m["tags"][6]["character_id_reference"] = 1
        self.assertEqual(build_display_depth_evidence(m)["anomaly_counts"]["remove_character_mismatch"], 1)
    def test_bad_frame_order_fails(self):
        m = fixture()
        m["tags"][5]["frame"] = 0
        with self.assertRaisesRegex(ValueError, "Non-sequential ShowFrame"):
            build_display_depth_evidence(m)
    def test_non_increasing_offsets_fail(self):
        m = fixture()
        m["tags"][1]["offset_uncompressed"] = 20
        with self.assertRaisesRegex(ValueError, "Non-increasing"):
            build_display_depth_evidence(m)
    def test_missing_sprite_declaration_fails(self):
        m = fixture()
        m["tags"].append({"timeline": "sprite:4", "tag_code": 1,
                          "frame": 0, "offset_uncompressed": 120})
        with self.assertRaisesRegex(ValueError, "Timeline set"):
            build_display_depth_evidence(m)
    def test_frame_count_mismatch_is_explicit(self):
        m = fixture()
        m["stage"]["frame_count"] = 4
        self.assertEqual(build_display_depth_evidence(m)["frame_count_mismatch_timelines"], 1)
    def test_bad_sha_rejected(self):
        m = fixture()
        m["source"]["sha256"] = "invalid"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_display_depth_evidence(m)
    def test_no_source_or_transform_payloads(self):
        r = build_display_depth_evidence(fixture())
        self.assertNotIn("matrix", str(r))
        self.assertNotIn("payload", str(r["timelines"]))
        self.assertNotIn("script_body", str(r))

if __name__ == "__main__":
    unittest.main()
