import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from button_action_structure import ActionStructureError
from button_partitioned_entry_graph import audit_partitioned_entry_graph


FUNCTION = bytes.fromhex("9b 06 00 66 00 00 00 02 00")


class PartitionedButtonEntryGraphTests(unittest.TestCase):
    def test_end_terminates_before_post_end_syntax(self):
        result = audit_partitioned_entry_graph(bytes.fromhex("04 00 04 00"))
        self.assertEqual(result["visited_record_count"], 2)
        self.assertEqual(result["visited_post_end_record_count"], 0)
        self.assertFalse(result["syntactic_entry_path_to_post_end_record"])
        self.assertFalse(result["runtime_reachability_verified"])

    def test_jump_to_post_end_record_is_only_syntactic(self):
        result = audit_partitioned_entry_graph(bytes.fromhex("99 02 00 01 00 00 04 00"))
        self.assertEqual(result["visited_branch_target_class_counts"]["post_end_record"], 1)
        self.assertEqual(result["visited_post_end_record_count"], 1)
        self.assertTrue(result["syntactic_entry_path_to_post_end_record"])
        self.assertFalse(result["runtime_reachability_verified"])

    def test_if_has_target_and_fallthrough_edges(self):
        result = audit_partitioned_entry_graph(bytes.fromhex("9d 02 00 01 00 00 04 00"))
        self.assertTrue(result["visited_first_end"])
        self.assertEqual(result["visited_branch_kind_counts"]["if"], 1)
        self.assertEqual(result["visited_post_end_record_count"], 1)

    def test_function_body_is_not_walked_as_top_level(self):
        payload = FUNCTION + bytes.fromhex("04 00 04 00")
        result = audit_partitioned_entry_graph(payload)
        self.assertEqual(result["top_level_record_count"], 3)
        self.assertEqual(result["visited_record_count"], 3)
        self.assertEqual(result["declared_function_count"], 1)
        self.assertEqual(result["declared_function_body_byte_total"], 2)
        self.assertFalse(result["syntactic_entry_path_to_post_end_record"])

    def test_branch_into_function_body_not_traversed(self):
        payload = bytes.fromhex("99 02 00 09 00") + FUNCTION + bytes.fromhex("04 00 00")
        result = audit_partitioned_entry_graph(payload)
        self.assertEqual(result["visited_branch_target_class_counts"]["function_body"], 1)
        self.assertEqual(result["visited_record_count"], 1)
        self.assertFalse(result["syntactic_entry_path_to_post_end_record"])

    def test_invalid_branch_operand_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "operand length"):
            audit_partitioned_entry_graph(bytes.fromhex("99 01 00 00 00"))

    def test_unsupported_nested_scope_fails_closed(self):
        with self.assertRaises(ActionStructureError):
            audit_partitioned_entry_graph(bytes.fromhex("94 02 00 00 00 00"))

    def test_missing_top_level_end_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Missing top-level ActionEnd"):
            audit_partitioned_entry_graph(bytes.fromhex("04"))

    def test_self_loop_is_bounded(self):
        result = audit_partitioned_entry_graph(bytes.fromhex("99 02 00 fb ff 00"))
        self.assertEqual(result["visited_record_count"], 1)
        self.assertFalse(result["visited_first_end"])
        self.assertFalse(result["runtime_reachability_verified"])


if __name__ == "__main__":
    unittest.main()
