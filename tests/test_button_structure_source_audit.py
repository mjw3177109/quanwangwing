import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_button_structure_audit import (
    STATUSES, build_button_structure_audit, summarize_partitions,
)


def fixture(payload, cid=693, offset=8):
    data = b"x" * offset + b"\x00" * 4 + payload
    record = {"offset_uncompressed": offset,
              "action_bytes_including_terminator": len(payload)}
    buttons = {"embedded_action_record_count": 1,
               "buttons": [{"character_id": cid,
                            "embedded_action_records": [record]}]}
    opcodes = {"source_sha256": "a" * 64,
               "records": [{"button_character_id": cid,
                            "action_offset_uncompressed": offset}]}
    return buttons, opcodes, data


class ButtonStructureSourceAuditTests(unittest.TestCase):
    def test_function_body_end_is_not_top_level_end(self):
        payload = b"\x9b\x06\x00f\x00\x00\x00\x03\x00\x04\x00\x04\x00"
        report = summarize_partitions(*fixture(payload))
        self.assertEqual(report["partition_status_counts"]["partitioned"], 1)
        self.assertEqual(report["flat_first_end_disagreement_count"], 1)
        self.assertEqual(report["declared_function_count_in_partitioned_records"], 1)
        self.assertEqual(report["declared_function_body_bytes_in_partitioned_records"], 3)
        self.assertEqual(report["records"][0]["first_top_level_end_offset"], 12)
        self.assertEqual(report["records"][0]["flat_first_end_offset"], 10)
        self.assertFalse(report["runtime_reachability_verified"])

    def test_simple_stream_has_matching_end(self):
        report = summarize_partitions(*fixture(b"\x04\x00"))
        self.assertEqual(report["flat_first_end_disagreement_count"], 0)
        self.assertEqual(report["records"][0]["first_top_level_end_offset"], 1)

    def test_post_end_record_is_syntactic_only(self):
        report = summarize_partitions(*fixture(b"\x04\x00\x04\x00"))
        self.assertEqual(report["top_level_post_end_record_count_in_partitioned_records"], 2)
        self.assertFalse(report["records"][0]["runtime_reachability_verified"])

    def test_missing_top_level_end_reported(self):
        report = summarize_partitions(*fixture(b"\x04"))
        self.assertEqual(report["partitioned_without_top_level_end_count"], 1)

    def test_unsupported_nested_scope_fails_closed(self):
        report = summarize_partitions(*fixture(b"\x94\x02\x00\x00\x00\x00"))
        self.assertEqual(report["partition_status_counts"]["unsupported_nested_scope"], 1)
        self.assertFalse(report["records"][0]["top_level_partition_verified"])

    def test_malformed_scope_fails_closed(self):
        report = summarize_partitions(*fixture(b"\x96\x08\x00\x00"))
        self.assertEqual(report["partition_status_counts"]["malformed_or_unsupported"], 1)
        self.assertEqual(set(report["partition_status_counts"]), set(STATUSES))

    def test_partitioned_if_target_after_first_end(self):
        report = summarize_partitions(*fixture(b"\\x9d\\x02\\x00\\x01\\x00\\x00\\x04\\x00"))
        row = report["records"][0]
        self.assertTrue(row["partitioned_pre_end_branch_audit_complete"])
        self.assertEqual(row["partitioned_pre_end_branch_count"], 1)
        self.assertEqual(row["partitioned_pre_end_branch_target_class_counts"]["post_end_record"], 1)
        self.assertEqual(report["partitioned_pre_end_branch_count"], 1)
        self.assertFalse(row["runtime_reachability_verified"])

    def test_function_body_target_is_not_top_level_boundary(self):
        function = b"\\x9b\\x06\\x00f\\x00\\x00\\x00\\x02\\x00"
        payload = b"\\x99\\x02\\x00\\x09\\x00" + function + b"\\x04\\x04\\x00"
        report = summarize_partitions(*fixture(payload))
        row = report["records"][0]
        self.assertEqual(row["declared_function_count"], 1)
        self.assertEqual(row["partitioned_pre_end_branch_target_class_counts"]["function_body"], 1)
        self.assertEqual(row["partitioned_pre_end_branch_target_class_counts"]["pre_end_record"], 0)
        self.assertEqual(report["partitioned_pre_end_branch_target_class_totals"]["function_body"], 1)

    def test_partitioned_invalid_branch_operand_length(self):
        report = summarize_partitions(*fixture(b"\\x99\\x01\\x00\\x00\\x00"))
        row = report["records"][0]
        self.assertEqual(row["partitioned_pre_end_branch_target_class_counts"]["invalid_operand_length"], 1)
        self.assertEqual(sum(row["partitioned_pre_end_branch_target_class_counts"].values()), 1)

    def test_partitioned_record_interior_target(self):
        report = summarize_partitions(*fixture(b"\\x99\\x02\\x00\\xfc\\xff\\x00"))
        self.assertEqual(report["partitioned_pre_end_branch_target_class_totals"]["record_interior"], 1)

    def test_no_end_does_not_claim_complete_branch_audit(self):
        report = summarize_partitions(*fixture(b"\\x99\\x02\\x00\\x00\\x00"))
        row = report["records"][0]
        self.assertFalse(row["partitioned_pre_end_branch_audit_complete"])
        self.assertEqual(report["partitioned_pre_end_branch_audits_complete"], 0)
        self.assertEqual(report["partitioned_pre_end_branch_count"], 0)

    def test_duplicate_opcode_entry_rejected(self):
        buttons, opcodes, data = fixture(b"\x04\x00")
        opcodes["records"].append(opcodes["records"][0])
        with self.assertRaisesRegex(ValueError, "coverage"):
            summarize_partitions(buttons, opcodes, data)

    def test_out_of_bounds_payload_rejected(self):
        buttons, opcodes, data = fixture(b"\x04\x00")
        buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = 500
        with self.assertRaisesRegex(ValueError, "bounds"):
            summarize_partitions(buttons, opcodes, data)

    def test_upstream_byte_evidence_mismatch_rejected(self):
        buttons, opcodes, data = fixture(b"\x04\x00")
        with patch("build_button_structure_audit.build_button_opcode_evidence",
                   return_value={"source_sha256": "b" * 64}):
            with self.assertRaisesRegex(ValueError, "original SWF bytes"):
                build_button_structure_audit({}, buttons, opcodes, data)


if __name__ == "__main__":
    unittest.main()
