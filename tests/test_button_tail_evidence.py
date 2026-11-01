import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_opcode_evidence import build_button_opcode_evidence
from build_button_tail_evidence import build_button_tail_evidence, first_action_end_offset
from test_button_opcode_evidence import fixture


def audit(payload):
    manifest, buttons, data = fixture(payload)
    opcodes = build_button_opcode_evidence(manifest, buttons, data)
    return build_button_tail_evidence(manifest, buttons, opcodes, data)


class ButtonTailEvidenceTests(unittest.TestCase):
    def test_no_tail(self):
        report = audit(b"\x04\x00")
        self.assertEqual(report["trailing_record_count"], 0)
        self.assertEqual(report["trailing_byte_total"], 0)

    def test_nonzero_tail_is_not_declared_executable(self):
        report = audit(b"\x04\x00\x77")
        self.assertEqual(report["trailing_byte_class_counts"]["nonzero_only"], 1)
        self.assertEqual(report["trailing_nonzero_byte_total"], 1)
        self.assertEqual(report["tail_records"][0]["post_end_candidate_status"], "missing_action_end")
        self.assertFalse(report["tail_records"][0]["runtime_reachability_verified"])

    def test_zero_only_tail(self):
        report = audit(b"\x04\x00\x00\x00")
        self.assertEqual(report["trailing_byte_class_counts"]["zero_only"], 1)
        self.assertEqual(report["trailing_zero_byte_total"], 2)

    def test_mixed_tail_and_candidate_walk(self):
        report = audit(b"\x04\x00\x96\x02\x00\x01\x02\x00")
        row = report["tail_records"][0]
        self.assertEqual(row["byte_class"], "mixed")
        self.assertEqual(row["post_end_candidate_status"], "terminated_at_end")
        self.assertEqual(row["post_end_candidate_record_count"], 1)
        self.assertFalse(row["runtime_reachability_verified"])

    def test_action_end_inside_long_operand_is_skipped(self):
        self.assertEqual(first_action_end_offset(b"\x96\x02\x00\x00\x01\x04\x00"), 6)
        self.assertIsNone(first_action_end_offset(b"\x96\x05\x00\x00"))

    def test_pre_end_jump_targets_tail_candidate_boundary(self):
        report = audit(b"\x99\x02\x00\x01\x00\x00\x04\x00")
        row = report["tail_records"][0]
        self.assertEqual(row["pre_end_branch_count"], 1)
        self.assertEqual(row["pre_end_branch_to_tail_record_boundary_count"], 1)
        self.assertEqual(report["pre_end_branch_target_class_counts"]["tail_record_boundary"], 1)
        self.assertFalse(row["runtime_reachability_verified"])

    def test_tail_terminator_and_first_end_are_distinct_targets(self):
        for displacement, expected in ((2, "tail_action_end"), (0, "first_action_end")):
            with self.subTest(expected=expected):
                report = audit(b"\x99\x02\x00" + displacement.to_bytes(2, "little") +
                               b"\x00\x04\x00")
                self.assertEqual(report["pre_end_branch_target_class_counts"][expected], 1)
                self.assertEqual(report["pre_end_branch_to_tail_record_boundary_count"], 0)

    def test_pre_end_interior_and_invalid_branch_operand(self):
        interior = audit(b"\x9d\x02\x00\xff\xff\x00\x04\x00")
        self.assertEqual(interior["pre_end_branch_target_class_counts"]["pre_end_record_interior"], 1)
        invalid = audit(b"\x99\x01\x00\x00\x00\x04\x00")
        self.assertEqual(invalid["pre_end_branch_target_class_counts"]["invalid_branch_operand_length"], 1)

    def test_outside_branch_targets_are_counted_without_following(self):
        for displacement, expected in ((3, "outside_after"), (-7, "outside_before")):
            with self.subTest(expected=expected):
                report = audit(b"\x99\x02\x00" + displacement.to_bytes(2, "little", signed=True) +
                               b"\x00\x04\x00")
                self.assertEqual(report["pre_end_branch_target_class_counts"][expected], 1)

    def test_branch_accounting_and_metadata_only(self):
        report = audit(b"\x9d\x02\x00\x01\x00\x00\x04\x00")
        self.assertEqual(sum(report["pre_end_branch_target_class_counts"].values()),
                         report["pre_end_branch_count"])
        self.assertEqual(sum(report["pre_end_branch_kind_counts"].values()),
                         report["pre_end_branch_count"])
        self.assertEqual(report["pre_end_branch_kind_counts"]["if"], 1)
        self.assertNotIn("original_operands", str(report))
        self.assertNotIn("script_source", str(report))

    def test_tail_record_boundary_branch_kind_split(self):
        for opcode, expected in ((0x99, "jump"), (0x9D, "if")):
            with self.subTest(expected=expected):
                report = audit(bytes((opcode, 2, 0, 1, 0, 0, 4, 0)))
                row = report["tail_records"][0]
                counts = row["tail_record_boundary_branch_kind_counts"]
                self.assertEqual(counts[expected], 1)
                self.assertEqual(counts["if" if expected == "jump" else "jump"], 0)
                self.assertEqual(report["tail_record_boundary_branch_kind_counts"], counts)
                self.assertEqual(sum(counts.values()),
                                 report["pre_end_branch_to_tail_record_boundary_count"])
                self.assertFalse(row["runtime_reachability_verified"])

    def test_tail_action_end_kind_split_and_accounting(self):
        report = audit(b"\x9d\x02\x00\x02\x00\x00\x04\x00")
        row = report["tail_records"][0]
        self.assertEqual(row["tail_action_end_branch_kind_counts"], {"jump": 0, "if": 1})
        self.assertEqual(report["tail_action_end_branch_kind_counts"], {"jump": 0, "if": 1})
        self.assertEqual(sum(report["tail_action_end_branch_kind_counts"].values()),
                         report["pre_end_branch_target_class_counts"]["tail_action_end"])
        self.assertEqual(report["tail_record_boundary_branch_kind_counts"],
                         {"jump": 0, "if": 0})

    def test_tampered_opcode_report_is_rejected(self):
        manifest, buttons, data = fixture(b"\x04\x00\x77")
        report = build_button_opcode_evidence(manifest, buttons, data)
        report["unparsed_tail_bytes"] = 999
        with self.assertRaisesRegex(ValueError, "does not match verified"):
            build_button_tail_evidence(manifest, buttons, report, data)

    def test_tampered_button_metadata_is_rejected(self):
        manifest, buttons, data = fixture(b"\x04\x00\x77")
        report = build_button_opcode_evidence(manifest, buttons, data)
        bad = copy.deepcopy(buttons)
        bad["buttons"][0]["embedded_action_records"][0]["condition_flags"] = 9
        with self.assertRaisesRegex(ValueError, "header mismatch"):
            build_button_tail_evidence(manifest, bad, report, data)


if __name__ == "__main__":
    unittest.main()
