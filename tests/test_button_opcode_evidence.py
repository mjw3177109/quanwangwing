import copy
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_opcode_evidence import build_button_opcode_evidence, walk_action_records


def fixture(payload=b"\x04\x00", flags=8):
    body = struct.pack("<HBH", 7, 0, 3) + b"\x00" + struct.pack("<HH", 0, flags) + payload
    data = struct.pack("<H", (34 << 6) | len(body)) + body
    sha = "a" * 64
    manifest = {"source": {"sha256": sha}, "tag_counts_by_code": {"34": 1}, "tags": [
        {"tag_code": 34, "character_id": 7, "offset_uncompressed": 0,
         "body_offset_uncompressed": 2, "length": len(body), "timeline": "main", "frame": 0}]}
    buttons = {"source_sha256": sha, "embedded_action_record_count": 1,
               "embedded_action_bytes": len(payload), "buttons": [
                   {"character_id": 7, "tag_offset_uncompressed": 0, "timeline": "main", "frame_zero_based": 0,
                    "embedded_action_record_count": 1, "embedded_action_records": [
                        {"offset_uncompressed": 8, "condition_flags": flags,
                         "action_bytes_including_terminator": len(payload),
                         "is_last_by_zero_size": True, "ends_with_action_end": payload[-1] == 0}]}]}
    return manifest, buttons, data


class ButtonOpcodeEvidenceTests(unittest.TestCase):
    def test_short_opcode_then_end(self):
        r = build_button_opcode_evidence(*fixture())
        self.assertEqual(r["opcode_histogram"], {"0x04": 1})
        self.assertEqual(r["parse_status_counts"]["terminated_at_end"], 1)
        self.assertEqual(r["embedded_action_bytes"], 2)

    def test_long_opcode_with_payload(self):
        r = build_button_opcode_evidence(*fixture(b"\x96\x02\x00\x01\x02\x00"))
        self.assertEqual(r["opcode_histogram"], {"0x96": 1})
        self.assertEqual(r["parsed_opcode_count"], 1)

    def test_early_end_is_not_assumed_executable(self):
        r = build_button_opcode_evidence(*fixture(b"\x04\x00\x77"))
        self.assertEqual(r["parse_status_counts"]["early_action_end_with_trailing_bytes"], 1)
        self.assertEqual(r["unparsed_tail_bytes"], 1)
        self.assertNotIn("0x77", r["opcode_histogram"])

    def test_truncated_extended_header(self):
        r = build_button_opcode_evidence(*fixture(b"\x96\x00"))
        self.assertEqual(r["parse_status_counts"]["truncated_extended_header"], 1)

    def test_extended_payload_out_of_bounds(self):
        r = build_button_opcode_evidence(*fixture(b"\x96\x05\x00\x00"))
        self.assertEqual(r["parse_status_counts"]["extended_payload_out_of_bounds"], 1)

    def test_missing_action_end(self):
        r = build_button_opcode_evidence(*fixture(b"\x04\x05"))
        self.assertEqual(r["parse_status_counts"]["missing_action_end"], 1)

    def test_tampered_condition_rejected(self):
        m, b, data = fixture()
        b["buttons"][0]["embedded_action_records"][0]["condition_flags"] = 9
        with self.assertRaisesRegex(ValueError, "header mismatch"):
            build_button_opcode_evidence(m, b, data)

    def test_source_mismatch_rejected(self):
        m, b, data = fixture()
        b["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "source mismatch"):
            build_button_opcode_evidence(m, b, data)

    def test_duplicate_button_rejected(self):
        m, b, data = fixture()
        b["buttons"].append(copy.deepcopy(b["buttons"][0]))
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            build_button_opcode_evidence(m, b, data)

    def test_opcode_counts_exclude_end(self):
        counts, n, status, tail = walk_action_records(b"\x04\x05\x00")
        self.assertEqual((n, status, tail), (2, "terminated_at_end", 0))
        self.assertEqual(counts, {"0x04": 1, "0x05": 1})
