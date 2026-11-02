import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_operand_origin_audit import audit_operand_origins, _push_origins, _push_string_values


class ButtonOperandOriginAuditTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 64

    def run_body(self, body, branch_records=(), source_status="bounded_candidate_paths", **limits):
        join = {"source_sha256": self.sha, "records": [{"button_character_id": 693,
            "bytecode_function_body_ranges": [{"body_start_uncompressed": 0,
                                                "body_end_uncompressed": len(body)}]}]}
        stack = {"function_body_count": 1, "records": [{"button_character_id": 693,
            "function_body_start_uncompressed": 0, "stack_status": source_status}]}
        branches = {"records": list(branch_records)}
        with patch("build_button_operand_origin_audit.audit_stack_candidates", return_value=stack), \
             patch("build_button_operand_origin_audit.audit_branches", return_value=branches):
            return audit_operand_origins(join, body, self.sha, **limits)

    def test_variable_read_result_flows_to_if_candidate(self):
        body = b"\x96\x03\x00\x00x\x00\x1c\x9d\x02\x00\x00\x00\x00"
        branch = {"function_body_start_uncompressed": 0, "branch_offset_uncompressed": 7,
                  "target_classification": "record_start", "target_offset_uncompressed": 12}
        report = self.run_body(body, [branch])
        self.assertEqual(report["source_get_variable_opcode_total"], 1)
        self.assertEqual(report["source_if_opcode_total"], 1)
        self.assertEqual(report["if_operand_origin_totals"], {"variable_read_result": 1})
        self.assertEqual(report["variable_name_operand_origin_totals"], {"literal_string": 1})
        self.assertFalse(report["runtime_behavior_verified"])

    def test_set_variable_name_is_below_value(self):
        body = b"\x96\x08\x00\x00x\x00\x07\x01\x00\x00\x00\x1d\x00"
        report = self.run_body(body)
        self.assertEqual(report["source_set_variable_opcode_total"], 1)
        self.assertEqual(report["variable_name_operand_origin_totals"], {"literal_string": 1})
        self.assertEqual(report["origin_status_counts"]["bounded_origin_candidates"], 1)

    def test_literal_boolean_condition_origin(self):
        body = b"\x96\x02\x00\x05\x01\x9d\x02\x00\x00\x00\x00"
        branch = {"function_body_start_uncompressed": 0, "branch_offset_uncompressed": 5,
                  "target_classification": "record_start", "target_offset_uncompressed": 10}
        report = self.run_body(body, [branch])
        self.assertEqual(report["if_operand_origin_totals"], {"literal_boolean": 1})

    def test_unresolved_source_not_upgraded(self):
        report = self.run_body(b"\x04", source_status="source_cfg_unresolved")
        self.assertEqual(report["origin_status_counts"]["source_stack_unresolved"], 1)
        self.assertIsNone(report["records"][0]["if_operand_origin_counts"])

    def test_missing_branch_provenance_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing source-verified branch"):
            self.run_body(b"\x9d\x02\x00\x00\x00\x00")

    def test_explicit_limit_prevents_complete_claim(self):
        body = b"\x96\x03\x00\x00x\x00\x1c\x00"
        report = self.run_body(body, max_states=1)
        self.assertEqual(report["origin_status_counts"]["analysis_limit_reached"], 1)

    def test_limit_after_partial_origin_evidence_withholds_counts(self):
        body = b"\x96\x03\x00\x00x\x00\x1c\x9d\x02\x00\x00\x00\x00"
        branch = {"function_body_start_uncompressed": 0, "branch_offset_uncompressed": 7,
                  "target_classification": "record_start", "target_offset_uncompressed": 12}
        report = self.run_body(body, [branch], max_states=3)
        row = report["records"][0]
        self.assertEqual(row["origin_status"], "analysis_limit_reached")
        self.assertIsNone(row["if_operand_origin_counts"])
        self.assertIsNone(row["variable_name_operand_origin_counts"])
        self.assertEqual(report["if_operand_origin_totals"], {})
        self.assertEqual(report["variable_name_operand_origin_totals"], {})

    def test_underflow_does_not_claim_complete_producer_origins(self):
        body = b"\x9d\x02\x00\x00\x00\x00"
        branch = {"function_body_start_uncompressed": 0, "branch_offset_uncompressed": 0,
                  "target_classification": "record_start", "target_offset_uncompressed": 5}
        report = self.run_body(body, [branch])
        row = report["records"][0]
        self.assertEqual(row["origin_status"], "candidate_underflow_detected")
        self.assertEqual(row["candidate_underflow_record_count"], 1)
        self.assertIsNone(row["if_operand_origin_counts"])
        self.assertIsNone(row["variable_name_operand_origin_counts"])
        self.assertEqual(report["if_operand_origin_totals"], {})

    def test_actionpush_literal_equality_without_disclosing_values(self):
        # Two identical strings in one ActionPush produce the same local class.
        body = b"\x96\x0e\x00\x00alpha\x00\x00alpha\x00\x00"
        report = self.run_body(body)
        row = report["records"][0]
        self.assertEqual(row["literal_string_equivalence_classes_in_push_order"], ["S1", "S1"])
        self.assertEqual(report["literal_string_occurrence_count"], 2)
        self.assertEqual(report["distinct_literal_string_class_count"], 1)
        self.assertEqual(report["literal_string_class_occurrence_counts"], {"S1": 2})
        self.assertNotIn("alpha", json.dumps(report))
        self.assertFalse(report["runtime_behavior_verified"])

    def test_string_locations_include_non_string_element_indices(self):
        body = b"\x96\x08\x00\x05\x01\x00x\x00\x00y\x00\x00"
        row = self.run_body(body)["records"][0]
        self.assertEqual(row["literal_string_equivalence_classes_in_push_order"], ["S1", "S2"])
        self.assertEqual(row["literal_string_locations"], [
            {"push_record_offset_uncompressed": 0, "push_element_index": 1, "class_label": "S1"},
            {"push_record_offset_uncompressed": 0, "push_element_index": 2, "class_label": "S2"},
        ])
        self.assertNotIn('"x"', json.dumps(row))
        self.assertNotIn('"y"', json.dumps(row))

    def test_string_locations_identify_distinct_push_record_offsets(self):
        body = b"\x96\x03\x00\x00x\x00\x96\x03\x00\x00x\x00\x00"
        row = self.run_body(body)["records"][0]
        self.assertEqual(row["literal_string_locations"], [
            {"push_record_offset_uncompressed": 0, "push_element_index": 0, "class_label": "S1"},
            {"push_record_offset_uncompressed": 6, "push_element_index": 0, "class_label": "S1"},
        ])

    def test_unresolved_source_withholds_literal_equality(self):
        report = self.run_body(b"\x00", source_status="source_cfg_unresolved")
        self.assertIsNone(report["records"][0]["literal_string_count"])
        self.assertIsNone(report["records"][0]["literal_string_equivalence_classes_in_push_order"])
        self.assertIsNone(report["records"][0]["literal_string_locations"])
        self.assertEqual(report["literal_string_occurrence_count"], 0)

    def test_literal_string_parser_rejects_unterminated_source(self):
        with self.assertRaisesRegex(ValueError, "Unterminated"):
            _push_string_values(b"\x00secret")
        with self.assertRaisesRegex(ValueError, "Invalid ActionPush"):
            _push_string_values(b"\x07\x01")

    def test_invalid_limits_rejected(self):
        with self.assertRaisesRegex(ValueError, "Positive integer"):
            self.run_body(b"\x00", max_depth=0)

    def test_actionpush_parser_rejects_truncated_operand(self):
        with self.assertRaisesRegex(ValueError, "Invalid ActionPush"):
            _push_origins(b"\x07\x01")


if __name__ == "__main__":
    unittest.main()
