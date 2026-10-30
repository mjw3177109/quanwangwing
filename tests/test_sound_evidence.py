import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_sound_evidence import build_sound_evidence
from swf_inventory import inventory, load_swf
from test_swf_inventory import fixture, tag


def sound_fixture(extra=b""):
    prefix = fixture()[:21]
    sound = tag(14, struct.pack("<HB I", 7, 0x2F, 4000) + b"MP3")
    start = tag(15, struct.pack("<HB", 7, 0))
    stream_head = tag(45, b"\x00\x2f\x40\x00")
    stream_block = tag(19, b"\x01\x02")
    button = tag(17, struct.pack("<HHBHHH", 5, 7, 0, 0, 0, 0))
    start2 = tag(89, b"SoundClass\x00\x00")
    raw = prefix + sound + start + stream_head + stream_block + button + start2 + extra + tag(1) + tag(0)
    return raw[:4] + struct.pack("<I", len(raw)) + raw[8:]


def analyze(raw):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "test.swf"
        path.write_bytes(raw)
        manifest = inventory(path)
        data, _ = load_swf(path)
        return build_sound_evidence(manifest, data)


class SoundEvidenceTests(unittest.TestCase):
    def test_sound_metadata_and_stream_references(self):
        report = analyze(sound_fixture())
        self.assertEqual(report["define_sound_count"], 1)
        self.assertEqual(report["start_sound_count"], 1)
        self.assertEqual(report["button_sound_transition_count"], 1)
        self.assertEqual(report["stream_head_count"], 1)
        self.assertEqual(report["stream_block_count"], 1)
        self.assertEqual(report["start_sound2_count"], 1)
        self.assertEqual(report["definitions"][0]["sample_count"], 4000)
        self.assertEqual(report["stream_blocks"][0]["stream_head_index"], 0)
        self.assertEqual(report["unresolved_sound_ids"], [])
        self.assertNotIn("MP3", json.dumps(report))

    def test_missing_sound_definition_remains_unresolved(self):
        report = analyze(sound_fixture(tag(15, struct.pack("<HB", 8, 0))))
        self.assertEqual(report["unresolved_sound_ids"], [8])

    def test_truncated_define_sound_rejected(self):
        with self.assertRaisesRegex(ValueError, "Truncated DefineSound"):
            analyze(sound_fixture(tag(14, b"\x01\x00")))

    def test_truncated_sound_info_rejected(self):
        with self.assertRaisesRegex(ValueError, "Truncated SOUNDINFO"):
            analyze(sound_fixture(tag(15, struct.pack("<HB", 7, 0x01))))

    def test_sound_tag_offset_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.swf"
            path.write_bytes(sound_fixture())
            manifest = inventory(path)
            data, _ = load_swf(path)
            next(t for t in manifest["tags"] if t["tag_code"] == 14)["length"] += 1
            with self.assertRaisesRegex(ValueError, "Manifest tag does not match"):
                build_sound_evidence(manifest, data)

    def test_sound_info_envelope_length_checked(self):
        with self.assertRaisesRegex(ValueError, "Truncated SOUNDINFO envelope"):
            analyze(sound_fixture(tag(15, struct.pack("<HB", 7, 0x08) + b"\x01")))

    def test_sync_stop_flag_has_no_optional_payload(self):
        report = analyze(sound_fixture(tag(15, struct.pack("<HB", 7, 0x20))))
        self.assertEqual(report["start_sound_count"], 2)

    def test_soundinfo_optional_fields_have_correct_bit_positions(self):
        info = bytes([0x0F]) + b"\x00" * 4 + b"\x00" * 4 + b"\x02\x00" + b"\x01" + b"\x00" * 8
        report = analyze(sound_fixture(tag(15, struct.pack("<H", 7) + info)))
        self.assertEqual(report["start_sound_count"], 2)

    def test_stream_block_without_header_reported(self):
        report = analyze(sound_fixture(tag(39, struct.pack("<HH", 9, 1) + tag(19, b"\x00") + tag(1) + tag(0))))
        self.assertEqual(report["stream_blocks_without_head"], 1)


if __name__ == "__main__":
    unittest.main()
