import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_zero_frame_as2_class_links import build_zero_frame_as2_class_links

SHA = "a" * 64


def fixture():
    manifest = {"source": {"sha256": SHA}, "tags": [
        {"tag_code": 39, "timeline": "main", "character_id": 7,
         "offset_uncompressed": 12, "sprite_frame_count": 1},
        {"tag_code": 0, "timeline": "sprite:7", "offset_uncompressed": 18},
        {"tag_code": 59, "timeline": "main", "init_target_sprite_id": 7},
    ], "export_assets": [{"character_id": 7, "name": "__Packages.Kyo_role"}]}
    asset = {"source_sha256": SHA, "assets": [
        {"character_id": 7, "category": "sprite", "tag_code": 39, "offset_uncompressed": 12}
    ], "exported_symbol_count": 1, "export_assets": copy.deepcopy(manifest["export_assets"])}
    export = {"source_sha256": SHA, "script_count": 1, "unexpected_empty_count": 0,
              "files": [{"path": "scripts/__Packages/Kyo_role.as", "size_bytes": 123,
                         "sha256": "b" * 64}]}
    return manifest, asset, export


class ZeroFrameAS2ClassLinksTests(unittest.TestCase):
    def test_verified_path_match(self):
        result = build_zero_frame_as2_class_links(*fixture())
        self.assertEqual(result["zero_show_frame_sprite_count"], 1)
        self.assertEqual(result["zero_sprites_with_init_target"], 1)
        self.assertEqual(result["zero_sprites_with_class_path_match"], 1)
        self.assertEqual(result["class_path_classifications"], {"verified_path_match": 1})
        self.assertEqual(result["entries"][0]["verified_script_size_bytes"], 123)

    def test_missing_path_is_not_a_match(self):
        m, a, e = fixture()
        e["files"][0]["path"] = "scripts/other.as"
        r = build_zero_frame_as2_class_links(m, a, e)
        self.assertEqual(r["class_path_classifications"], {"unmatched_class_path": 1})

    def test_non_class_name_is_not_a_match(self):
        m, a, e = fixture()
        m["export_assets"][0]["name"] = "UI/Logo"
        a["export_assets"] = copy.deepcopy(m["export_assets"])
        self.assertEqual(build_zero_frame_as2_class_links(m, a, e)["class_path_classifications"],
                         {"not_class_path": 1})

    def test_sprite_with_showframe_excluded(self):
        m, a, e = fixture()
        m["tags"].append({"tag_code": 1, "timeline": "sprite:7"})
        self.assertEqual(build_zero_frame_as2_class_links(m, a, e)["zero_show_frame_sprite_count"], 0)

    def test_source_mismatch_rejected(self):
        m, a, e = fixture()
        e["source_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_zero_frame_as2_class_links(m, a, e)

    def test_export_name_tamper_rejected(self):
        m, a, e = fixture()
        a["export_assets"][0]["name"] = "Other"
        with self.assertRaisesRegex(ValueError, "disagree"):
            build_zero_frame_as2_class_links(m, a, e)

    def test_asset_definition_tamper_rejected(self):
        m, a, e = fixture()
        a["assets"][0]["offset_uncompressed"] = 99
        with self.assertRaisesRegex(ValueError, "definition"):
            build_zero_frame_as2_class_links(m, a, e)

    def test_duplicate_script_path_rejected(self):
        m, a, e = fixture()
        e["files"].append(copy.deepcopy(e["files"][0]))
        e["script_count"] = 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_zero_frame_as2_class_links(m, a, e)

    def test_duplicate_sprite_id_rejected(self):
        m, a, e = fixture()
        m["tags"].append(copy.deepcopy(m["tags"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate sprite"):
            build_zero_frame_as2_class_links(m, a, e)

    def test_unexplained_empty_export_rejected(self):
        m, a, e = fixture()
        e["unexpected_empty_count"] = 1
        with self.assertRaisesRegex(ValueError, "empty"):
            build_zero_frame_as2_class_links(m, a, e)

    def test_no_names_or_paths_leak(self):
        result = build_zero_frame_as2_class_links(*fixture())
        text = str(result)
        self.assertNotIn("Kyo_role", text)
        self.assertNotIn("scripts/__Packages", text)


if __name__ == "__main__":
    unittest.main()
