import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_action_evidence import build_button_action_evidence


def make_tag(payload, offset, long_header=False):
    if long_header or len(payload) >= 63:
        header = struct.pack("<HI", (34 << 6) | 63, len(payload))
    else:
        header = struct.pack("<H", (34 << 6) | len(payload))
    return header + payload, {
        "tag_code": 34, "character_id": 7, "timeline": "main", "frame": 2,
        "offset_uncompressed": offset, "body_offset_uncompressed": offset + len(header),
        "length": len(payload),
    }


def fixture(payload, long_header=False):
    prefix = b"FWS\x09" + b"\0" * 4
    raw, tag = make_tag(payload, len(prefix), long_header)
    return prefix + raw, {"source": {"sha256": "a" * 64},
                          "tags": [tag], "tag_counts_by_code": {"34": 1}}


def button(offset, tail):
    return struct.pack("<HBH", 7, 0, offset) + b"\0" + tail


class ButtonActionEvidenceTests(unittest.TestCase):
    def test_no_actions(self):
        data, manifest = fixture(button(0, b""))
        report = build_button_action_evidence(manifest, data)
        self.assertEqual(report["buttons_without_actions"], 1)
        self.assertEqual(report["embedded_action_record_count"], 0)

    def test_last_record_and_raw_condition_flags(self):
        data, manifest = fixture(button(3, struct.pack("<HH", 0, 0x0201) + b"\0"))
        report = build_button_action_evidence(manifest, data)
        self.assertEqual(report["embedded_action_record_count"], 1)
        self.assertEqual(report["embedded_action_bytes"], 1)
        self.assertEqual(report["buttons"][0]["embedded_action_records"][0]["condition_flags"], 0x0201)
        self.assertNotIn("script_body", str(report))

    def test_two_cond_actions_and_long_tag_header(self):
        first = struct.pack("<HH", 5, 1) + b"\0"
        second = struct.pack("<HH", 0, 2) + b"\0" * 64
        data, manifest = fixture(button(3, first + second), long_header=True)
        report = build_button_action_evidence(manifest, data)
        self.assertEqual(report["embedded_action_record_count"], 2)
        self.assertEqual(report["embedded_action_bytes"], 65)
        self.assertEqual(report["buttons_without_zero_sized_final_record"], 0)

    def test_bad_offset_rejected(self):
        data, manifest = fixture(button(500, b"\0"))
        with self.assertRaisesRegex(ValueError, "ActionOffset"):
            build_button_action_evidence(manifest, data)

    def test_invalid_cond_action_size_rejected(self):
        data, manifest = fixture(button(3, struct.pack("<HH", 4, 0) + b"\0"))
        with self.assertRaisesRegex(ValueError, "ButtonCondAction size"):
            build_button_action_evidence(manifest, data)

    def test_tampered_manifest_header_rejected(self):
        data, manifest = fixture(button(0, b""))
        manifest["tags"][0]["body_offset_uncompressed"] += 1
        with self.assertRaisesRegex(ValueError, "manifest/header"):
            build_button_action_evidence(manifest, data)

    def test_character_id_mismatch_rejected(self):
        data, manifest = fixture(button(0, b""))
        manifest["tags"][0]["character_id"] = 9
        with self.assertRaisesRegex(ValueError, "character ID"):
            build_button_action_evidence(manifest, data)

    def test_noncanonical_action_end_is_reported_not_falsified(self):
        data, manifest = fixture(button(3, struct.pack("<HH", 0, 1) + b"\x81"))
        report = build_button_action_evidence(manifest, data)
        self.assertEqual(report["records_without_terminal_action_end"], 1)


if __name__ == "__main__":
    unittest.main()
