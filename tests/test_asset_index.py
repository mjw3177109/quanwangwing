import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_asset_index import build_index
from swf_inventory import inventory


class AssetIndexTests(unittest.TestCase):
    def test_asset_categories_and_role_class_evidence(self):
        manifest = {
            "source": {"filename": "test.swf", "sha256": "abc"},
            "stage": {"width_px": 660, "height_px": 485, "frame_rate": 32},
            "export_assets": [
                {"character_id": 12, "name": "__Packages.Kyo_role"},
                {"character_id": 13, "name": "__Packages.Type2_Kyo_role"},
                {"character_id": 20, "name": "menuButton"},
            ],
            "characters": [
                {"character_id": 12, "tag_code": 39, "tag_name": "DefineSprite",
                 "timeline": "main", "offset_uncompressed": 20},
                {"character_id": 20, "tag_code": 34, "tag_name": "DefineButton2",
                 "timeline": "main", "offset_uncompressed": 100},
            ],
            "scripts": [{"tag_code": 12, "timeline": "main", "frame": 0}],
        }
        index = build_index(manifest)
        self.assertEqual(index["asset_definition_count"], 2)
        self.assertEqual(index["asset_categories"], {"button": 1, "sprite": 1})
        self.assertEqual(index["assets"][0]["export_names"], ["__Packages.Kyo_role"])
        self.assertEqual(len(index["character_class_candidates"]), 1)
        self.assertEqual(index["character_class_candidates"][0]["base_role_character_id"], 12)
        self.assertEqual(index["character_class_candidates"][0]["type2_role_character_id"], 13)
        self.assertEqual(len(index["script_tags"]), 1)

    @unittest.skipUnless((ROOT / "拳皇wing1.4.swf").is_file(), "original SWF not present")
    def test_original_swf_baseline_is_unchanged(self):
        manifest = inventory(ROOT / "拳皇wing1.4.swf")
        self.assertEqual(
            manifest["source"]["sha256"],
            "cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb",
        )
        self.assertEqual(manifest["stage"]["width_px"], 660)
        self.assertEqual(manifest["stage"]["height_px"], 485)
        self.assertEqual(manifest["stage"]["frame_rate"], 32)
        self.assertEqual(manifest["stage"]["frame_count"], 39)
        self.assertEqual(manifest["tag_count_including_sprites"], 98210)
        index = build_index(manifest)
        self.assertEqual(index["asset_definition_count"], 14562)
        self.assertEqual(index["exported_symbol_count"], 715)
        self.assertEqual(
            {x["class_name"] for x in index["character_class_candidates"]},
            {"Kyo", "Mai", "Iori", "K", "Kula", "Ryo", "Moriya", "Orochi"},
        )


if __name__ == "__main__":
    unittest.main()
