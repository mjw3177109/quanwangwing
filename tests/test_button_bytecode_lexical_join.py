import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_bytecode_lexical_join import join_button_bytecode_lexical


class ButtonBytecodeLexicalJoinTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 64
        self._set_payload(b"\x9b\x06\x00f\x00\x00\x00\x02\x00\x04\x00\x00")
        self.buttons = {"source_sha256": self.sha, "embedded_action_record_count": 1,
                        "buttons": [{"character_id": 693, "embedded_action_record_count": 1,
                                     "embedded_action_records": [{"offset_uncompressed": 20,
                                          "condition_flags": 8, "action_bytes_including_terminator": len(self.payload),
                                          "ends_with_action_end": True,
                                          "is_last_by_zero_size": True}]}]}
        self.lexical = {"source_sha256": self.sha, "audited_button_action_count": 1,
                        "lexical_function_candidate_total": 0,
                        "decompiled_semantics_verified": False, "runtime_behavior_verified": False,
                        "records": [{"button_character_id": 693, "action_offset_uncompressed": 20,
                                     "ffdec_export_path": "scripts/a.as", "ffdec_export_sha256": "b"*64,
                                     "lexical_function_candidate_count": 0,
                                     "lexical_matched_function_scope_count": 0,
                                     "lexical_unmatched_function_candidate_count": 0,
                                     "decompiled_semantics_verified": False, "runtime_behavior_verified": False}]}
        self.crosswalk = {"source_sha256": self.sha, "matched_export_count": 1,
                          "source_action_record_count": 1,
                          "decompiled_semantics_verified": False, "runtime_behavior_verified": False,
                          "records": [{"button_character_id": 693, "action_offset_uncompressed": 20,
                                       "condition_flags": 8, "source_action_byte_length": len(self.payload),
                                       "ffdec_export_path": "scripts/a.as", "ffdec_export_sha256": "b"*64,
                                       "decompiled_semantics_verified": False, "runtime_behavior_verified": False}]}

    def _set_payload(self, payload):
        self.payload = payload
        # Four raw ButtonCondAction header bytes: zero final size, flags=8.
        self.data = b"\x00" * 20 + b"\x00\x00\x08\x00" + payload

    def run_join(self):
        return join_button_bytecode_lexical(self.buttons, self.lexical, self.crosswalk, self.data, self.sha)

    def test_bytecode_only_source_candidate(self):
        result = self.run_join()
        self.assertEqual(result["bytecode_declared_function_total_on_partitioned_records"], 1)
        self.assertEqual(result["classification_counts"]["bytecode_only_candidate"], 1)
        self.assertFalse(result["decompiled_semantics_verified"])
        self.assertNotIn("function f", str(result))

    def test_source_backed_function_body_range_is_half_open(self):
        result = self.run_join()
        ranges = result["records"][0]["bytecode_function_body_ranges"]
        self.assertEqual(ranges, [{
            "opcode": "DefineFunction",
            "declaration_offset_uncompressed": 24,
            "body_start_uncompressed": 33,
            "body_end_uncompressed": 35,
            "body_byte_length": 2,
            "body_partition_status": "partitioned",
            "body_top_level_record_count": 2,
            "body_opcode_histogram": {"0x00": 1, "0x04": 1},
            "body_first_action_end_offset_uncompressed": 34,
            "body_post_end_record_count": 0,
        }])
        self.assertEqual(result["bytecode_function_body_byte_total_on_partitioned_records"], 2)
        self.assertFalse(result["runtime_behavior_verified"])

    def test_function_body_opcode_histogram_is_source_scoped(self):
        result = self.run_join()
        body = result["records"][0]["bytecode_function_body_ranges"][0]
        self.assertEqual(body["body_partition_status"], "partitioned")
        self.assertEqual(body["body_opcode_histogram"], {"0x00": 1, "0x04": 1})
        self.assertEqual(body["body_top_level_record_count"], 2)
        self.assertEqual(body["body_first_action_end_offset_uncompressed"], 34)
        self.assertEqual(body["body_post_end_record_count"], 0)
        self.assertEqual(result["bytecode_function_body_record_total"], 2)
        self.assertEqual(result["bytecode_function_body_partition_status_counts"],
                         {"partitioned": 1, "rejected": 0})

    def test_malformed_nested_function_body_is_explicitly_rejected(self):
        # Parent header is valid; the declared 1-byte body has a truncated
        # extended opcode, so no function-body opcode claim may be made.
        self._set_payload(b"\x9b\x06\x00f\x00\x00\x00\x01\x00\x9b\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = len(self.payload)
        self.crosswalk["records"][0]["source_action_byte_length"] = len(self.payload)
        result = self.run_join()
        body = result["records"][0]["bytecode_function_body_ranges"][0]
        self.assertEqual(body["body_partition_status"], "rejected")
        self.assertIsNone(body["body_opcode_histogram"])
        self.assertIsNone(body["body_top_level_record_count"])
        self.assertEqual(result["bytecode_function_body_partition_status_counts"]["rejected"], 1)
        self.assertEqual(result["bytecode_function_body_record_total"], 0)
        self.assertEqual(result["source_partition_rejected_count"], 0)

    def test_post_end_body_records_are_only_syntactic(self):
        self._set_payload(b"\x9b\x06\x00f\x00\x00\x00\x02\x00\x00\x04\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = len(self.payload)
        self.crosswalk["records"][0]["source_action_byte_length"] = len(self.payload)
        result = self.run_join()
        body = result["records"][0]["bytecode_function_body_ranges"][0]
        self.assertEqual(body["body_first_action_end_offset_uncompressed"], 33)
        self.assertEqual(body["body_post_end_record_count"], 1)
        self.assertFalse(result["runtime_behavior_verified"])

    def test_no_function_body_has_empty_aggregate(self):
        self._set_payload(b"\x04\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = len(self.payload)
        self.crosswalk["records"][0]["source_action_byte_length"] = len(self.payload)
        result = self.run_join()
        self.assertEqual(result["records"][0]["bytecode_function_body_ranges"], [])
        self.assertEqual(result["bytecode_function_body_partition_status_counts"],
                         {"partitioned": 0, "rejected": 0})
        self.assertEqual(result["bytecode_function_body_opcode_histogram"], {})

    def test_with_scope_in_function_body_is_not_silently_accepted(self):
        self._set_payload(b"\x9b\x06\x00f\x00\x00\x00\x03\x00\x94\x00\x00\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = len(self.payload)
        self.crosswalk["records"][0]["source_action_byte_length"] = len(self.payload)
        body = self.run_join()["records"][0]["bytecode_function_body_ranges"][0]
        self.assertEqual(body["body_partition_status"], "rejected")
        self.assertIsNone(body["body_first_action_end_offset_uncompressed"])

    def test_definefunction2_source_backed_range(self):
        # 9-byte DefineFunction2 header, 1-byte body, then top-level End.
        self._set_payload(b"\x8e\x09\x00f\x00\x00\x00\x00\x00\x00\x01\x00\x04\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = len(self.payload)
        self.crosswalk["records"][0]["source_action_byte_length"] = len(self.payload)
        result = self.run_join()
        self.assertEqual(result["records"][0]["bytecode_function_body_ranges"], [{
            "opcode": "DefineFunction2",
            "declaration_offset_uncompressed": 24,
            "body_start_uncompressed": 36,
            "body_end_uncompressed": 37,
            "body_byte_length": 1,
            "body_partition_status": "partitioned",
            "body_top_level_record_count": 1,
            "body_opcode_histogram": {"0x04": 1},
            "body_first_action_end_offset_uncompressed": None,
            "body_post_end_record_count": 0,
        }])
        self.assertEqual(result["bytecode_function_body_byte_total_on_partitioned_records"], 1)

    def test_rejected_partition_has_no_verified_function_ranges(self):
        self._set_payload(b"\x9b\xff\xff\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = len(self.payload)
        self.crosswalk["records"][0]["source_action_byte_length"] = len(self.payload)
        result = self.run_join()
        self.assertIsNone(result["records"][0]["bytecode_function_body_ranges"])
        self.assertEqual(result["bytecode_function_body_byte_total_on_partitioned_records"], 0)
        self.assertEqual(result["source_partition_rejected_count"], 1)

    def test_both_present_not_semantics_verified(self):
        self.lexical["records"][0]["lexical_function_candidate_count"] = 1
        self.lexical["records"][0]["lexical_matched_function_scope_count"] = 1
        self.lexical["lexical_function_candidate_total"] = 1
        self.assertEqual(self.run_join()["classification_counts"]["both_present_unverified"], 1)

    def test_lexical_only_candidate(self):
        self._set_payload(b"\x04\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = 2
        self.crosswalk["records"][0]["source_action_byte_length"] = 2
        self.lexical["records"][0]["lexical_function_candidate_count"] = 1
        self.lexical["records"][0]["lexical_matched_function_scope_count"] = 1
        self.lexical["lexical_function_candidate_total"] = 1
        self.assertEqual(self.run_join()["classification_counts"]["lexical_only_candidate"], 1)

    def test_malformed_bytecode_is_explicitly_rejected(self):
        self._set_payload(b"\x9b\xff\xff\x00")
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] = len(self.payload)
        self.crosswalk["records"][0]["source_action_byte_length"] = len(self.payload)
        self.assertEqual(self.run_join()["classification_counts"]["source_partition_rejected"], 1)

    def test_raw_flags_checked_even_if_metadata_reports_agree(self):
        self.buttons["buttons"][0]["embedded_action_records"][0]["condition_flags"] = 9
        self.crosswalk["records"][0]["condition_flags"] = 9
        with self.assertRaisesRegex(ValueError, "raw header"):
            self.run_join()

    def test_explicit_condaction_size_must_match_length(self):
        self.data = self.data[:20] + b"\x05\x00" + self.data[22:]
        self.buttons["buttons"][0]["embedded_action_records"][0]["is_last_by_zero_size"] = False
        with self.assertRaisesRegex(ValueError, "CondActionSize"):
            self.run_join()

    def test_final_record_flag_checked_against_source_bytes(self):
        self.buttons["buttons"][0]["embedded_action_records"][0]["is_last_by_zero_size"] = False
        with self.assertRaisesRegex(ValueError, "final-record"):
            self.run_join()

    def test_valid_explicit_size_record(self):
        size = (len(self.payload) + 4).to_bytes(2, "little")
        self.data = self.data[:20] + size + self.data[22:]
        self.buttons["buttons"][0]["embedded_action_records"][0]["is_last_by_zero_size"] = False
        self.assertEqual(self.run_join()["classification_counts"]["bytecode_only_candidate"], 1)

    def test_source_sha_mismatch(self):
        self.crosswalk["source_sha256"] = "c"*64
        with self.assertRaisesRegex(ValueError, "source SHA"):
            self.run_join()

    def test_missing_source_record(self):
        self.lexical["records"][0]["action_offset_uncompressed"] = 22
        with self.assertRaisesRegex(ValueError, "Missing or extra"):
            self.run_join()

    def test_duplicate_source_key(self):
        self.lexical["records"].append(copy.deepcopy(self.lexical["records"][0]))
        self.lexical["audited_button_action_count"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate lexical"):
            self.run_join()

    def test_flags_mismatch(self):
        self.crosswalk["records"][0]["condition_flags"] = 1
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.run_join()

    def test_byte_bounds(self):
        self.buttons["buttons"][0]["embedded_action_records"][0]["action_bytes_including_terminator"] += 100
        self.crosswalk["records"][0]["source_action_byte_length"] += 100
        with self.assertRaisesRegex(ValueError, "outside"):
            self.run_join()

    def test_false_runtime_claim(self):
        self.lexical["records"][0]["runtime_behavior_verified"] = True
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.run_join()

    def test_lexical_total_mismatch(self):
        self.lexical["lexical_function_candidate_total"] = 2
        with self.assertRaisesRegex(ValueError, "total mismatch"):
            self.run_join()

    def test_action_end_mismatch(self):
        self.buttons["buttons"][0]["embedded_action_records"][0]["ends_with_action_end"] = False
        with self.assertRaisesRegex(ValueError, "ActionEnd"):
            self.run_join()


if __name__ == "__main__":
    unittest.main()
