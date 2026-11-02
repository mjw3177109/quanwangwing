import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_function_stack_audit import audit_stack_candidates


class ButtonFunctionStackAuditTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 64

    def run_body(self, body, histogram, count, **limits):
        join = {
            "source_sha256": self.sha,
            "compared_button_action_count": 1,
            "bytecode_declared_function_total_on_partitioned_records": 1,
            "bytecode_function_body_partition_status_counts": {"partitioned": 1, "rejected": 0},
            "decompiled_semantics_verified": False, "runtime_behavior_verified": False,
            "records": [{"button_character_id": 693, "comparison_class": "bytecode_only_candidate",
                         "bytecode_function_body_ranges": [{
                             "body_start_uncompressed": 0,
                             "body_end_uncompressed": len(body),
                             "body_byte_length": len(body),
                             "body_partition_status": "partitioned",
                             "body_top_level_record_count": count,
                             "body_opcode_histogram": histogram}]}],
        }
        return audit_stack_candidates(join, body, self.sha, **limits)

    def test_push_and_return_balanced_candidate(self):
        body = b"\x96\x05\x00\x07\x01\x00\x00\x00\x3e"
        report = self.run_body(body, {"0x96": 1, "0x3e": 1}, 2)
        row = report["records"][0]
        self.assertEqual(row["stack_status"], "bounded_candidate_paths")
        self.assertEqual(row["explored_candidate_state_count"], 2)
        self.assertEqual(row["max_candidate_stack_depth"], 1)
        self.assertEqual(row["potential_underflow_record_count"], 0)
        self.assertFalse(report["runtime_stack_verified"])

    def test_return_without_push_is_only_potential_underflow(self):
        report = self.run_body(b"\x3e", {"0x3e": 1}, 1)
        self.assertEqual(report["potential_underflow_record_total"], 1)
        self.assertFalse(report["decompiled_semantics_verified"])

    def test_if_follows_both_candidate_paths(self):
        body = b"\x96\x02\x00\x05\x01\x9d\x02\x00\x01\x00\x3e\x3e"
        report = self.run_body(body, {"0x96": 1, "0x9d": 1, "0x3e": 2}, 4)
        self.assertEqual(report["explored_candidate_state_total"], 4)
        self.assertEqual(report["potential_underflow_record_total"], 2)

    def test_positive_depth_loop_reaches_explicit_limit(self):
        body = b"\x96\x01\x00\x03\x99\x02\x00\xf7\xff"
        report = self.run_body(body, {"0x96": 1, "0x99": 1}, 2, max_depth=2)
        self.assertEqual(report["stack_status_counts"]["analysis_limit_reached"], 1)
        self.assertFalse(report["runtime_stack_verified"])

    def test_unknown_cfg_is_not_treated_as_verified_stack(self):
        report = self.run_body(b"\x04", {"0x04": 1}, 1)
        self.assertEqual(report["stack_status_counts"]["source_cfg_unresolved"], 1)
        self.assertIsNone(report["records"][0]["potential_underflow_record_count"])

    def test_invalid_limit_rejected(self):
        with self.assertRaisesRegex(ValueError, "Positive integer"):
            self.run_body(b"\x3e", {"0x3e": 1}, 1, max_states=0)


if __name__ == "__main__":
    unittest.main()
