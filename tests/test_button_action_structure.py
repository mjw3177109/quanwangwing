import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from button_action_structure import ActionStructureError, partition_top_level_actions


class ButtonActionStructureTests(unittest.TestCase):
    def test_definefunction_body_zero_is_not_top_level_end(self):
        # Header size 6, CodeSize 3, body contains an ActionEnd byte.
        payload = b"\x9b\x06\x00f\x00\x00\x00\x03\x00\x04\x00\x04\x00"
        result = partition_top_level_actions(payload)
        self.assertEqual(result["first_top_level_action_end_offset"], 12)
        self.assertEqual(result["top_level_record_count"], 2)
        self.assertEqual(result["declared_function_body_byte_total"], 3)
        self.assertEqual([r.start for r in result["records"]], [0, 12])

    def test_definefunction2_body_skipped(self):
        # Name='f', NumParams=0, RegisterCount=0, Flags=0, CodeSize=2.
        payload = b"\x8e\x09\x00f\x00\x00\x00\x00\x00\x00\x02\x00\x00\x04\x00"
        result = partition_top_level_actions(payload)
        self.assertEqual(result["declared_function_count"], 1)
        self.assertEqual(result["first_top_level_action_end_offset"], 14)
        self.assertEqual(result["top_level_record_count"], 2)

    def test_end_and_post_end_records_separated(self):
        result = partition_top_level_actions(b"\x04\x00\x04\x00")
        self.assertEqual(result["first_top_level_action_end_offset"], 1)
        self.assertEqual(result["top_level_post_end_record_count"], 2)
        self.assertFalse(result["runtime_reachability_verified"])

    def test_long_operand_zero_is_not_end(self):
        result = partition_top_level_actions(b"\x96\x02\x00\x00\x00\x00")
        self.assertEqual(result["first_top_level_action_end_offset"], 5)

    def test_rejects_function_body_out_of_bounds(self):
        with self.assertRaisesRegex(ActionStructureError, "body exceeds"):
            partition_top_level_actions(b"\x9b\x06\x00f\x00\x00\x00\x10\x00\x00")

    def test_rejects_unterminated_function_name(self):
        with self.assertRaisesRegex(ActionStructureError, "Unterminated"):
            partition_top_level_actions(b"\x9b\x03\x00abc\x00")

    def test_rejects_unhandled_with_scope(self):
        with self.assertRaisesRegex(ActionStructureError, "With/Try"):
            partition_top_level_actions(b"\x94\x02\x00\x00\x00\x00")

    def test_rejects_truncated_operand(self):
        with self.assertRaisesRegex(ActionStructureError, "operand exceeds"):
            partition_top_level_actions(b"\x96\x08\x00\x00")

    def test_no_original_bytes_or_names_in_summary(self):
        result = partition_top_level_actions(b"\x9b\x06\x00f\x00\x00\x00\x00\x00\x00")
        self.assertNotIn("function_name", str(result))
        self.assertNotIn("body_bytes", str(result))
        self.assertTrue(result["top_level_partition_verified"])


if __name__ == "__main__":
    unittest.main()
