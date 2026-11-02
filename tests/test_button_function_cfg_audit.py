import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_function_cfg_audit import audit_function_cfg


class FunctionCfgAuditTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 64
        self.body = b"\x99\x02\x00\x01\x00\x1c\x3e"
        self.join = {
            "source_sha256": self.sha, "compared_button_action_count": 1,
            "bytecode_declared_function_total_on_partitioned_records": 1,
            "bytecode_function_body_partition_status_counts": {"partitioned": 1, "rejected": 0},
            "decompiled_semantics_verified": False, "runtime_behavior_verified": False,
            "records": [{"button_character_id": 693, "comparison_class": "bytecode_only_candidate",
                         "bytecode_function_body_ranges": [{
                             "body_start_uncompressed": 0, "body_end_uncompressed": 7,
                             "body_byte_length": 7, "body_partition_status": "partitioned",
                             "body_top_level_record_count": 3,
                             "body_opcode_histogram": {"0x1c": 1, "0x3e": 1, "0x99": 1}}]}],
        }

    def use_body(self, body, hist, count):
        self.body = body
        item = self.join["records"][0]["bytecode_function_body_ranges"][0]
        item.update(body_end_uncompressed=len(body), body_byte_length=len(body),
                    body_top_level_record_count=count, body_opcode_histogram=hist)

    def test_jump_skips_record(self):
        d = audit_function_cfg(self.join, self.body, self.sha)
        self.assertEqual(d["static_entry_reachable_candidate_total"], 2)
        self.assertEqual(d["static_entry_unreachable_candidate_total"], 1)
        self.assertFalse(d["runtime_reachability_verified"])

    def test_if_preserves_both_paths(self):
        self.use_body(b"\x9d\x02\x00\x01\x00\x1c\x3e",
                      {"0x1c": 1, "0x3e": 1, "0x9d": 1}, 3)
        self.assertEqual(audit_function_cfg(self.join, self.body, self.sha)[
            "static_entry_reachable_candidate_total"], 3)

    def test_return_terminates_fallthrough(self):
        self.use_body(b"\x3e\x1c", {"0x1c": 1, "0x3e": 1}, 2)
        self.assertEqual(audit_function_cfg(self.join, self.body, self.sha)[
            "static_entry_unreachable_candidate_total"], 1)

    def test_unknown_opcode_is_unresolved(self):
        self.use_body(b"\x04\x3e", {"0x04": 1, "0x3e": 1}, 2)
        d = audit_function_cfg(self.join, self.body, self.sha)
        self.assertEqual(d["graph_status_counts"]["unresolved_opcode_or_target"], 1)
        self.assertIsNone(d["records"][0]["static_entry_reachable_record_count"])

    def test_invalid_target_is_unresolved(self):
        self.use_body(b"\x99\x02\x00\xfe\xff\x1c\x3e",
                      {"0x1c": 1, "0x3e": 1, "0x99": 1}, 3)
        self.assertEqual(audit_function_cfg(self.join, self.body, self.sha)[
            "records"][0]["invalid_branch_target_count"], 1)

    def test_sha_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            audit_function_cfg(self.join, self.body, "b" * 64)

    def test_duplicate_body_rejected(self):
        self.join["records"][0]["bytecode_function_body_ranges"] *= 2
        self.join["bytecode_declared_function_total_on_partitioned_records"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            audit_function_cfg(self.join, self.body, self.sha)

    def test_rejected_body_not_verified(self):
        item = self.join["records"][0]["bytecode_function_body_ranges"][0]
        item["body_partition_status"] = "rejected"
        self.join["bytecode_function_body_partition_status_counts"] = {"partitioned": 0, "rejected": 1}
        d = audit_function_cfg(self.join, self.body, self.sha)
        self.assertEqual(d["graph_status_counts"]["source_partition_rejected"], 1)
        self.assertEqual(d["complete_graph_record_total"], 0)


if __name__ == "__main__":
    unittest.main()
