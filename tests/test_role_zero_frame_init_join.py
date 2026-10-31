import copy
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_role_zero_frame_init_join import build_role_zero_frame_init_join

SHA = "a" * 64
PATH = "scripts/__Packages/Kyo_role.as"
PATH_HASH = hashlib.sha256(PATH.encode("utf-8")).hexdigest()

def fixture():
    roles = {"source_sha256": SHA, "role_variant_count": 1, "roles": [{
        "export_assets_character_id": 7, "character_candidate": "Kyo", "variant": "base",
        "verified_as2_script_path": PATH, "verified_as2_script_sha256": "b" * 64,
        "do_init_action_target_count": 1, "direct_placement_count": 0,
        "do_init_action_targets": [{"parent_timeline": "main", "frame": 0,
                                    "offset_uncompressed": 20}]}]}
    zero = {"source_sha256": SHA, "zero_sprite_export_count": 1, "entries": [{
        "sprite_character_id": 7, "classification": "verified_path_match",
        "candidate_script_path_sha256": PATH_HASH, "verified_script_sha256": "b" * 64,
        "do_init_action_target_count": 1,
        "init_script_tags": [{"timeline": "main", "frame_zero_based": 0,
                              "offset_uncompressed": 20, "tag_length_bytes": 24}]}]}
    return roles, zero

class RoleZeroFrameJoinTests(unittest.TestCase):
    def test_join_and_no_plaintext_leak(self):
        result = build_role_zero_frame_init_join(*fixture())
        self.assertEqual(result["role_variants_with_zero_show_frame"], 1)
        self.assertEqual(result["role_variants_with_same_verified_class_path"], 1)
        self.assertEqual(result["role_init_reference_count"], 1)
        self.assertNotIn("Kyo", str(result))
        self.assertNotIn(PATH, str(result))
    def test_nonzero_sprite_not_claimed(self):
        r, z = fixture()
        z["entries"], z["zero_sprite_export_count"] = [], 0
        self.assertFalse(build_role_zero_frame_init_join(r, z)["entries"][0]["zero_show_frame_sprite"])
    def test_mismatched_class_hash_not_equated(self):
        r, z = fixture()
        z["entries"][0]["verified_script_sha256"] = "c" * 64
        self.assertFalse(build_role_zero_frame_init_join(r, z)["entries"][0]["same_verified_class_path"])
    def test_init_offset_mismatch_rejected(self):
        r, z = fixture()
        z["entries"][0]["init_script_tags"][0]["offset_uncompressed"] = 21
        with self.assertRaisesRegex(ValueError, "disagree"):
            build_role_zero_frame_init_join(r, z)
    def test_duplicate_role_rejected(self):
        r, z = fixture()
        r["roles"].append(copy.deepcopy(r["roles"][0]))
        r["role_variant_count"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate role"):
            build_role_zero_frame_init_join(r, z)
    def test_source_mismatch_rejected(self):
        r, z = fixture()
        z["source_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_role_zero_frame_init_join(r, z)
    def test_duplicate_init_rejected(self):
        r, z = fixture()
        r["roles"][0]["do_init_action_targets"].append(copy.deepcopy(r["roles"][0]["do_init_action_targets"][0]))
        r["roles"][0]["do_init_action_target_count"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate role init"):
            build_role_zero_frame_init_join(r, z)

if __name__ == "__main__":
    unittest.main()
