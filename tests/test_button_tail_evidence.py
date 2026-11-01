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
