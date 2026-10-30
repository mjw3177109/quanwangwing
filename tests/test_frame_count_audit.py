import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_frame_count_audit import build_frame_count_audit


def fixture():
    def tag(timeline, code, frame, offset, **extra):
        return {"timeline": timeline, "tag_code": code, "frame": frame,
                "offset_uncompressed": offset, **extra}
    m = {"source": {"sha256": "a" * 64}, "stage": {"frame_count": 2}, "tags": [
        tag("main", 39, 0, 10, character_id=7, sprite_frame_count=3),
        tag("sprite:7", 12, 0, 20),
        tag("sprite:7", 1, 0, 30),
        tag("sprite:7", 1, 1, 40),
        tag("sprite:7", 0, 2, 50),
        tag("main", 1, 0, 60),
        tag("main", 1, 1, 70),
        tag("main", 0, 2, 80),
    ]}
    return m, depth_for(m)


def depth_for(m):
    reports = []
    for name in ("main", "sprite:7"):
        show = [t for t in m["tags"] if t["timeline"] == name and t["tag_code"] == 1]
        declared = m["stage"]["frame_count"] if name == "main" else m["tags"][0]["sprite_frame_count"]
        reports.append({"timeline": name, "declared_frames": declared,
                        "observed_show_frames": len(show),
                        "frame_count_mismatch": declared != len(show),
                        "frames": [{"frame_zero_based": i, "show_frame_offset_uncompressed": t["offset_uncompressed"]}
                                   for i, t in enumerate(show)]})
    return {"source_sha256": m["source"]["sha256"], "timeline_count": len(reports),
            "show_frame_count": sum(r["observed_show_frames"] for r in reports),
            "frame_count_mismatch_timelines": sum(r["frame_count_mismatch"] for r in reports),
            "timelines": reports}


class FrameCountAuditTests(unittest.TestCase):
    def test_shortfall_and_metadata(self):
        m, d = fixture()
        r = build_frame_count_audit(m, d)
        self.assertEqual(r["mismatch_count"], 1)
        self.assertEqual(r["mismatch_direction_counts"], {"shortfall": 1})
        self.assertEqual(r["delta_histogram"], {"-1": 1})
        self.assertEqual(r["mismatches"][0]["timeline"], "sprite:7")
        self.assertEqual(r["mismatches"][0]["script_tag_count"], 1)
        self.assertEqual(r["mismatches"][0]["end_tag_offset_uncompressed"], 50)
    def test_surplus(self):
        m, _ = fixture()
        m["tags"][0]["sprite_frame_count"] = 1
        d = depth_for(m)
        r = build_frame_count_audit(m, d)
        self.assertEqual(r["delta_histogram"], {"1": 1})
        self.assertEqual(r["mismatch_direction_counts"], {"surplus": 1})
    def test_no_mismatch(self):
        m, _ = fixture()
        m["tags"][0]["sprite_frame_count"] = 2
        d = depth_for(m)
        self.assertEqual(build_frame_count_audit(m, d)["mismatch_count"], 0)
    def test_wrong_hash_rejected(self):
        m, d = fixture()
        d["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            build_frame_count_audit(m, d)
    def test_tampered_offset_rejected(self):
        m, d = fixture()
        d["timelines"][1]["frames"][0]["show_frame_offset_uncompressed"] += 1
        with self.assertRaisesRegex(ValueError, "ShowFrame offset"):
            build_frame_count_audit(m, d)
    def test_missing_timeline_rejected(self):
        m, d = fixture()
        d["timelines"].pop()
        d["timeline_count"] -= 1
        with self.assertRaisesRegex(ValueError, "Timeline set mismatch"):
            build_frame_count_audit(m, d)
    def test_tampered_aggregate_rejected(self):
        m, d = fixture()
        d["frame_count_mismatch_timelines"] = 0
        with self.assertRaisesRegex(ValueError, "Aggregate frame accounting"):
            build_frame_count_audit(m, d)
    def test_duplicate_sprite_rejected(self):
        m, d = fixture()
        m["tags"].append(copy.deepcopy(m["tags"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate sprite"):
            build_frame_count_audit(m, d)
    def test_metadata_only(self):
        m, d = fixture()
        r = build_frame_count_audit(m, d)
        self.assertNotIn("payload", str(r["mismatches"]))
        self.assertNotIn("script_body", str(r))
        self.assertNotIn("image", str(r["mismatches"]))


if __name__ == "__main__":
    unittest.main()
