"""Regression tests use synthetic ActionRecords only; no original SWF bytes."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_action_tail_opcode_compatibility import (
    push_payload_well_formed, classify_long_action, classify_11_byte_tail,
    build_tail_compatibility, audit_11_byte_tail_control_flow,
    audit_11_byte_tail_reachability,
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

    def test_tail_gotoframe_not_treated_as_relative_jump(self):
        tail = bytes.fromhex("8102000100810200020000")
        kinds, targets, pre_kinds, pre_targets = audit_11_byte_tail_control_flow(b"\x3d\x00" + tail)
        self.assertEqual(kinds, {"goto_frame": 2})
        self.assertFalse(targets)
        self.assertFalse(pre_kinds)
        self.assertFalse(pre_targets)

    def test_tail_jump_if_boundary_classification(self):
        tail = bytes.fromhex("99020005009d0200f6ff00")
        kinds, targets, _, _ = audit_11_byte_tail_control_flow(b"\x3d\x00" + tail)
        self.assertEqual(kinds, {"jump": 1, "if": 1})
        self.assertEqual(targets, {"record_boundary": 2})

    def test_pre_end_jump_skipping_first_action_end(self):
        tail = bytes.fromhex("8102000100810200020000")
        body = bytes.fromhex("990200010000") + tail
        _, _, kinds, targets = audit_11_byte_tail_control_flow(body)
        self.assertEqual(kinds, {"jump": 1})
        self.assertEqual(targets, {"record_boundary": 1})

    def test_pre_end_if_into_record_interior(self):
        tail = bytes.fromhex("8102000100810200020000")
        body = bytes.fromhex("9d0200020000") + tail
        _, _, kinds, targets = audit_11_byte_tail_control_flow(body)
        self.assertEqual(kinds, {"if": 1})
        self.assertEqual(targets, {"record_interior": 1})

    def test_flow_report_accounting_and_privacy(self):
        tail = bytes.fromhex("99020005009d0200f6ff00")
        manifest, data = synthetic_manifest([(12, tail), (59, tail)])
        report = build_tail_compatibility(manifest, data)
        self.assertEqual(report["candidate_action_kind_histogram"]["jump"], 2)
        self.assertEqual(report["candidate_action_kind_histogram"]["if"], 2)
        self.assertEqual(report["candidate_branch_target_histogram"]["record_boundary"], 4)
        self.assertEqual(report["pre_end_branch_count"], 0)
        self.assertNotIn("990200", str(report))

    def test_static_graph_stops_at_first_action_end(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("3d00") + tail)
        self.assertEqual(result["tail_record_count"], 0)
        self.assertTrue(result["first_end_reachable"])
        self.assertFalse(result["tail_end_reachable"])

    def test_static_jump_skips_end_to_both_tail_records(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("990200010000") + tail)
        self.assertEqual(result["tail_record_count"], 2)
        self.assertFalse(result["first_end_reachable"])
        self.assertEqual(result["reachable_pre_end_to_tail_edges"], 1)

    def test_static_if_has_branch_and_fallthrough(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("9d0200010000") + tail)
        self.assertEqual(result["tail_record_count"], 2)
        self.assertTrue(result["first_end_reachable"])
        self.assertEqual(result["pre_end_to_tail_edges"], 1)

    def test_static_graph_rejects_interior_target(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("990200020000") + tail)
        self.assertEqual(result["tail_record_count"], 0)
        self.assertEqual(result["unresolved_branch_edges"], 1)
        self.assertEqual(result["unresolved_branch_target_histogram"]["tail_record_interior"], 1)
        self.assertEqual(result["reachable_unresolved_branch_target_histogram"]["tail_record_interior"], 1)

    def test_static_graph_classifies_pre_end_interior(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("990200fcff00") + tail)
        self.assertEqual(result["unresolved_branch_target_histogram"]["pre_end_record_interior"], 1)
        self.assertEqual(result["reachable_unresolved_branch_target_histogram"]["pre_end_record_interior"], 1)

    def test_static_graph_classifies_outside_before_and_after(self):
        tail = bytes.fromhex("8102000100810200020000")
        for prefix, expected in (
            ("990200f6ff00", "outside_before"),
            ("9902000c0000", "outside_after"),
        ):
            with self.subTest(expected=expected):
                result = audit_11_byte_tail_reachability(bytes.fromhex(prefix) + tail)
                self.assertEqual(result["unresolved_branch_target_histogram"][expected], 1)
                self.assertEqual(sum(result["unresolved_branch_target_histogram"].values()), 1)
                self.assertEqual(sum(result["reachable_unresolved_branch_target_histogram"].values()), 1)

    def test_static_graph_classifies_invalid_branch_operand(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("9d01000000") + tail)
        self.assertEqual(result["unresolved_branch_target_histogram"]["invalid_operand_length"], 1)
        self.assertEqual(result["reachable_unresolved_branch_target_histogram"]["invalid_operand_length"], 1)

    def test_static_graph_unreachable_unresolved_edge_not_counted_reachable(self):
        tail = bytes.fromhex("8102000100810200020000")
        # Return ends the entry path before the malformed branch.
        result = audit_11_byte_tail_reachability(bytes.fromhex("3e990200020000") + tail)
        self.assertEqual(result["unresolved_branch_target_histogram"]["tail_record_interior"], 1)
        self.assertEqual(sum(result["reachable_unresolved_branch_target_histogram"].values()), 0)

    def test_static_graph_tail_end_only_not_counted_as_record(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("9902000b0000") + tail)
        self.assertEqual(result["tail_record_count"], 0)
        self.assertTrue(result["tail_end_reachable"])

    def test_static_graph_return_is_terminal(self):
        tail = bytes.fromhex("8102000100810200020000")
        result = audit_11_byte_tail_reachability(bytes.fromhex("3e00") + tail)
        self.assertEqual(result["tail_record_count"], 0)
        self.assertFalse(result["first_end_reachable"])

    def test_static_report_counts_close_without_original_bytes(self):
        tail = bytes.fromhex("8102000100810200020000")
        manifest, data = synthetic_manifest([(12, tail), (59, tail)])
        report = build_tail_compatibility(manifest, data)
        self.assertEqual(report["candidate_tail_static_reachability_histogram"],
                         {"0": 2, "1": 0, "2": 0})
        self.assertEqual(report["candidate_first_end_static_reachable_count"], 2)
        self.assertEqual(report["candidate_reachable_pre_end_to_tail_boundary_edges"], 0)
        self.assertEqual(sum(report["candidate_unresolved_branch_target_histogram"].values()),
                         report["candidate_unresolved_branch_edges"])
        self.assertEqual(sum(report["candidate_reachable_unresolved_branch_target_histogram"].values()), 0)
        self.assertNotIn("810200", str(report))

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
