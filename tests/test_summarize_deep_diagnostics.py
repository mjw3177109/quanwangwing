import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from summarize_deep_diagnostics import summarize


class DeepDiagnosticsSummaryTests(unittest.TestCase):
    def base(self):
        return {
            "phase": "deep",
            "java_version": "1.8.0_504",
            "as3_tag_present": False,
            "source": {"sha256": "a" * 64, "size_bytes": 17244375},
            "deep_diagnostics_complete": True,
            "commands": {
                "as1_as2": {
                    "ok": True, "exit_code": 0, "timed_out": False,
                    "duration_seconds": 82.5, "timeout_seconds": 180,
                    "detected_errors": [], "args": ["private", "source"],
                    "log": "private/path.log",
                },
                "link_report": {
                    "ok": True, "exit_code": 0, "timed_out": False,
                    "duration_seconds": 41.25, "timeout_seconds": 180,
                    "detected_errors": [], "args": ["private", "source"],
                    "log": "private/path.log",
                },
            },
        }

    def test_success_is_metadata_only(self):
        result = summarize(self.base())
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["deep_diagnostics_complete"])
        self.assertEqual(result["required_commands"], ["as1_as2", "link_report"])
        self.assertEqual(result["commands"]["as1_as2"]["duration_seconds"], 82.5)
        encoded = json.dumps(result)
        for secret in ("private", "args", "log", "detected_errors"):
            self.assertNotIn(secret, encoded)
        self.assertFalse(result["runtime_binding_verified"])
        self.assertFalse(result["execution_verified"])

    def test_timeout_is_not_promoted_to_success(self):
        data = self.base()
        data["commands"]["link_report"]["ok"] = False
        data["commands"]["link_report"]["exit_code"] = None
        data["commands"]["link_report"]["timed_out"] = True
        data["deep_diagnostics_complete"] = False
        result = summarize(data)
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["required_commands_successful"])
        self.assertTrue(result["commands"]["link_report"]["timed_out"])

    def test_as3_is_required_only_when_source_marks_it_present(self):
        data = self.base()
        data["as3_tag_present"] = True
        result = summarize(data)
        self.assertFalse(result["required_commands_present"])
        self.assertFalse(result["deep_diagnostics_complete"])
        data["commands"]["as3"] = {
            "ok": True, "exit_code": 0, "timed_out": False,
            "duration_seconds": 1.0, "timeout_seconds": 180,
            "detected_errors": [],
        }
        result = summarize(data)
        self.assertTrue(result["required_commands_successful"])

    def test_wrong_phase_or_summary_flag_is_incomplete(self):
        data = self.base()
        data["phase"] = "scripts"
        self.assertEqual(summarize(data)["status"], "incomplete")
        data = self.base()
        data["deep_diagnostics_complete"] = False
        self.assertFalse(summarize(data)["deep_diagnostics_complete"])

    def test_invalid_source_or_command_shape_fails_closed(self):
        data = self.base()
        data["source"]["sha256"] = "not-a-sha"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            summarize(data)
        data = self.base()
        data["commands"]["as1_as2"]["timed_out"] = "false"
        with self.assertRaisesRegex(ValueError, "outcome"):
            summarize(data)


if __name__ == "__main__":
    unittest.main()
