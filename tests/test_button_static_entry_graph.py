import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_opcode_evidence import build_button_opcode_evidence
from build_button_tail_evidence import build_button_tail_evidence, first_action_end_offset
from build_button_static_entry_graph import (
    audit_top_level_entry_graph, build_button_static_entry_graph,
)
from test_button_opcode_evidence import fixture


def graph(payload):
    end = first_action_end_offset(payload)
    assert end is not None
    return audit_top_level_entry_graph(payload, end)


def full_audit(payload):
    manifest, buttons, data = fixture(payload)
    opcodes = build_button_opcode_evidence(manifest, buttons, data)
    tails = build_button_tail_evidence(manifest, buttons, opcodes, data)
    return build_button_static_entry_graph(manifest, buttons, opcodes, tails, data)


class ButtonStaticEntryGraphTests(unittest.TestCase):
    def test_if_branch_has_syntactic_tail_candidate_path(self):
        r = graph(b"\x9d\x02\x00\x01\x00\x00\x04\x00")
        self.assertTrue(r["syntactic_entry_path_to_post_end_candidate"])
        self.assertEqual(r["visited_post_end_candidate_record_count"], 1)
        self.assertEqual(r["visited_branch_edges_to_post_end_candidate"], 1)
        self.assertFalse(r["runtime_reachability_verified"])

    def test_jump_to_first_end_stops_before_tail(self):
        r = graph(b"\x99\x02\x00\x00\x00\x00\x04\x00")
        self.assertFalse(r["syntactic_entry_path_to_post_end_candidate"])
        self.assertTrue(r["visited_first_action_end"])

    def test_unvisited_if_branch_cannot_create_entry_path(self):
        r = graph(b"\x99\x02\x00\x05\x00\x9d\x02\x00\x01\x00\x00\x04\x00")
        self.assertFalse(r["syntactic_entry_path_to_post_end_candidate"])
        self.assertEqual(r["visited_top_level_record_count"], 2)

    def test_action_end_has_no_fallthrough(self):
        r = graph(b"\x04\x00\x04\x00")
        self.assertFalse(r["syntactic_entry_path_to_post_end_candidate"])
        self.assertEqual(r["visited_top_level_record_count"], 2)

    def test_jump_to_tail_end_does_not_reach_candidate(self):
        r = graph(b"\x99\x02\x00\x02\x00\x00\x04\x00")
        self.assertFalse(r["syntactic_entry_path_to_post_end_candidate"])
        self.assertEqual(r["visited_post_end_action_end_count"], 1)
        self.assertEqual(r["visited_branch_edges_to_post_end_action_end"], 1)

    def test_invalid_branch_operand_fails_closed(self):
        r = graph(b"\x99\x01\x00\x00\x00\x04\x00")
        self.assertEqual(r["invalid_visited_branch_target_count"], 1)
        self.assertFalse(r["syntactic_entry_path_to_post_end_candidate"])

    def test_invalid_branch_target_is_before_stream(self):
        r = graph(b"\x99\x02\x00\xf0\xff\x00")
        self.assertEqual(r["invalid_visited_branch_target_class_counts"]["before_stream"], 1)
        self.assertEqual(r["invalid_visited_branch_target_count"], 1)

    def test_invalid_branch_target_is_after_stream(self):
        r = graph(b"\x99\x02\x00\x64\x00\x00")
        self.assertEqual(r["invalid_visited_branch_target_class_counts"]["after_stream"], 1)
        self.assertEqual(r["invalid_visited_branch_target_count"], 1)

    def test_invalid_branch_target_is_record_interior(self):
        r = graph(b"\x99\x02\x00\xfc\xff\x00")
        self.assertEqual(r["invalid_visited_branch_target_class_counts"]["record_interior"], 1)
        self.assertEqual(r["invalid_visited_branch_target_count"], 1)

    def test_invalid_branch_operand_length_is_separate_class(self):
        r = graph(b"\x99\x01\x00\x00\x00\x04\x00")
        self.assertEqual(r["invalid_visited_branch_target_class_counts"]["invalid_operand_length"], 1)
        self.assertEqual(sum(r["invalid_visited_branch_target_class_counts"].values()),
                         r["invalid_visited_branch_target_count"])

    def test_unmodeled_control_opcode_is_disclosed(self):
        r = graph(b"\x8a\x03\x00\x00\x00\x00\x00\x04\x00")
        self.assertEqual(r["unmodeled_visited_control_opcode_count"], 1)
        self.assertFalse(r["runtime_reachability_verified"])

    def test_unmodeled_opcode_histogram_counts_only_visited_records(self):
        # Jump skips the first unmodeled opcode; the second is on the entry path.
        r = graph(b"\x99\x02\x00\x04\x00\x8a\x00\x00\x00\x8d\x00\x00\x00\x00\x04\x00")
        self.assertEqual(r["unmodeled_visited_control_opcode_count"], 1)
        self.assertEqual(r["unmodeled_visited_control_opcode_counts"]["0x8a"], 0)
        self.assertEqual(r["unmodeled_visited_control_opcode_counts"]["0x8d"], 1)
        self.assertEqual(sum(r["unmodeled_visited_control_opcode_counts"].values()), 1)

    def test_unmodeled_opcode_histogram_full_report_closes(self):
        r = full_audit(b"\x8a\x00\x00\x00\x00\x04\x00")
        counts = r["unmodeled_visited_control_opcode_totals"]
        self.assertEqual(counts["0x8a"], 1)
        self.assertEqual(sum(counts.values()), r["unmodeled_visited_control_opcode_total"])
        self.assertEqual(counts, r["graphs"][0]["unmodeled_visited_control_opcode_counts"])
        self.assertFalse(r["runtime_reachability_verified"])

    def test_unmodeled_opcode_histogram_excludes_unvisited_tail(self):
        r = graph(b"\x00\x8a\x00\x00\x00\x00")
        self.assertEqual(r["unmodeled_visited_control_opcode_count"], 0)
        self.assertTrue(all(n == 0 for n in r["unmodeled_visited_control_opcode_counts"].values()))

    def test_visited_define_function_header_complete(self):
        r = graph(b"\x9b\x06\x00f\x00\x00\x00\x00\x00\x00")
        self.assertEqual(r["visited_define_function_header_status_counts"]["complete"], 1)
        self.assertEqual(r["visited_define_function_parameter_total"], 0)
        self.assertEqual(r["visited_define_function_declared_body_byte_total"], 0)
        self.assertFalse(r["runtime_reachability_verified"])

    def test_visited_define_function_parameter_and_body_size(self):
        r = graph(b"\x9b\x09\x00f\x00\x01\x00p\x00\x01\x00\x00\x00")
        self.assertEqual(r["visited_define_function_header_status_counts"]["complete"], 1)
        self.assertEqual(r["visited_define_function_parameter_total"], 1)
        self.assertEqual(r["visited_define_function_declared_body_byte_total"], 1)

    def test_define_function_code_size_mismatch_is_not_complete(self):
        r = graph(b"\x9b\x07\x00f\x00\x00\x00\x02\x00\x04\x00")
        self.assertEqual(r["visited_define_function_header_status_counts"]["code_size_mismatch"], 1)
        self.assertEqual(r["visited_define_function_declared_body_byte_total"], 0)

    def test_define_function_malformed_header_is_bounded(self):
        r = graph(b"\x9b\x02\x00xy\x00")
        self.assertEqual(r["visited_define_function_header_status_counts"]["malformed_header"], 1)
        self.assertFalse(r["runtime_reachability_verified"])

    def test_define_function_aggregate_and_no_names(self):
        r = full_audit(b"\x9b\x06\x00f\x00\x00\x00\x00\x00\x00")
        self.assertEqual(r["visited_define_function_header_status_totals"]["complete"], 1)
        self.assertEqual(r["visited_define_function_parameter_total"], 0)
        self.assertNotIn("function_name", str(r))
        self.assertNotIn("function_body", str(r))

    def test_long_operand_zero_not_misread_as_end(self):
        r = graph(b"\x96\x02\x00\x00\x00\x00\x04\x00")
        self.assertEqual(r["top_level_record_count"], 4)
        self.assertFalse(r["syntactic_entry_path_to_post_end_candidate"])

    def test_rejects_malformed_record_boundary(self):
        with self.assertRaisesRegex(ValueError, "exceeds verified"):
            audit_top_level_entry_graph(b"\x00\x96\x04\x00\x01", 0)

    def test_full_report_recomputes_original_bytes(self):
        r = full_audit(b"\x9d\x02\x00\x01\x00\x00\x04\x00")
        self.assertEqual(r["trailing_record_count"], 1)
        self.assertEqual(r["graphs_with_syntactic_entry_path_to_post_end_candidate"], 1)
        self.assertFalse(r["runtime_reachability_verified"])
        self.assertNotIn("original_operands", str(r))
        self.assertNotIn("script_source", str(r))

    def test_tampered_tail_report_is_rejected(self):
        manifest, buttons, data = fixture(b"\x9d\x02\x00\x01\x00\x00\x04\x00")
        opcodes = build_button_opcode_evidence(manifest, buttons, data)
        tails = build_button_tail_evidence(manifest, buttons, opcodes, data)
        bad = copy.deepcopy(tails)
        bad["tail_records"][0]["trailing_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "does not match verified"):
            build_button_static_entry_graph(manifest, buttons, opcodes, bad, data)


if __name__ == "__main__":
    unittest.main()
