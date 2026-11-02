import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_function_branch_audit import audit_branches


class BranchAuditTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 64
        # Jump +2 from offset 5 to ActionEnd at offset 7.
        self.body = b"\x99\x02\x00\x02\x00\x04\x04\x00"
        self.join = {
            "source_sha256": self.sha, "compared_button_action_count": 1,
            "bytecode_declared_function_total_on_partitioned_records": 1,
            "bytecode_function_body_partition_status_counts": {"partitioned": 1, "rejected": 0},
            "decompiled_semantics_verified": False, "runtime_behavior_verified": False,
            "records": [{"button_character_id": 693, "comparison_class": "bytecode_only_candidate",
                         "bytecode_function_body_ranges": [self.entry()]}],
        }

    def entry(self):
        return {"body_start_uncompressed": 0, "body_end_uncompressed": len(self.body),
                "body_byte_length": len(self.body), "body_partition_status": "partitioned",
                "body_top_level_record_count": 4,
                "body_opcode_histogram": {"0x00": 1, "0x04": 2, "0x99": 1}}

    def test_branch_to_record_start(self):
        d = audit_branches(self.join, self.body, self.sha)
        self.assertEqual(d["branch_target_classification_counts"]["record_start"], 1)
        self.assertEqual(d["records"][0]["target_offset_uncompressed"], 7)
        self.assertFalse(d["runtime_behavior_verified"])

    def test_branch_to_body_end(self):
        self.body = b"\x99\x02\x00\x00\x00"
        self.join["records"][0]["bytecode_function_body_ranges"][0].update({
            "body_end_uncompressed": 5, "body_byte_length": 5,
            "body_top_level_record_count": 1, "body_opcode_histogram": {"0x99": 1}})
        d = audit_branches(self.join, self.body, self.sha)
        self.assertEqual(d["branch_target_classification_counts"]["body_end"], 1)

    def test_branch_to_middle_of_operand(self):
        self.body = b"\x99\x02\x00\xfe\xff\x04\x04\x00"
        self.assertEqual(audit_branches(self.join, self.body, self.sha)[
            "branch_target_classification_counts"]["non_record_boundary"], 1)

    def test_branch_outside_body(self):
        self.body = b"\x99\x02\x00\xf0\xff\x04\x04\x00"
        self.assertEqual(audit_branches(self.join, self.body, self.sha)[
            "branch_target_classification_counts"]["outside_body"], 1)

    def test_bad_operand_length_is_explicit(self):
        self.body = b"\x99\x01\x00\x01\x04\x04\x00"
        self.join["records"][0]["bytecode_function_body_ranges"][0].update({
            "body_end_uncompressed": 7, "body_byte_length": 7,
            "body_top_level_record_count": 4,
            "body_opcode_histogram": {"0x00": 1, "0x04": 2, "0x99": 1}})
        d = audit_branches(self.join, self.body, self.sha)
        self.assertEqual(d["branch_target_classification_counts"]["invalid_operand_length"], 1)
        self.assertIsNone(d["records"][0]["target_offset_uncompressed"])

    def test_mismatched_inventory_rejected(self):
        self.join["records"][0]["bytecode_function_body_ranges"][0]["body_opcode_histogram"] = {"0x99": 1}
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            audit_branches(self.join, self.body, self.sha)

    def test_rejected_body_is_not_claimed_verified(self):
        entry = self.join["records"][0]["bytecode_function_body_ranges"][0]
        entry["body_partition_status"] = "rejected"
        self.join["bytecode_function_body_partition_status_counts"] = {"partitioned": 0, "rejected": 1}
        d = audit_branches(self.join, self.body, self.sha)
        self.assertEqual(d["rejected_function_body_count"], 1)
        self.assertEqual(d["branch_record_count"], 0)

    def test_source_sha_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "source SHA"):
            audit_branches(self.join, self.body, "b" * 64)

    def test_invalid_function_bounds_rejected(self):
        self.join["records"][0]["bytecode_function_body_ranges"][0]["body_end_uncompressed"] = 100
        with self.assertRaisesRegex(ValueError, "bounds"):
            audit_branches(self.join, self.body, self.sha)


if __name__ == "__main__":
    unittest.main()
