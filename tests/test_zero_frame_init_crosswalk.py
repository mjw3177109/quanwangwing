import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_zero_frame_init_crosswalk import build_zero_frame_init_crosswalk

SHA = "a" * 64


def fixture():
    manifest = {
        "source": {"sha256": SHA},
        "tags": [
            {"timeline": "main", "tag_code": 39, "offset_uncompressed": 12,
             "character_id": 7, "sprite_frame_count": 1},
            {"timeline": "sprite:7", "tag_code": 0, "offset_uncompressed": 16},
            {"timeline": "main", "tag_code": 59, "offset_uncompressed": 20,
             "frame": 0, "length": 24, "init_target_sprite_id": 7},
        ],
    }
    zero = {
        "source_sha256": SHA, "zero_show_frame_sprite_count": 1,
        "static_init_action_reference_count": 1,
        "sprites": [{
            "sprite_character_id": 7, "timeline": "sprite:7", "declared_frames": 1,
            "observed_show_frames": 0, "definition_offset_uncompressed": 12,
            "internal_tag_counts_by_code": {}, "static_place_reference_count": 0,
            "static_init_action_reference_count": 1, "export_asset_name_count": 1,
            "static_inbound_references": [{"kind": "init_action", "tag_code": 59,
                "timeline": "main", "frame_zero_based": 0, "offset_uncompressed": 20}],
        }],
    }
    scripts = {
        "source_sha256": SHA, "script_container_count": 1,
        "script_container_counts_by_tag": {"59": 1},
        "entries": [{"timeline": "main", "tag_code": 59, "offset_uncompressed": 20,
            "frame_zero_based": 0, "frame_one_based": 1, "length": 24,
            "init_target_sprite_id": 7}],
    }
    return manifest, zero, scripts


class ZeroFrameInitCrosswalkTests(unittest.TestCase):
    def test_verified_join(self):
        report = build_zero_frame_init_crosswalk(*fixture())
        self.assertEqual(report["matched_init_script_count"], 1)
        self.assertEqual(report["init_script_container_bytes_total"], 24)
        self.assertEqual(report["sprites_with_no_internal_tags"], 1)
        self.assertEqual(report["init_scripts_on_main_frame_zero"], 1)

    def test_unreferenced_sprite(self):
        m, z, s = fixture()
        z["sprites"][0]["static_inbound_references"] = []
        z["sprites"][0]["static_init_action_reference_count"] = 0
        z["static_init_action_reference_count"] = 0
        self.assertEqual(build_zero_frame_init_crosswalk(m, z, s)["matched_init_script_count"], 0)

    def test_nonempty_sprite_not_misreported(self):
        m, z, s = fixture()
        m["tags"].insert(1, {"timeline": "sprite:7", "tag_code": 12,
                               "offset_uncompressed": 14, "frame": 0, "length": 3})
        s["entries"].append({"timeline": "sprite:7", "tag_code": 12,
                              "offset_uncompressed": 14, "frame_zero_based": 0,
                              "frame_one_based": 1, "length": 3})
        s["script_container_count"] = 2
        s["script_container_counts_by_tag"]["12"] = 1
        z["sprites"][0]["internal_tag_counts_by_code"] = {"12": 1}
        self.assertEqual(build_zero_frame_init_crosswalk(m, z, s)["sprites_with_no_internal_tags"], 0)

    def test_missing_script_entry_rejected(self):
        m, z, s = fixture()
        s["entries"].clear()
        with self.assertRaisesRegex(ValueError, "accounting"):
            build_zero_frame_init_crosswalk(m, z, s)

    def test_tampered_target_rejected(self):
        m, z, s = fixture()
        s["entries"][0]["init_target_sprite_id"] = 9
        with self.assertRaisesRegex(ValueError, "target"):
            build_zero_frame_init_crosswalk(m, z, s)

    def test_tampered_script_length_rejected(self):
        m, z, s = fixture()
        s["entries"][0]["length"] = 999
        with self.assertRaisesRegex(ValueError, "disagrees"):
            build_zero_frame_init_crosswalk(m, z, s)

    def test_hash_mismatch_rejected(self):
        m, z, s = fixture()
        z["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_zero_frame_init_crosswalk(m, z, s)

    def test_duplicate_script_offset_rejected(self):
        m, z, s = fixture()
        m["tags"].append({"timeline": "main", "tag_code": 12,
                          "offset_uncompressed": 30, "frame": 0, "length": 4})
        s["entries"].append(copy.deepcopy(s["entries"][0]))
        s["script_container_count"] = 2
        s["script_container_counts_by_tag"]["12"] = 1
        with self.assertRaisesRegex(ValueError, "Duplicate script entry"):
            build_zero_frame_init_crosswalk(m, z, s)

    def test_bad_reference_offset_rejected(self):
        m, z, s = fixture()
        z["sprites"][0]["static_inbound_references"][0]["offset_uncompressed"] = 21
        with self.assertRaisesRegex(ValueError, "reference"):
            build_zero_frame_init_crosswalk(m, z, s)

    def test_bad_definition_offset_rejected(self):
        m, z, s = fixture()
        z["sprites"][0]["definition_offset_uncompressed"] = 999
        with self.assertRaisesRegex(ValueError, "sprite disagrees"):
            build_zero_frame_init_crosswalk(m, z, s)

    def test_no_source_payload_or_export_names(self):
        report = build_zero_frame_init_crosswalk(*fixture())
        self.assertNotIn("script_body", str(report))
        self.assertNotIn("export_asset_name", str(report))
        self.assertNotIn("source_code", str(report))


if __name__ == "__main__":
    unittest.main()
