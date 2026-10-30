import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_script_entry_evidence import build_script_entry_evidence


def tag(code, payload, offset, frame=0, timeline="main"):
    header = struct.pack("<H", (code << 6) | (len(payload) if len(payload) < 63 else 63))
    if len(payload) >= 63:
        header += struct.pack("<I", len(payload))
    record = {"timeline": timeline, "frame": frame, "tag_code": code,
              "tag_name": {12: "DoAction", 59: "DoInitAction", 69: "FileAttributes", 82: "DoABC"}.get(code, "DoABCDefine"),
              "offset_uncompressed": offset, "body_offset_uncompressed": offset + len(header),
              "length": len(payload)}
    if code == 59:
        record["init_target_sprite_id"] = 7
    return header + payload, record


def fixture(as3=False, include_abc=False):
    data = bytearray(b"FWS\\x09" + b"\\0" * 4)
    tags = []
    for code, payload, frame in [(69, struct.pack("<I", 8 if as3 else 0), 0),
                                 (12, b"\\x00", 0), (59, b"\\x07\\x00\\x00", 2)] + (
                                 [(82, b"\\x00" * 65, 3)] if include_abc else []):
        raw, record = tag(code, payload, len(data), frame)
        data.extend(raw)
        tags.append(record)
    scripts = [{k: t[k] for k in ("tag_code", "tag_name", "timeline", "frame", "offset_uncompressed", "length")}
               | ({"init_target_sprite_id": 7} if t["tag_code"] == 59 else {})
               for t in tags if t["tag_code"] in (12, 59, 72, 82)]
    return bytes(data), {"source": {"sha256": "f" * 64}, "tags": tags, "scripts": scripts}


class ScriptEntryEvidenceTests(unittest.TestCase):
    def test_legacy_script_counts_and_frames(self):
        data, manifest = fixture()
        report = build_script_entry_evidence(manifest, data)
        self.assertEqual(report["legacy_action_container_count"], 2)
        self.assertEqual(report["abc_container_count"], 0)
        self.assertEqual(report["file_attributes_as3_flag"], False)
        self.assertEqual(report["entries"][1]["frame_one_based"], 3)
        self.assertEqual(report["entries"][1]["init_target_sprite_id"], 7)
        self.assertNotIn("script_body", str(report))

    def test_abc_and_as3_flag(self):
        data, manifest = fixture(True, True)
        report = build_script_entry_evidence(manifest, data)
        self.assertEqual(report["abc_container_count"], 1)
        self.assertEqual(report["file_attributes_as3_flag"], True)
        self.assertEqual(report["script_container_count"], 3)

    def test_missing_attributes_is_unknown_not_false(self):
        data, manifest = fixture()
        manifest["tags"] = [t for t in manifest["tags"] if t["tag_code"] != 69]
        report = build_script_entry_evidence(manifest, data)
        self.assertIsNone(report["file_attributes_as3_flag"])

    def test_tampered_tag_offset_fails(self):
        data, manifest = fixture()
        manifest["tags"][1]["offset_uncompressed"] += 1
        with self.assertRaisesRegex(ValueError, "disagree"):
            build_script_entry_evidence(manifest, data)

    def test_tampered_script_body_fails(self):
        data, manifest = fixture()
        manifest["tags"][1]["body_offset_uncompressed"] += 1
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_script_entry_evidence(manifest, data)

    def test_mismatched_inventory_fails(self):
        data, manifest = fixture()
        manifest["scripts"].pop()
        with self.assertRaisesRegex(ValueError, "disagree"):
            build_script_entry_evidence(manifest, data)

    def test_invalid_file_attributes_length(self):
        data, manifest = fixture()
        manifest["tags"][0]["length"] = 3
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_script_entry_evidence(manifest, data)


if __name__ == "__main__":
    unittest.main()
