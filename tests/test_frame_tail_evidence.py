import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_frame_tail_evidence import build_frame_tail_evidence
from build_frame_count_audit import build_frame_count_audit
from test_frame_count_audit import fixture, depth_for


class FrameTailEvidenceTests(unittest.TestCase):
    def report(self, m):
        return build_frame_tail_evidence(m, build_frame_count_audit(m, depth_for(m)))

    def test_direct_end_after_show(self):
        m, _ = fixture()
        result = self.report(m)
        self.assertEqual(result["mismatch_count"], 1)
        self.assertEqual(result["tail_class_counts"], {"end_directly_after_show": 1})
        self.assertEqual(result["mismatches"][0]["tags_between_last_show_and_end"], 0)

    def test_pending_script_after_show(self):
        m, _ = fixture()
        m["tags"].insert(4, {"timeline": "sprite:7", "tag_code": 12, "frame": 2,
                              "offset_uncompressed": 45})
        result = self.report(m)
        self.assertEqual(result["tail_class_counts"], {"pending_tags_after_last_show": 1})
        self.assertEqual(result["tail_tag_counts_by_code"], {"12": 1})
        self.assertEqual(result["mismatches"][0]["first_tail_tag_offset_uncompressed"], 45)

    def test_no_show_frame(self):
        m, _ = fixture()
        m["tags"] = [t for t in m["tags"] if t["timeline"] != "sprite:7" or t["tag_code"] != 1]
        m["tags"][1]["frame"] = 0
        for t in m["tags"]:
            if t["timeline"] == "sprite:7" and t["tag_code"] == 0:
                t["frame"] = 0
        result = self.report(m)
        self.assertEqual(result["tail_class_counts"], {"no_show_frame": 1})
        self.assertEqual(result["mismatches"][0]["last_show_frame_offset_uncompressed"], None)

    def test_no_mismatch(self):
        m, _ = fixture()
        m["tags"][0]["sprite_frame_count"] = 2
        self.assertEqual(self.report(m)["mismatch_count"], 0)

    def test_wrong_hash(self):
        m, d = fixture()
        a = build_frame_count_audit(m, d)
        a["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_frame_tail_evidence(m, a)

    def test_tampered_audit_row(self):
        m, d = fixture()
        a = build_frame_count_audit(m, d)
        a["mismatches"][0]["end_tag_offset_uncompressed"] += 1
        with self.assertRaisesRegex(ValueError, "audit row"):
            build_frame_tail_evidence(m, a)

    def test_nonincreasing_offset(self):
        m, d = fixture()
        a = build_frame_count_audit(m, d)
        m["tags"][3]["offset_uncompressed"] = 20
        with self.assertRaisesRegex(ValueError, "Non-increasing"):
            build_frame_tail_evidence(m, a)

    def test_wrong_frame_index(self):
        m, d = fixture()
        a = build_frame_count_audit(m, d)
        m["tags"][3]["frame"] = 0
        with self.assertRaisesRegex(ValueError, "frame index"):
            build_frame_tail_evidence(m, a)

    def test_unexpected_end_position(self):
        m, d = fixture()
        a = build_frame_count_audit(m, d)
        m["tags"].insert(5, {"timeline": "sprite:7", "tag_code": 12, "frame": 2,
                              "offset_uncompressed": 55})
        with self.assertRaisesRegex(ValueError, "End tag is not last"):
            build_frame_tail_evidence(m, a)

    def test_duplicate_mismatch_row(self):
        m, d = fixture()
        a = build_frame_count_audit(m, d)
        a["mismatches"].append(copy.deepcopy(a["mismatches"][0]))
        a["mismatch_count"] += 1
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_frame_tail_evidence(m, a)

    def test_no_original_payload(self):
        m, _ = fixture()
        result = self.report(m)
        self.assertNotIn("payload", str(result["mismatches"]))
        self.assertNotIn("script_body", str(result))


if __name__ == "__main__":
    unittest.main()
