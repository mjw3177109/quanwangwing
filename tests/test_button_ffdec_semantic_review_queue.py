import sys
import unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_ffdec_semantic_review_queue import build_review_queue


class ButtonFFDecSemanticReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 64
        self.export_sha = "b" * 64
        self.join = {"source_sha256": self.sha, "compared_button_action_count": 1,
                     "classification_counts": {"bytecode_only_candidate": 1},
                     "records": [{"button_character_id": 693, "action_offset_uncompressed": 100,
                                  "ffdec_export_sha256": self.export_sha,
                                  "comparison_class": "bytecode_only_candidate",
                                  "bytecode_declared_function_count": 1,
                                  "bytecode_function_body_ranges": [{"body_start_uncompressed": 110}],
                                  "lexical_function_candidate_count": 0}]}
        self.lexical = {"source_sha256": self.sha, "audited_button_action_count": 1,
                        "records": [{"button_character_id": 693, "action_offset_uncompressed": 100,
                                     "ffdec_export_sha256": self.export_sha,
                                     "ffdec_export_path": "scripts/DefineButton2_693/event.as",
                                     "lexical_function_candidate_count": 0,
                                     "lexical_branch_keyword_counts": {"if": 30, "return": 7}}]}
        self.crosswalk = {"source_sha256": self.sha, "matched_export_count": 1,
                          "records": [{"button_character_id": 693, "action_offset_uncompressed": 100,
                                       "ffdec_export_sha256": self.export_sha,
                                       "ffdec_export_path": "scripts/DefineButton2_693/event.as"}]}
        self.origins = {"source_sha256": self.sha, "function_body_count": 1,
                        "records": [{"button_character_id": 693, "function_body_start_uncompressed": 110,
                                     "origin_status": "bounded_origin_candidates",
                                     "source_if_opcode_count": 1,
                                     "if_operand_origin_counts": {"literal_string": 1}}]}

    def build(self):
        return build_review_queue(self.join, self.lexical, self.crosswalk, self.origins)

    def test_review_queue_keeps_scope_and_no_semantic_claim(self):
        d = self.build()
        self.assertEqual(d["manual_review_queue_count"], 1)
        row = d["records"][0]
        self.assertEqual(row["source_action_if_opcode_count"], 1)
        self.assertEqual(row["ffdec_event_lexical_if_keyword_count"], 30)
        self.assertEqual(row["source_if_operand_origin_types"], ["literal_string"])
        self.assertFalse(row["decompiled_semantics_verified"])
        self.assertTrue(row["manual_semantic_review_required"])

    def test_export_hash_mismatch_rejected(self):
        self.lexical["records"][0]["ffdec_export_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "content hash mismatch"):
            self.build()

    def test_missing_function_origin_rejected(self):
        self.origins["records"] = []
        self.origins["function_body_count"] = 0
        with self.assertRaisesRegex(ValueError, "Missing source-backed"):
            self.build()

    def test_unresolved_origin_not_claimed_complete(self):
        self.origins["records"][0]["origin_status"] = "analysis_limit_reached"
        self.origins["records"][0]["if_operand_origin_counts"] = None
        row = self.build()["records"][0]
        self.assertFalse(row["operand_origins_complete"])
        self.assertIsNone(row["source_if_operand_origin_types"])

    def test_mismatched_source_hash_rejected(self):
        self.crosswalk["source_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
            self.build()

    def test_duplicate_button_event_rejected(self):
        self.lexical["records"].append(deepcopy(self.lexical["records"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate lexical"):
            self.build()


if __name__ == "__main__":
    unittest.main()
