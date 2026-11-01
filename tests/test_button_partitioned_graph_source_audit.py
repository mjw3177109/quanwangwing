import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from button_action_structure import ActionStructureError, partition_top_level_actions
from build_button_partitioned_graph_source_audit import (
    STATUSES, build_source_partitioned_graph,
)


def fixture(payload, status=None):
    cid, offset = 693, 8
    data = b"x" * offset + b"\x00" * 4 + payload
    buttons = {
        "embedded_action_record_count": 1,
        "buttons": [{"character_id": cid, "embedded_action_records": [{
            "offset_uncompressed": offset,
            "action_bytes_including_terminator": len(payload),
        }]}],
    }
    opcodes = {"source_sha256": "a" * 64}
    try:
        parsed = partition_top_level_actions(payload)
    except ActionStructureError:
        parsed = None
    if status is None:
        status = "partitioned" if parsed is not None else "unsupported_nested_scope"
    item = {
        "button_character_id": cid,
        "action_offset_uncompressed": offset,
        "action_byte_length": len(payload),
        "status": status,
        "first_top_level_end_offset": (
            parsed["first_top_level_action_end_offset"] if parsed else None),
        "top_level_record_count": parsed["top_level_record_count"] if parsed else None,
        "declared_function_count": parsed["declared_function_count"] if parsed else None,
        "declared_function_body_byte_total": (
            parsed["declared_function_body_byte_total"] if parsed else None),
    }
    structure = {
        "source_sha256": "a" * 64,
        "embedded_action_record_count": 1,
        "records": [item],
    }
    return buttons, opcodes, data, structure


def build(payload, status=None):
    buttons, opcodes, data, structure = fixture(payload, status)
    with patch("build_button_partitioned_graph_source_audit.build_button_structure_audit",
               return_value=structure):
        return build_source_partitioned_graph({}, buttons, opcodes, data)


class SourcePartitionedGraphTests(unittest.TestCase):
    def test_simple_verified_graph(self):
        result = build(bytes.fromhex("04 00"))
        self.assertEqual(result["graph_verified_count"], 1)
        self.assertEqual(result["visited_record_total_in_verified_graphs"], 2)
        self.assertEqual(result["graph_status_counts"]["verified_graph"], 1)
        self.assertFalse(result["runtime_reachability_verified"])

    def test_jump_to_post_end_is_only_syntactic(self):
        result = build(bytes.fromhex("99 02 00 01 00 00 04 00"))
        self.assertEqual(result["graphs_with_syntactic_entry_path_to_post_end_record"], 1)
        self.assertEqual(result["visited_branch_target_class_totals"]["post_end_record"], 1)
        self.assertFalse(result["records"][0]["runtime_reachability_verified"])

    def test_function_body_not_treated_as_top_level(self):
        function = bytes.fromhex("9b 06 00 66 00 00 00 02 00")
        result = build(function + bytes.fromhex("04 00 04 00"))
        self.assertEqual(result["graph_verified_count"], 1)
        self.assertEqual(result["visited_record_total_in_verified_graphs"], 3)
        self.assertEqual(result["visited_post_end_record_total_in_verified_graphs"], 0)

    def test_missing_end_is_unverified(self):
        result = build(bytes.fromhex("04"))
        self.assertEqual(result["graph_status_counts"]["missing_top_level_end"], 1)
        self.assertEqual(result["graph_verified_count"], 0)

    def test_unsupported_scope_is_unverified(self):
        result = build(bytes.fromhex("94 02 00 00 00 00"))
        self.assertEqual(result["graph_status_counts"]["unsupported_nested_scope"], 1)
        self.assertEqual(result["graph_verified_count"], 0)

    def test_invalid_branch_operand_is_rejected(self):
        result = build(bytes.fromhex("99 01 00 00 00"))
        self.assertEqual(result["graph_status_counts"]["graph_rejected"], 1)
        self.assertFalse(result["records"][0]["graph_verified"])

    def test_missing_source_row_fails_closed(self):
        buttons, opcodes, data, structure = fixture(bytes.fromhex("04 00"))
        structure["records"][0]["action_offset_uncompressed"] = 12
        with patch("build_button_partitioned_graph_source_audit.build_button_structure_audit",
                   return_value=structure):
            with self.assertRaisesRegex(ValueError, "source action"):
                build_source_partitioned_graph({}, buttons, opcodes, data)

    def test_structural_disagreement_fails_closed(self):
        buttons, opcodes, data, structure = fixture(bytes.fromhex("04 00"))
        structure["records"][0]["top_level_record_count"] = 999
        with patch("build_button_partitioned_graph_source_audit.build_button_structure_audit",
                   return_value=structure):
            with self.assertRaisesRegex(ValueError, "disagrees"):
                build_source_partitioned_graph({}, buttons, opcodes, data)

    def test_source_hash_mismatch_fails_closed(self):
        buttons, opcodes, data, structure = fixture(bytes.fromhex("04 00"))
        structure["source_sha256"] = "b" * 64
        with patch("build_button_partitioned_graph_source_audit.build_button_structure_audit",
                   return_value=structure):
            with self.assertRaisesRegex(ValueError, "provenance"):
                build_source_partitioned_graph({}, buttons, opcodes, data)

    def test_status_keys_stable(self):
        result = build(bytes.fromhex("04 00"))
        self.assertEqual(set(result["graph_status_counts"]), set(STATUSES))
        self.assertEqual(sum(result["graph_status_counts"].values()), 1)


if __name__ == "__main__":
    unittest.main()
