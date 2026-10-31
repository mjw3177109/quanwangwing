"""Regression tests use synthetic ActionRecords only; no original SWF bytes."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_action_tail_opcode_compatibility import (
    push_payload_well_formed, classify_long_action, classify_11_byte_tail,
    build_tail_compatibility,
)


def synthetic_manifest(tails):
    data = bytearray(b"FWS\x09" + bytes(4))
    tags = []
    for code, tail in tails:
        body = (b"\x07\x00" if code == 59 else b"") + b"\x3d\x00" + tail
        header = struct.pack("<H", (code << 6) | len(body))
        offset = len(data)
        data.extend(header + body)
        tag = {
            "tag_code": code, "timeline": "main", "frame": 0,
            "offset_uncompressed": offset,
            "body_offset_uncompressed": offset + len(header), "length": len(body)
        }
        if code == 59:
            tag["init_target_sprite_id"] = 7
        tags.append(tag)
    scripts = [{k: v for k, v in t.items() if k != "body_offset_uncompressed"} for t in tags]
    return {"source": {"sha256": "f" * 64}, "tags": tags, "scripts": scripts}, bytes(data)


class TailCompatibilityTests(unittest.TestCase):
    def test_push_framing_accepts_register_and_null_undefined(self):
        self.assertTrue(push_payload_well_formed(bytes.fromhex("0401")))
        self.assertTrue(push_payload_well_formed(bytes.fromhex("0203")))
        self.assertTrue(push_payload_well_formed(bytes.fromhex("0000")))

    def test_push_framing_rejects_truncated_and_unknown_types(self):
        for value in (bytes.fromhex("0001"), bytes.fromhex("0100"),
                      bytes.fromhex("0900"), bytes.fromhex("ff00")):
            with self.subTest(value=value):
                self.assertFalse(push_payload_well_formed(value))

    def test_fixed_length_and_unknown_opcode_classes(self):
        self.assertEqual(classify_long_action(0x99, b"\x01\x00"), "fixed_length_match")
        self.assertEqual(classify_long_action(0x99, b"\x01"), "fixed_length_mismatch")
        self.assertEqual(classify_long_action(0x9B, b"\x01\x00"), "known_variable_payload_unchecked")
        self.assertEqual(classify_long_action(0xFE, b"\x01\x00"), "unlisted_long_opcode")
        with self.assertRaises(ValueError):
            classify_long_action(0x3D, b"")

    def test_exact_two_long_records_and_terminator(self):
        tail = bytes.fromhex("9602000401990200010000")
        self.assertEqual(classify_11_byte_tail(tail),
                         ("push_payload_well_formed", "fixed_length_match"))
        self.assertIsNone(classify_11_byte_tail(tail[:-1] + b"\x01"))
        self.assertIsNone(classify_11_byte_tail(b"\x3d" + tail[1:]))
        with self.assertRaises(ValueError):
            classify_11_byte_tail(tail[:-1])

    def test_report_counts_two_records_and_protects_bytes(self):
        tail = bytes.fromhex("9602000401990200010000")
        manifest, data = synthetic_manifest([(12, tail), (59, tail)])
        report = build_tail_compatibility(manifest, data)
        self.assertEqual(report["legacy_container_count"], 2)
        self.assertEqual(report["trailing_length_11_count"], 2)
        self.assertEqual(report["l2_l2_end_candidate_count"], 2)
        self.assertEqual(report["candidate_record_count"], 4)
        self.assertEqual(report["candidate_by_tag_code"], {"12": 1, "59": 1})
        self.assertEqual(report["candidate_record_class_histogram"]["push_payload_well_formed"], 2)
        self.assertEqual(report["candidate_record_class_histogram"]["fixed_length_match"], 2)
        self.assertEqual(sum(report["candidate_pair_class_histogram"].values()), 2)
        self.assertNotIn("960200", str(report))
        self.assertNotIn("script_body", str(report))

    def test_nonmatching_shape_is_accounted_not_accepted(self):
        valid = bytes.fromhex("9602000401990200010000")
        invalid = b"\x3d" * 10 + b"\x00"
        manifest, data = synthetic_manifest([(12, valid), (12, invalid)])
        report = build_tail_compatibility(manifest, data)
        self.assertEqual(report["trailing_length_11_count"], 2)
        self.assertEqual(report["l2_l2_end_candidate_count"], 1)
        self.assertEqual(report["other_shape_count"], 1)

    def test_wrong_init_target_fails_closed(self):
        tail = bytes.fromhex("9602000401990200010000")
        manifest, data = synthetic_manifest([(59, tail)])
        manifest["tags"][0]["init_target_sprite_id"] = 9
        with self.assertRaisesRegex(ValueError, "target mismatch"):
            build_tail_compatibility(manifest, data)

    def test_script_provenance_mismatch_fails_closed(self):
        tail = bytes.fromhex("9602000401990200010000")
        manifest, data = synthetic_manifest([(12, tail)])
        manifest["scripts"][0]["frame"] = 9
        with self.assertRaisesRegex(ValueError, "provenance"):
            build_tail_compatibility(manifest, data)


if __name__ == "__main__":
    unittest.main()
