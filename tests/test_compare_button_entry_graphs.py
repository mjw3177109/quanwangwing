import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_button_entry_graphs import compare_entry_graphs


def fixture():
    source = "a" * 64
    old = {
        "source_sha256": source,
        "graph_record_count": 1,
        "runtime_reachability_verified": False,
        "graphs": [{
            "button_character_id": 693,
            "action_offset_uncompressed": 80,
            "runtime_reachability_verified": False,
            "top_level_partition_verified": False,
            "visited_define_function_body_shadowed_record_count": 13,
            "visited_top_level_record_count": 18,
            "visited_post_end_candidate_record_count": 4,
            "syntactic_entry_path_to_post_end_candidate": True,
        }],
    }
    new = {
        "source_sha256": source,
        "embedded_action_record_count": 2,
        "graph_verified_count": 2,
        "runtime_reachability_verified": False,
        "records": [{
            "button_character_id": 693,
            "action_offset_uncompressed": 80,
            "runtime_reachability_verified": False,
            "graph_verified": True,
            "status": "verified_graph",
            "visited_record_count": 5,
            "visited_post_end_record_count": 1,
            "syntactic_entry_path_to_post_end_record": False,
        }, {
            "button_character_id": 701,
            "action_offset_uncompressed": 120,
            "runtime_reachability_verified": False,
            "graph_verified": True,
            "status": "verified_graph",
            "visited_record_count": 2,
            "visited_post_end_record_count": 0,
            "syntactic_entry_path_to_post_end_record": False,
        }],
    }
    return old, new


class GraphComparisonTests(unittest.TestCase):
    def test_source_keyed_tail_subset_and_deltas(self):
        old, new = fixture()
        r = compare_entry_graphs(old, new)
        self.assertEqual(r["legacy_tail_graph_count"], 1)
        self.assertEqual(r["partitioned_source_graph_count"], 2)
        self.assertEqual(r["compared_count"], 1)
        self.assertEqual(r["visited_record_delta_total"], -13)
        self.assertEqual(r["post_end_candidate_delta_total"], -3)
        self.assertEqual(r["changed_syntactic_path_count"], 1)
        self.assertEqual(r["legacy_shadowed_function_body_record_total"], 13)
        self.assertFalse(r["legacy_graph_replaced"])
        self.assertFalse(r["runtime_reachability_verified"])
        self.assertEqual(r["records"][0]["button_character_id"], 693)

    def test_equal_graphs_are_not_reported_as_changed(self):
        old, new = fixture()
        new["records"][0].update({
            "visited_record_count": 18,
            "visited_post_end_record_count": 4,
            "syntactic_entry_path_to_post_end_record": True,
        })
        r = compare_entry_graphs(old, new)
        self.assertEqual(r["changed_visited_record_count"], 0)
        self.assertEqual(r["changed_post_end_candidate_count"], 0)
        self.assertEqual(r["changed_syntactic_path_count"], 0)

    def test_unverified_graph_excluded_without_invented_deltas(self):
        old, new = fixture()
        new["records"][0].update({"graph_verified": False, "status": "graph_rejected"})
        new["graph_verified_count"] = 1
        r = compare_entry_graphs(old, new)
        self.assertEqual(r["compared_count"], 0)
        self.assertEqual(r["new_graph_unverified_count"], 1)
        self.assertNotIn("visited_record_delta", r["records"][0])

    def test_source_mismatch_rejected(self):
        old, new = fixture()
        new["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            compare_entry_graphs(old, new)

    def test_missing_source_key_rejected(self):
        old, new = fixture()
        new["records"][0]["action_offset_uncompressed"] = 81
        with self.assertRaisesRegex(ValueError, "missing from partitioned"):
            compare_entry_graphs(old, new)

    def test_duplicate_source_key_rejected(self):
        old, new = fixture()
        new["records"][1]["button_character_id"] = 693
        new["records"][1]["action_offset_uncompressed"] = 80
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            compare_entry_graphs(old, new)

    def test_tampered_coverage_rejected(self):
        old, new = fixture()
        old["graph_record_count"] = 2
        with self.assertRaisesRegex(ValueError, "coverage"):
            compare_entry_graphs(old, new)

    def test_runtime_claim_rejected(self):
        old, new = fixture()
        old["graphs"][0]["runtime_reachability_verified"] = True
        with self.assertRaisesRegex(ValueError, "runtime"):
            compare_entry_graphs(old, new)

    def test_bad_numeric_and_boolean_fields_rejected(self):
        old, new = fixture()
        old["graphs"][0]["visited_top_level_record_count"] = True
        with self.assertRaisesRegex(ValueError, "count"):
            compare_entry_graphs(old, new)
        old, new = fixture()
        new["records"][0]["graph_verified"] = 1
        with self.assertRaisesRegex(ValueError, "boolean"):
            compare_entry_graphs(old, new)

    def test_no_original_bytes_or_source_in_report(self):
        old, new = fixture()
        report = compare_entry_graphs(copy.deepcopy(old), copy.deepcopy(new))
        payload = str(report)
        self.assertNotIn("original_operands", payload)
        self.assertNotIn("script_source", payload)
        self.assertNotIn("image_bytes", payload)


if __name__ == "__main__":
    unittest.main()
