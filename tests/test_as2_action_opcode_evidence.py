import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_as2_action_opcode_evidence import _records, classify_trailing_bytes, zero_position_mask, walk_action_tail_candidate, build_action_opcode_evidence


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

    def test_zero_position_mask_has_no_nonzero_byte_values(self):
        self.assertEqual(zero_position_mask(bytes([0, 65, 0, 255]), 4), '0x0x')
        self.assertEqual(zero_position_mask(b'\x3d\x00', 0), '')
        self.assertEqual(zero_position_mask(bytes([0, 1, 0]), 2), 'x0')

    def test_zero_position_mask_invalid_tail_rejected(self):
        for trailing in (-1, 4):
            with self.subTest(trailing=trailing), self.assertRaises(ValueError):
                zero_position_mask(b'abc', trailing)

    def test_length_11_mask_histograms_are_accounted_by_tag(self):
        tail_a = bytes([0, 1, 0, 2, 0, 3, 0, 4, 0, 5, 0])
        tail_b = bytes([0, 8, 0, 7, 0, 6, 0, 5, 0, 4, 0])
        tail_c = bytes([1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6])
        data = bytearray(b'FWS\x09' + bytes(4))
        tags = []
        for code, tail, target in ((12, tail_a, None), (12, tail_b, None), (59, tail_c, 7)):
            body = (b'\x07\x00' if code == 59 else b'') + b'\x3d\x00' + tail
            raw, row = make_tag(code, body, len(data), target=target)
            data.extend(raw)
            tags.append(row)
        scripts = [{k: v for k, v in t.items() if k != 'body_offset_uncompressed'} for t in tags]
        report = build_action_opcode_evidence(
            {'source': {'sha256': 'f' * 64}, 'tags': tags, 'scripts': scripts}, bytes(data))
        self.assertEqual(report['trailing_length_histogram'], {'11': 3})
        self.assertEqual(report['trailing_length_11_zero_position_masks'],
                         {'0x0x0x0x0x0': 2, 'x0x0x0x0x0x': 1})
        self.assertEqual(report['trailing_length_11_zero_count_histogram'], {'5': 1, '6': 2})
        self.assertEqual(report['trailing_length_11_by_tag_code'], {'12': 2, '59': 1})
        self.assertEqual(sum(report['trailing_length_11_zero_position_masks'].values()), 3)

    def test_non_length_11_tails_do_not_enter_mask_histogram(self):
        manifest, data = fixture()
        report = build_action_opcode_evidence(manifest, data)
        self.assertEqual(report['trailing_length_11_zero_position_masks'], {})
        self.assertEqual(report['trailing_length_11_zero_count_histogram'], {})
        self.assertEqual(report['trailing_length_11_by_tag_code'], {})


    def test_secondary_tail_record_walk_classifies_only_structure(self):
        self.assertEqual(walk_action_tail_candidate(b'\x3d\x00', 0), ('none', 0))
        self.assertEqual(walk_action_tail_candidate(b'\x3d\x00\x3d\x00', 2), ('terminated_at_end', 1))
        self.assertEqual(walk_action_tail_candidate(b'\x3d\x00\x00\x7f', 2), ('terminated_with_remainder', 0))
        self.assertEqual(walk_action_tail_candidate(b'\x3d\x00\x3d\x3d', 2), ('no_terminator', 2))
        self.assertEqual(walk_action_tail_candidate(b'\x3d\x00\x96\x04\x00\x01', 4),
                         ('invalid_record_boundary', 0))

    def test_secondary_tail_record_walk_invalid_length_rejected(self):
        for trailing in (-1, 4):
            with self.subTest(trailing=trailing), self.assertRaises(ValueError):
                walk_action_tail_candidate(b'abc', trailing)

    def test_length_11_candidate_walk_histograms_close(self):
        tails = (b'\x3d' * 10 + b'\x00',
                 b'\x00' + b'\x3d' * 10,
                 b'\x3d' * 11,
                 b'\x96\xff\x7f' + bytes(8))
        data = bytearray(b'FWS\x09' + bytes(4))
        tags = []
        for tail in tails:
            raw, row = make_tag(12, b'\x3d\x00' + tail, len(data))
            data.extend(raw)
            tags.append(row)
        scripts = [{k: v for k, v in t.items() if k != 'body_offset_uncompressed'} for t in tags]
        report = build_action_opcode_evidence(
            {'source': {'sha256': 'f' * 64}, 'tags': tags, 'scripts': scripts}, bytes(data))
        self.assertEqual(report['trailing_length_histogram'], {'11': 4})
        self.assertEqual(report['trailing_length_11_candidate_walk_status'], {
            'terminated_at_end': 1, 'terminated_with_remainder': 1,
            'no_terminator': 1, 'invalid_record_boundary': 1})
        self.assertEqual(report['trailing_length_11_candidate_record_count_histogram'],
                         {'0': 1, '10': 1, '11': 1})
        self.assertNotIn('script_body', str(report))

if __name__ == '__main__':
    unittest.main()
