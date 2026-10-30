import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_role_reference_evidence import build_role_reference_evidence


def fixtures():
    sha = "f" * 64
    crosswalk = {"source_sha256": sha, "role_variant_count": 2, "roles": [
        {"character_candidate": "Kyo", "variant": "base", "export_assets_character_id": 100,
         "verified_as2_script_path": "Kyo_role.as", "verified_as2_script_sha256": "a" * 64,
         "sprite_timeline": {"sprite_character_id": 100}},
        {"character_candidate": "Kyo", "variant": "type2", "export_assets_character_id": 101,
         "verified_as2_script_path": "Type2_Kyo_role.as", "verified_as2_script_sha256": "b" * 64,
         "sprite_timeline": None},
    ]}
    timeline = {"source_sha256": sha, "timelines": [
        {"timeline": "main", "display_events": [
            {"kind": "place", "tag_code": 26, "frame": 1, "offset_uncompressed": 200,
             "depth": 4, "move": False, "character_id": 100},
            {"kind": "place", "tag_code": 26, "frame": 2, "offset_uncompressed": 210,
             "depth": 4, "move": True},
            {"kind": "remove", "tag_code": 28, "frame": 3, "offset_uncompressed": 220,
             "depth": 4, "character_id": 100},
        ], "script_events": [
            {"tag_code": 59, "frame": 0, "offset_uncompressed": 120, "init_target_sprite_id": 100},
            {"tag_code": 12, "frame": 1, "offset_uncompressed": 300},
        ]},
        {"timeline": "sprite:777", "display_events": [
            {"kind": "place", "tag_code": 70, "frame": 5, "offset_uncompressed": 400,
             "depth": 9, "character_id": 101},
        ], "script_events": []},
    ]}
    return crosswalk, timeline


class RoleReferenceEvidenceTests(unittest.TestCase):
    def test_direct_reference_counts_and_offsets(self):
        result = build_role_reference_evidence(*fixtures())
        self.assertEqual(result["role_variant_count"], 2)
        self.assertEqual(result["direct_placement_count"], 2)
        self.assertEqual(result["do_init_action_target_count"], 1)
        self.assertEqual(result["roles"][0]["direct_placements"][0]["offset_uncompressed"], 200)
        self.assertEqual(result["roles"][0]["do_init_action_targets"][0]["offset_uncompressed"], 120)
        self.assertEqual(result["roles"][1]["direct_placements"][0]["parent_timeline"], "sprite:777")

    def test_unidentified_place_and_generic_script_do_not_count(self):
        a, t = fixtures()
        t["timelines"][0]["display_events"][0].pop("character_id")
        t["timelines"][0]["script_events"][0]["tag_code"] = 12
        result = build_role_reference_evidence(a, t)
        self.assertEqual(result["direct_placement_count"], 1)
        self.assertEqual(result["do_init_action_target_count"], 0)

    def test_source_hash_must_match(self):
        a, t = fixtures()
        t["source_sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            build_role_reference_evidence(a, t)

    def test_duplicate_role_id_rejected(self):
        a, t = fixtures()
        a["roles"][1]["export_assets_character_id"] = 100
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_role_reference_evidence(a, t)

    def test_sprite_id_mismatch_rejected(self):
        a, t = fixtures()
        a["roles"][0]["sprite_timeline"]["sprite_character_id"] = 999
        with self.assertRaisesRegex(ValueError, "Sprite character ID mismatch"):
            build_role_reference_evidence(a, t)

    def test_invalid_offset_rejected(self):
        a, t = fixtures()
        t["timelines"][0]["display_events"][0]["offset_uncompressed"] = -1
        with self.assertRaisesRegex(ValueError, "tag offset"):
            build_role_reference_evidence(a, t)

    def test_duplicate_timeline_rejected(self):
        a, t = fixtures()
        t["timelines"].append(copy.deepcopy(t["timelines"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate or invalid parent timeline"):
            build_role_reference_evidence(a, t)

    def test_no_script_bodies_or_gameplay_guesses(self):
        result = build_role_reference_evidence(*fixtures())
        self.assertNotIn("Key.isDown(", str(result))
        self.assertNotIn("function to_punch", str(result))
        self.assertNotIn("hitbox", str(result["roles"]))


if __name__ == "__main__":
    unittest.main()
