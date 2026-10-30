import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_timeline_index import build_timeline_index
from swf_inventory import inventory
from test_swf_inventory import fixture, tag


def reference_fixture() -> bytes:
    prefix = fixture()[:21]  # SWF header, RECT, frame rate/count
    sprite = struct.pack("<HH", 5, 1) + tag(1) + tag(0)
    tags = (
        tag(39, sprite)
        + tag(14, struct.pack("<H", 17) + b"\x00\x00")
        + tag(56, struct.pack("<HH", 1, 5) + b"__Packages.Kyo_role\x00")
        + tag(26, bytes([0x02]) + struct.pack("<HH", 3, 5))
        + tag(26, bytes([0x01]) + struct.pack("<H", 3))
        + tag(43, b"idle\x00")
        + tag(15, struct.pack("<H", 17) + b"\x00")
        + tag(59, struct.pack("<H", 5) + b"\x00")
        + tag(253, b"\x01\x02")
        + tag(12, b"\x00")
        + tag(28, struct.pack("<H", 3))
        + tag(1) + tag(0)
    )
    raw = prefix + tags
    return raw[:4] + struct.pack("<I", len(raw)) + raw[8:]


class TimelineReferenceTests(unittest.TestCase):
    def test_references_are_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.swf"
            path.write_bytes(reference_fixture())
            manifest = inventory(path)
            placements = [t for t in manifest["tags"] if t["tag_code"] == 26]
            self.assertEqual(placements[0]["character_id_reference"], 5)
            self.assertEqual(placements[0]["depth"], 3)
            self.assertNotIn("character_id_reference", placements[1])
            self.assertTrue(placements[1]["move"])
            scripts = [s for s in manifest["scripts"] if s["tag_code"] == 59]
            self.assertEqual(scripts[0]["init_target_sprite_id"], 5)
            result = build_timeline_index(manifest)
            self.assertEqual(result["timeline_count"], 2)
            self.assertEqual(result["script_event_count"], 2)
            self.assertEqual(result["sound_event_count"], 1)
            self.assertEqual(result["frame_label_count"], 1)
            self.assertEqual(result["unknown_tag_253_next_code_counts"], {"12": 1})
            self.assertEqual(result["references_without_local_definition"], [])
            main = result["timelines"][0]
            self.assertEqual(main["timeline"], "main")
            self.assertEqual(main["observed_show_frames"], 1)
            self.assertEqual(main["frame_labels"][0]["label"], "idle")
            self.assertEqual(main["display_events"][0]["export_names"], ["__Packages.Kyo_role"])
            self.assertEqual(main["sound_events"][0]["sound_id"], 17)
            self.assertEqual(main["script_events"][0]["target_export_names"], ["__Packages.Kyo_role"])
            self.assertNotIn("payload", json.dumps(result))

    def test_truncated_reference_is_rejected(self):
        prefix = fixture()[:21]
        raw = prefix + tag(26, b"\x02\x01\x00") + tag(1) + tag(0)
        raw = raw[:4] + struct.pack("<I", len(raw)) + raw[8:]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.swf"
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "Truncated placement character ID"):
                inventory(path)

    @unittest.skipUnless((ROOT / "拳皇wing1.4.swf").is_file(), "original SWF not present")
    def test_original_unknown_tag_adjacency(self):
        manifest = inventory(ROOT / "拳皇wing1.4.swf")
        result = build_timeline_index(manifest)
        self.assertEqual(result["timeline_count"], 1776)
        self.assertEqual(result["script_event_count"], 3065)
        self.assertEqual(result["unknown_tag_253_next_code_counts"],
                         {"12": 536, "26": 1991, "34": 3, "59": 199})
        self.assertEqual(result["timelines"][0]["declared_frames"], 39)
        self.assertEqual(result["timelines"][0]["observed_show_frames"], 39)


if __name__ == "__main__":
    unittest.main()
