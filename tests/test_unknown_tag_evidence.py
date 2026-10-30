import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_unknown_tag_evidence import build_unknown_tag_evidence
from swf_inventory import inventory
from test_swf_inventory import fixture, tag


def unknown_fixture(compressed=False):
    prefix = fixture()[:21]
    sprite = struct.pack("<HH", 7, 1) + tag(253, b"\x01\x02") + tag(1) + tag(0)
    body = (tag(39, sprite) + tag(253, b"\x01\x02") +
            tag(253, b"\x01\x02") + tag(255, b"\xff" * 80) + tag(1) + tag(0))
    fws = prefix[:4] + struct.pack("<I", len(prefix) + len(body)) + prefix[8:] + body
    if compressed:
        return b"CWS" + fws[3:8] + zlib.compress(fws[8:])
    return fws


class UnknownTagEvidenceTests(unittest.TestCase):
    def test_hashes_lengths_nested_timeline_and_long_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            for compressed in (False, True):
                path = Path(tmp) / "unknown.swf"
                path.write_bytes(unknown_fixture(compressed))
                result = build_unknown_tag_evidence(path, inventory(path))
                self.assertEqual(result["verified_occurrence_count"], 4)
                self.assertEqual(result["summary_by_code"]["253"]["count"], 3)
                self.assertEqual(result["summary_by_code"]["253"]["unique_payload_hashes"], 1)
                self.assertEqual(result["summary_by_code"]["253"]["repeated_payload_occurrences"], 3)
                self.assertEqual(result["summary_by_code"]["255"]["length_counts"], {"80": 1})
                sprite_event = next(x for x in result["occurrences"] if x["timeline"] == "sprite:7")
                self.assertEqual(sprite_event["next_tag_code_same_timeline"], 1)
                self.assertNotIn("payload_bytes", json.dumps(result))

    def test_wrong_source_and_tampered_manifest_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unknown.swf"
            path.write_bytes(unknown_fixture())
            manifest = inventory(path)
            manifest["source"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                build_unknown_tag_evidence(path, manifest)
            manifest = inventory(path)
            unknown = next(t for t in manifest["tags"] if t["tag_code"] == 253)
            unknown["length"] += 1
            with self.assertRaisesRegex(ValueError, "header/manifest mismatch"):
                build_unknown_tag_evidence(path, manifest)

    def test_unknown_count_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unknown.swf"
            path.write_bytes(unknown_fixture())
            manifest = inventory(path)
            manifest["tag_counts_by_code"]["253"] += 1
            with self.assertRaisesRegex(ValueError, "count mismatch"):
                build_unknown_tag_evidence(path, manifest)

    @unittest.skipUnless((ROOT / "拳皇wing1.4.swf").is_file(), "original SWF not present")
    def test_original_unknown_tag_counts(self):
        path = ROOT / "拳皇wing1.4.swf"
        result = build_unknown_tag_evidence(path, inventory(path))
        self.assertEqual(result["summary_by_code"]["253"]["count"], 2729)
        self.assertEqual(result["summary_by_code"]["255"]["count"], 1)
        self.assertEqual(result["verified_occurrence_count"], 2730)


if __name__ == "__main__":
    unittest.main()
