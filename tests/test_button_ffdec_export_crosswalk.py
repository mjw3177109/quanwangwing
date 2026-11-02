import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_ffdec_export_crosswalk import build_button_ffdec_export_crosswalk


def fixture():
    h = "a" * 64
    buttons = {
        "source_sha256": h, "define_button2_count": 2,
        "embedded_action_record_count": 3, "buttons_with_actions": 2,
        "buttons": [
            {"character_id": 648, "embedded_action_record_count": 2,
             "embedded_action_records": [
                 {"condition_flags": 1, "offset_uncompressed": 100,
                  "action_bytes_including_terminator": 4},
                 {"condition_flags": 2, "offset_uncompressed": 110,
                  "action_bytes_including_terminator": 4}]},
            {"character_id": 693, "embedded_action_record_count": 1,
             "embedded_action_records": [
                 {"condition_flags": 8, "offset_uncompressed": 200,
                  "action_bytes_including_terminator": 40}]},
        ],
    }
    paths = [
        "scripts/DefineButton2_648/BUTTONCONDACTION on(rollOver).as",
        "scripts/DefineButton2_648/BUTTONCONDACTION on(rollOut).as",
        "scripts/DefineButton2_693/BUTTONCONDACTION on(release).as",
    ]
    files = [{"path": p, "size_bytes": 12, "sha256": "b" * 64} for p in paths]
    exports = {"source_sha256": h, "script_count": 3,
               "total_bytes": 36, "files": files}
    return buttons, exports


class FFDecButtonCrosswalkTests(unittest.TestCase):
    def test_verified_match_including_multiple_events(self):
        b, e = fixture()
        r = build_button_ffdec_export_crosswalk(b, e)
        self.assertEqual(r["source_action_record_count"], 3)
        self.assertEqual(r["matched_export_count"], 3)
        self.assertEqual(r["buttons_with_matched_exports"], 2)
        self.assertEqual(r["condition_flag_counts"], {"0x0001": 1, "0x0002": 1, "0x0008": 1})
        self.assertFalse(r["runtime_behavior_verified"])
        self.assertFalse(r["decompiled_semantics_verified"])

    def test_source_mismatch_fails_closed(self):
        b, e = fixture()
        e["source_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_button_ffdec_export_crosswalk(b, e)

    def test_missing_export_fails_closed(self):
        b, e = fixture()
        e["files"].pop()
        e["script_count"] -= 1
        e["total_bytes"] -= 12
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
            build_button_ffdec_export_crosswalk(b, e)

    def test_extra_export_fails_closed(self):
        b, e = fixture()
        e["files"].append({"path": "scripts/DefineButton2_999/BUTTONCONDACTION on(release).as",
                           "size_bytes": 10, "sha256": "b" * 64})
        e["script_count"] += 1
        e["total_bytes"] += 10
        with self.assertRaisesRegex(ValueError, "Extra or unmatched"):
            build_button_ffdec_export_crosswalk(b, e)

    def test_duplicate_export_path_fails_closed(self):
        b, e = fixture()
        e["files"].append(copy.deepcopy(e["files"][0]))
        e["script_count"] += 1
        e["total_bytes"] += 12
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_button_ffdec_export_crosswalk(b, e)

    def test_unknown_or_combined_condition_fails_closed(self):
        b, e = fixture()
        b["buttons"][0]["embedded_action_records"][0]["condition_flags"] = 3
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            build_button_ffdec_export_crosswalk(b, e)

    def test_bad_export_hash_fails_closed(self):
        b, e = fixture()
        e["files"][0]["sha256"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "unverified"):
            build_button_ffdec_export_crosswalk(b, e)

    def test_tampered_counts_fail_closed(self):
        b, e = fixture()
        b["embedded_action_record_count"] = 4
        with self.assertRaisesRegex(ValueError, "total mismatch"):
            build_button_ffdec_export_crosswalk(b, e)
        b, e = fixture()
        e["total_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "byte accounting"):
            build_button_ffdec_export_crosswalk(b, e)

    def test_metadata_only(self):
        b, e = fixture()
        result = build_button_ffdec_export_crosswalk(b, e)
        self.assertNotIn("script_source", str(result))
        self.assertNotIn("original_action_bytes", str(result))


if __name__ == "__main__":
    unittest.main()
