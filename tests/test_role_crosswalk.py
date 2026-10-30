import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_role_crosswalk import build_crosswalk


def fixtures():
    sha = "f" * 64
    asset = {
        "source_sha256": sha,
        "character_class_candidates": [
            {"class_name": "Kyo", "base_role_character_id": 100,
             "type2_role_character_id": 101}
        ],
    }
    timeline = {
        "source_sha256": sha,
        "timelines": [
            {"timeline": "main", "sprite_character_id": None},
            {"timeline": "sprite:100", "sprite_character_id": 100,
             "declared_frames": 3, "observed_show_frames": 3,
             "frame_labels": [], "script_events": [{"frame": 0}],
             "display_events": [{"frame": 1}], "sound_events": []},
        ],
    }
    semantic = {
        "source_sha256": sha,
        "verified_script_count": 7054,
        "role_script_candidates": [
            {"character_candidate": "Kyo", "variant": "base",
             "expected_script_path": "scripts/__Packages/Kyo_role.as", "export_present": True},
            {"character_candidate": "Kyo", "variant": "type2",
             "expected_script_path": "scripts/__Packages/Type2_Kyo_role.as", "export_present": True},
        ],
        "candidate_scripts": [
            {"path": "scripts/__Packages/Kyo_role.as", "role_candidate": True,
             "sha256": "a" * 64, "size_bytes": 100,
             "function_scopes": [{
                 "name": "to_punch", "kind": "function_assignment",
                 "start_line": 2, "end_line": 7,
                 "marker_counts": {"keyboard": 2}, "marker_lines": {"keyboard": [4, 5]},
             }]},
            {"path": "scripts/__Packages/Type2_Kyo_role.as", "role_candidate": True,
             "sha256": "b" * 64, "size_bytes": 200,
             "function_scopes": []},
        ],
    }
    return asset, timeline, semantic


class RoleCrosswalkTests(unittest.TestCase):
    def test_crosswalk_preserves_provenance_and_missing_timeline(self):
        result = build_crosswalk(*fixtures())
        self.assertEqual(result["role_variant_count"], 2)
        self.assertEqual(result["linked_sprite_timeline_count"], 1)
        self.assertEqual(result["unlinked_sprite_timeline_count"], 1)
        self.assertEqual(result["function_scope_candidate_count"], 1)
        self.assertEqual(result["function_marker_counts"], {"keyboard": 2})
        base = next(x for x in result["roles"] if x["variant"] == "base")
        self.assertEqual(base["sprite_timeline"]["declared_frames"], 3)
        self.assertEqual(base["sprite_timeline"]["script_event_count"], 1)
        self.assertEqual(base["verified_as2_script_sha256"], "a" * 64)
        other = next(x for x in result["roles"] if x["variant"] == "type2")
        self.assertIsNone(other["sprite_timeline"])

    def test_rejects_mismatched_swf_source(self):
        a, t, s = fixtures()
        t["source_sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            build_crosswalk(a, t, s)

    def test_rejects_missing_verified_role_script(self):
        a, t, s = fixtures()
        s["candidate_scripts"].pop()
        with self.assertRaisesRegex(ValueError, "Missing hashed AS2"):
            build_crosswalk(a, t, s)

    def test_rejects_unverified_role_path(self):
        a, t, s = fixtures()
        s["role_script_candidates"][0]["export_present"] = False
        with self.assertRaisesRegex(ValueError, "Missing verified AS2"):
            build_crosswalk(a, t, s)

    def test_rejects_marker_outside_scope(self):
        a, t, s = fixtures()
        s["candidate_scripts"][0]["function_scopes"][0]["marker_lines"]["keyboard"] = [9]
        with self.assertRaisesRegex(ValueError, "outside function scope"):
            build_crosswalk(a, t, s)

    def test_rejects_duplicate_sprite_timeline(self):
        a, t, s = fixtures()
        t["timelines"].append(copy.deepcopy(t["timelines"][1]))
        with self.assertRaisesRegex(ValueError, "Duplicate sprite timeline"):
            build_crosswalk(a, t, s)

    def test_output_contains_no_source_bodies_or_argument_literals(self):
        a, t, s = fixtures()
        result = build_crosswalk(a, t, s)
        self.assertNotIn("Key.isDown(", str(result))
        self.assertNotIn("function to_punch", str(result))
        self.assertNotIn("hitbox", str(result["roles"]))


if __name__ == "__main__":
    unittest.main()
