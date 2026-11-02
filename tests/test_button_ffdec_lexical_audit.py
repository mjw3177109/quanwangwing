import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_button_ffdec_lexical_audit import audit_button_lexical_exports


class ButtonFFDecLexicalAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = "scripts/DefineButton2_693/BUTTONCONDACTION on(release).as"
        self.script = self.root / self.path
        self.script.parent.mkdir(parents=True)
        self.content = b'function act() { if (ok) return 1; } // function decoy() {}\nvar s="if return";'
        self.script.write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.crosswalk = {
            "source_sha256": "a" * 64, "matched_export_count": 1,
            "source_action_record_count": 1, "decompiled_semantics_verified": False,
            "runtime_behavior_verified": False,
            "records": [{"button_character_id": 693, "action_offset_uncompressed": 123,
                         "ffdec_export_path": self.path, "ffdec_event_label": "release",
                         "condition_flags": 8, "ffdec_export_size_bytes": len(self.content),
                         "ffdec_export_sha256": self.digest, "decompiled_semantics_verified": False,
                         "runtime_behavior_verified": False}],
        }
        self.index = {"source_sha256": "a" * 64, "script_count": 1,
                      "total_bytes": len(self.content), "files": [
                          {"path": self.path, "size_bytes": len(self.content), "sha256": self.digest}]}

    def audit(self):
        return audit_button_lexical_exports(self.root, self.crosswalk, self.index)

    def test_masked_source_counts_and_priority(self):
        result = self.audit()
        self.assertEqual(result["audited_button_action_count"], 1)
        self.assertEqual(result["priority_review_count"], 1)
        self.assertEqual(result["lexical_matched_function_scope_total"], 1)
        self.assertEqual(result["lexical_unmatched_function_candidate_total"], 0)
        self.assertEqual(result["lexical_branch_keyword_totals"]["if"], 1)
        self.assertEqual(result["lexical_branch_keyword_totals"]["return"], 1)
        self.assertEqual(result["records"][0]["lexical_branch_keyword_line_numbers"],
                         {"if": [1], "return": [1]})
        self.assertEqual(result["records"][0]["lexical_branch_keyword_scope_counts"], {
            "if": {"inside_recognized_function": 1, "outside_recognized_function": 0},
            "return": {"inside_recognized_function": 1, "outside_recognized_function": 0},
        })
        self.assertNotIn("function act", str(result))
        self.assertFalse(result["decompiled_semantics_verified"])

    def test_branch_line_locations_mask_strings_and_preserve_same_line_hits(self):
        self.content = (b'if (x) return 1; if (y) return 2;\n'
                        b'var s="if return"; // if return\n'
                        b'if (z) { return 3; }\n')
        self.script.write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.crosswalk["records"][0].update(ffdec_export_sha256=self.digest,
                                             ffdec_export_size_bytes=len(self.content))
        self.index["files"][0].update(sha256=self.digest, size_bytes=len(self.content))
        self.index["total_bytes"] = len(self.content)
        row = self.audit()["records"][0]
        self.assertEqual(row["lexical_branch_keyword_counts"]["if"], 3)
        self.assertEqual(row["lexical_branch_keyword_line_numbers"]["if"], [1, 1, 3])
        self.assertEqual(row["lexical_branch_keyword_line_numbers"]["return"], [1, 1, 3])

    def test_branch_scope_attribution_uses_token_offsets(self):
        self.content = (b'if (outside) return 0; function outer() { if (inside) '
                        b'{ function inner() { return 1; } return 2; } } '
                        b'return 3;')
        self.script.write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.crosswalk["records"][0].update(ffdec_export_sha256=self.digest,
                                             ffdec_export_size_bytes=len(self.content))
        self.index["files"][0].update(sha256=self.digest, size_bytes=len(self.content))
        self.index["total_bytes"] = len(self.content)
        row = self.audit()["records"][0]
        self.assertEqual(row["lexical_branch_keyword_scope_counts"], {
            "if": {"inside_recognized_function": 1, "outside_recognized_function": 1},
            "return": {"inside_recognized_function": 2, "outside_recognized_function": 2},
        })

    def test_source_mismatch_fails_closed(self):
        self.index["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "Source SHA"):
            self.audit()

    def test_tampered_file_fails_closed(self):
        self.script.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "hash or size"):
            self.audit()

    def test_tampered_crosswalk_digest_fails_closed(self):
        self.crosswalk["records"][0]["ffdec_export_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "hash or size"):
            self.audit()

    def test_duplicate_crosswalk_fails_closed(self):
        self.crosswalk["records"].append(copy.deepcopy(self.crosswalk["records"][0]))
        self.crosswalk["matched_export_count"] += 1
        self.crosswalk["source_action_record_count"] += 1
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.audit()

    def test_unverified_runtime_claim_fails_closed(self):
        self.crosswalk["records"][0]["runtime_behavior_verified"] = True
        with self.assertRaisesRegex(ValueError, "verification claim"):
            self.audit()

    def test_unmatched_function_candidate_is_not_accepted_scope(self):
        self.content = b"function broken() { if (x) return 1;"
        self.script.write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.crosswalk["records"][0].update(ffdec_export_sha256=self.digest,
                                               ffdec_export_size_bytes=len(self.content))
        self.index["files"][0].update(sha256=self.digest, size_bytes=len(self.content))
        self.index["total_bytes"] = len(self.content)
        result = self.audit()
        self.assertEqual(result["lexical_matched_function_scope_total"], 0)
        self.assertEqual(result["lexical_unmatched_function_candidate_total"], 1)

    def test_wrong_event_flag_fails_closed(self):
        self.crosswalk["records"][0]["condition_flags"] = 1
        with self.assertRaisesRegex(ValueError, "mapping"):
            self.audit()

    def test_extra_indexed_button_export_fails_closed(self):
        self.index["files"].append({"path": "scripts/DefineButton2_999/BUTTONCONDACTION on(release).as",
                                    "size_bytes": 0, "sha256": "b" * 64})
        self.index["script_count"] += 1
        with self.assertRaisesRegex(ValueError, "extra button export"):
            self.audit()

    def test_path_escape_fails_closed(self):
        self.crosswalk["records"][0]["ffdec_export_path"] = "scripts/../secret.as"
        with self.assertRaisesRegex(ValueError, "mapping"):
            self.audit()


if __name__ == "__main__":
    unittest.main()
