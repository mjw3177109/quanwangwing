import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_frame_count_audit import build_frame_count_audit
from build_frame_tail_evidence import build_frame_tail_evidence
from build_zero_frame_sprite_references import build_zero_frame_sprite_references
from test_frame_count_audit import fixture, depth_for


def zero_fixture():
    m, _ = fixture()
    m["tags"] = [t for t in m["tags"]
                 if not (t["timeline"] == "sprite:7" and t["tag_code"] == 1)]
    for tag in m["tags"]:
        if tag["timeline"] == "sprite:7":
            tag["frame"] = 0
    m["export_assets"] = []
    m["symbol_class"] = []
    return m


def report(m):
    audit = build_frame_count_audit(m, depth_for(m))
    tail = build_frame_tail_evidence(m, audit)
    return build_zero_frame_sprite_references(m, tail)


class ZeroFrameSpriteReferencesTests(unittest.TestCase):
    def test_unreferenced_zero_show_sprite(self):
        r = report(zero_fixture())
        self.assertEqual(r["zero_show_frame_sprite_count"], 1)
        self.assertEqual(r["static_place_reference_count"], 0)
        self.assertEqual(r["sprites"][0]["internal_tag_counts_by_code"], {"12": 1})
        self.assertEqual(r["sprites"][0]["observed_show_frames"], 0)

    def test_static_place_and_init_provenance(self):
        m = zero_fixture()
        m["tags"].insert(3, {"timeline": "main", "tag_code": 26, "frame": 0,
                              "offset_uncompressed": 55, "character_id_reference": 7})
        m["tags"].insert(4, {"timeline": "main", "tag_code": 59, "frame": 0,
                              "offset_uncompressed": 57, "init_target_sprite_id": 7})
        r = report(m)
        self.assertEqual(r["static_place_reference_count"], 1)
        self.assertEqual(r["static_init_action_reference_count"], 1)
        self.assertEqual(r["sprites_with_static_place_reference"], 1)
        self.assertEqual([e["offset_uncompressed"] for e in
                          r["sprites"][0]["static_inbound_references"]], [55, 57])

    def test_export_and_class_counts_without_names(self):
        m = zero_fixture()
        m["export_assets"] = [{"character_id": 7, "name": "private_original_name"}]
        m["symbol_class"] = [{"character_id": 7, "name": "private_original_class"}]
        r = report(m)
        self.assertEqual(r["sprites_with_export_name"], 1)
        self.assertEqual(r["sprites_with_symbol_class_name"], 1)
        self.assertNotIn("private_original", str(r))

    def test_declared_zero_sprite_without_mismatch_is_included(self):
        m = zero_fixture()
        next(t for t in m["tags"] if t["tag_code"] == 39)["sprite_frame_count"] = 0
        r = report(m)
        self.assertEqual(r["zero_show_frame_sprite_count"], 1)
        self.assertEqual(r["zero_sprite_declared_frame_counts"], {"0": 1})
        self.assertEqual(r["zero_sprites_in_frame_tail_mismatches"], 0)
        self.assertEqual(r["zero_sprites_with_matching_declared_frames"], 1)

    def test_mixed_declared_zero_and_one_sprite_coverage(self):
        m = zero_fixture()
        main_end = next(i for i, t in enumerate(m["tags"])
                        if t["timeline"] == "main" and t["tag_code"] == 0)
        m["tags"][main_end:main_end] = [
            {"timeline": "main", "tag_code": 39, "frame": 2,
             "character_id": 8, "sprite_frame_count": 0, "offset_uncompressed": 75},
            {"timeline": "sprite:8", "tag_code": 0, "frame": 0,
             "offset_uncompressed": 76},
        ]
        depth = depth_for(m)
        depth["timelines"].append({
            "timeline": "sprite:8", "declared_frames": 0,
            "observed_show_frames": 0, "frame_count_mismatch": False, "frames": [],
        })
        depth["timeline_count"] += 1
        audit = build_frame_count_audit(m, depth)
        r = build_zero_frame_sprite_references(m, build_frame_tail_evidence(m, audit))
        self.assertEqual(r["zero_show_frame_sprite_count"], 2)
        self.assertEqual(r["zero_sprite_declared_frame_counts"], {"0": 1, "1": 1})
        self.assertEqual(r["zero_sprites_in_frame_tail_mismatches"], 1)
        self.assertEqual(r["zero_sprites_with_matching_declared_frames"], 1)

    def test_declared_zero_with_showframe_is_not_zero_showframe(self):
        m = zero_fixture()
        next(t for t in m["tags"] if t["tag_code"] == 39)["sprite_frame_count"] = 0
        sprite_end = next(i for i, t in enumerate(m["tags"])
                          if t["timeline"] == "sprite:7" and t["tag_code"] == 0)
        m["tags"].insert(sprite_end, {"timeline": "sprite:7", "tag_code": 1,
                                      "frame": 0, "offset_uncompressed": 45})
        m["tags"][sprite_end + 1]["frame"] = 1
        self.assertEqual(report(m)["zero_show_frame_sprite_count"], 0)

    def test_nonzero_mismatch_not_misclassified(self):
        m, _ = fixture()
        m["export_assets"], m["symbol_class"] = [], []
        self.assertEqual(report(m)["zero_show_frame_sprite_count"], 0)

    def test_unrelated_reference_ignored(self):
        m = zero_fixture()
        m["tags"].insert(3, {"timeline": "main", "tag_code": 4, "frame": 0,
                              "offset_uncompressed": 55, "character_id_reference": 99})
        self.assertEqual(report(m)["static_place_reference_count"], 0)

    def test_source_hash_mismatch_fails(self):
        m = zero_fixture()
        tail = build_frame_tail_evidence(m, build_frame_count_audit(m, depth_for(m)))
        tail["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_zero_frame_sprite_references(m, tail)

    def test_tampered_tail_row_fails(self):
        m = zero_fixture()
        tail = build_frame_tail_evidence(m, build_frame_count_audit(m, depth_for(m)))
        tail["mismatches"][0]["declared_frames"] = 99
        with self.assertRaisesRegex(ValueError, "row disagrees"):
            build_zero_frame_sprite_references(m, tail)

    def test_missing_tail_row_fails(self):
        m = zero_fixture()
        tail = build_frame_tail_evidence(m, build_frame_count_audit(m, depth_for(m)))
        tail["mismatches"].clear()
        tail["mismatch_count"] = 0
        with self.assertRaisesRegex(ValueError, "membership"):
            build_zero_frame_sprite_references(m, tail)

    def test_duplicate_sprite_declaration_fails(self):
        m = zero_fixture()
        m["tags"].insert(1, copy.deepcopy(m["tags"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate sprite"):
            report(m)

    def test_metadata_has_no_payload(self):
        r = report(zero_fixture())
        self.assertNotIn("script_body", str(r))
        self.assertNotIn("payload", str(r))


if __name__ == "__main__":
    unittest.main()
