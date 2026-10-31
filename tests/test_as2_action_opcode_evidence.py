import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_as2_action_opcode_evidence import _records, classify_trailing_bytes, build_action_opcode_evidence


def make_tag(code, body, offset, frame=0, target=None):
    header = struct.pack('<H', (code << 6) | (len(body) if len(body) < 63 else 63))
    if len(body) >= 63:
        header += struct.pack('<I', len(body))
    row = {"tag_code": code, "tag_name": "DoAction" if code == 12 else "DoInitAction",
           "timeline": "main", "frame": frame, "offset_uncompressed": offset,
           "body_offset_uncompressed": offset + len(header), "length": len(body)}
    if target is not None:
        row["init_target_sprite_id"] = target
    return header + body, row


def fixture():
    data = bytearray(b'FWS\x09' + b'\0' * 4)
    tags = []
    for code, body, frame, target in [(12, b'\x96\x02\x00\x01\x02\x3d\x00', 0, None),
                                      (59, b'\x07\x00\x9b\x00\x00\x00', 2, 7)]:
        raw, row = make_tag(code, body, len(data), frame, target)
        data.extend(raw)
        tags.append(row)
    scripts = [{k: v for k, v in t.items() if k != 'body_offset_uncompressed'} for t in tags]
    return {"source": {"sha256": "f" * 64}, "tags": tags, "scripts": scripts}, bytes(data)


class OpcodeTests(unittest.TestCase):
    def test_verified_records_and_counts(self):
        m, data = fixture()
        r = build_action_opcode_evidence(m, data)
        self.assertEqual(r['legacy_container_count'], 2)
        self.assertEqual(r['action_record_count_top_level'], 3)
        self.assertEqual(r['function_record_count_top_level'], 1)
        self.assertEqual(r['containers_with_action_end'], 2)
        self.assertEqual(r['interesting_opcode_counts']['CallFunction'], 1)
        self.assertNotIn('script_body', str(r))

    def test_tail_classes_do_not_interpret_payload(self):
        self.assertEqual(classify_trailing_bytes(bytes.fromhex('3d00'), 0), 'none')
        self.assertEqual(classify_trailing_bytes(bytes.fromhex('3d000000'), 2), 'zero_only')
        self.assertEqual(classify_trailing_bytes(bytes.fromhex('3d000102'), 2), 'nonzero_only')
        self.assertEqual(classify_trailing_bytes(bytes.fromhex('3d000100'), 2), 'mixed')

    def test_tail_class_invalid_length_fails_closed(self):
        for length in (-1, 9):
            with self.subTest(length=length), self.assertRaises(ValueError):
                classify_trailing_bytes(b'abc', length)

    def test_tail_report_accounts_for_all_containers(self):
        m, data = fixture()
        r = build_action_opcode_evidence(m, data)
        self.assertEqual(r['trailing_class_counts']['none'], 2)
        self.assertEqual(sum(r['trailing_class_counts'].values()), r['legacy_container_count'])
        self.assertEqual(r['trailing_bytes_total'], 0)
        self.assertEqual(sum(r['trailing_bytes_by_class'].values()), 0)
        self.assertEqual(r['trailing_length_histogram'], {})

    def test_zero_and_mixed_tail_report(self):
        data = bytearray(bytes.fromhex('46575309') + bytes(4))
        tags = []
        for code, body, target in ((12, bytes.fromhex('3d000000'), None),
                                   (59, bytes.fromhex('07003d000100'), 7)):
            raw, row = make_tag(code, body, len(data), target=target)
            data.extend(raw)
            tags.append(row)
        scripts = [{k: v for k, v in t.items() if k != 'body_offset_uncompressed'} for t in tags]
        manifest = {'source': {'sha256': 'f' * 64}, 'tags': tags, 'scripts': scripts}
        r = build_action_opcode_evidence(manifest, bytes(data))
        self.assertEqual(r['trailing_class_counts']['zero_only'], 1)
        self.assertEqual(r['trailing_class_counts']['mixed'], 1)
        self.assertEqual(r['trailing_bytes_total'], 4)
        self.assertEqual(r['trailing_length_histogram'], {'2': 2})
        self.assertEqual([e['trailing_bytes_class'] for e in r['entries']], ['zero_only', 'mixed'])
        self.assertNotIn('script_body', str(r))

    def test_truncated_long_action_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            _records(b'\x96\x02')

    def test_long_action_out_of_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            _records(b'\x96\x04\x00\x01')

    def test_trailing_bytes_recorded_without_interpreting(self):
        counts, terminated, trailing = _records(b'\x3d\x00\x12\x13')
        self.assertEqual(counts[0x3d], 1)
        self.assertTrue(terminated)
        self.assertEqual(trailing, 2)

    def test_missing_action_end_is_explicit(self):
        counts, terminated, trailing = _records(b'\x3d')
        self.assertEqual((terminated, trailing), (False, 0))

    def test_mismatched_tag_offset_rejected(self):
        m, data = fixture()
        m['tags'][0]['offset_uncompressed'] += 1
        with self.assertRaises(ValueError): build_action_opcode_evidence(m, data)

    def test_mismatched_script_frame_rejected(self):
        m, data = fixture()
        m['scripts'][0]['frame'] = 5
        with self.assertRaises(ValueError): build_action_opcode_evidence(m, data)

    def test_mismatched_init_target_rejected(self):
        m, data = fixture()
        m['tags'][1]['init_target_sprite_id'] = 9
        with self.assertRaises(ValueError): build_action_opcode_evidence(m, data)

    def test_missing_legacy_script_rejected(self):
        m, data = fixture()
        m['scripts'].pop()
        with self.assertRaises(ValueError): build_action_opcode_evidence(m, data)

    def test_nested_function_payload_not_miscounted(self):
        counts, terminated, trailing = _records(b'\x9b\x02\x00\x3d\x3d\x00')
        self.assertEqual(counts[0x9b], 1)
        self.assertEqual(counts[0x3d], 0)
        self.assertTrue(terminated)


if __name__ == '__main__':
    unittest.main()
