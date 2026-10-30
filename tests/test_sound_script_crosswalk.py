import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_sound_script_crosswalk import build_sound_script_crosswalk


def evidence():
    tags = [
        {"timeline": "main", "frame": 0, "offset_uncompressed": 20, "tag_code": 12},
        {"timeline": "main", "frame": 0, "offset_uncompressed": 30, "tag_code": 15, "sound_id_reference": 7},
        {"timeline": "main", "frame": 0, "offset_uncompressed": 40, "tag_code": 59},
        {"timeline": "main", "frame": 1, "offset_uncompressed": 60, "tag_code": 15, "sound_id_reference": 8},
        {"timeline": "sprite:9", "frame": 0, "offset_uncompressed": 80, "tag_code": 12},
        {"timeline": "sprite:9", "frame": 0, "offset_uncompressed": 90, "tag_code": 15, "sound_id_reference": 7},
    ]
    manifest = {"source": {"sha256": "a" * 64}, "tags": tags}
    script_entries = [{"timeline": t["timeline"], "frame_zero_based": t["frame"],
                       "offset_uncompressed": t["offset_uncompressed"], "tag_code": t["tag_code"]}
                      for t in tags if t["tag_code"] in (12, 59, 72, 82)]
    sound_events = [{"timeline": t["timeline"], "frame_zero_based": t["frame"],
                     "offset_uncompressed": t["offset_uncompressed"], "sound_id": t["sound_id_reference"]}
                    for t in tags if t["tag_code"] == 15]
    return (manifest,
            {"source_sha256": "a" * 64, "start_sound_count": 3, "start_events": sound_events},
            {"source_sha256": "a" * 64, "script_container_count": 3, "entries": script_entries})


class SoundScriptCrosswalkTests(unittest.TestCase):
    def test_same_frame_and_timeline_only(self):
        report = build_sound_script_crosswalk(*evidence())
        self.assertEqual(report["start_sound_count"], 3)
        self.assertEqual(report["sound_events_with_same_frame_scripts"], 2)
        self.assertEqual(report["sound_events_without_same_frame_scripts"], 1)
        self.assertEqual(report["same_frame_sound_script_pairs"], 3)
        self.assertEqual(report["start_sound_counts_by_id"], {"7": 2, "8": 1})
        self.assertEqual([s["relative_tag_order"] for s in report["events"][0]["same_frame_script_containers"]], ["before", "after"])
        self.assertEqual(report["events"][1]["same_frame_script_containers"], [])

    def test_sound_hash_mismatch_fails_closed(self):
        m, a, s = evidence()
        a["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_sound_script_crosswalk(m, a, s)

    def test_script_hash_mismatch_fails_closed(self):
        m, a, s = evidence()
        s["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_sound_script_crosswalk(m, a, s)

    def test_sound_id_tampering_fails_closed(self):
        m, a, s = evidence()
        a["start_events"][0]["sound_id"] = 99
        with self.assertRaisesRegex(ValueError, "StartSound report"):
            build_sound_script_crosswalk(m, a, s)

    def test_script_offset_tampering_fails_closed(self):
        m, a, s = evidence()
        s["entries"][0]["offset_uncompressed"] = 999
        with self.assertRaisesRegex(ValueError, "Script entry report"):
            build_sound_script_crosswalk(m, a, s)

    def test_missing_sound_event_fails_closed(self):
        m, a, s = evidence()
        a["start_events"].pop()
        with self.assertRaisesRegex(ValueError, "StartSound report"):
            build_sound_script_crosswalk(m, a, s)

    def test_script_count_tampering_fails_closed(self):
        m, a, s = evidence()
        s["script_container_count"] = 100
        with self.assertRaisesRegex(ValueError, "Script entry report"):
            build_sound_script_crosswalk(m, a, s)

    def test_no_sounds_is_valid(self):
        m, a, s = evidence()
        m["tags"] = [t for t in m["tags"] if t["tag_code"] != 15]
        a["start_events"] = []
        a["start_sound_count"] = 0
        report = build_sound_script_crosswalk(m, a, s)
        self.assertEqual(report["same_frame_sound_script_pairs"], 0)
        self.assertEqual(report["events"], [])


if __name__ == "__main__":
    unittest.main()
