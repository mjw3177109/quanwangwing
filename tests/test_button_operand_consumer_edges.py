import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_button_operand_consumer_edges import trace_body, build_consumer_map


class ConsumerEdgesTests(unittest.TestCase):
    def test_direct_string_getvariable_provenance(self):
        body = b'\x96\x03\x00\x00x\x00\x1c\x00'
        locs = [{'push_record_offset_uncompressed': 100, 'push_element_index': 0, 'class_label': 'S1'}]
        r = trace_body(body, 100, locs, [])
        self.assertEqual(r['candidate_consumer_edges'], [{
            'consumer_offset_uncompressed': 106, 'consumer_opcode': 'GetVariable',
            'operand_role': 'variable_name', 'producer_type': 'literal_string',
            'producer_record_offset_uncompressed': 100, 'producer_element_index': 0,
            'producer_class_label': 'S1'}])
        self.assertNotIn('"x"', json.dumps(r))

    def test_setvariable_value_and_name_stack_order(self):
        body = b'\x96\x08\x00\x00x\x00\x07\x01\x00\x00\x00\x1d\x00'
        locs = [{'push_record_offset_uncompressed': 0, 'push_element_index': 0, 'class_label': 'S1'}]
        r = trace_body(body, 0, locs, [])
        self.assertEqual(len(r['candidate_consumer_edges']), 2)
        roles = {x['operand_role']: x for x in r['candidate_consumer_edges']}
        self.assertEqual(roles['variable_name']['producer_class_label'], 'S1')
        self.assertEqual(roles['variable_value']['producer_type'], 'literal_integer')

    def test_if_candidate_tracks_variable_read_not_literal(self):
        body = b'\x96\x03\x00\x00x\x00\x1c\x9d\x02\x00\x00\x00\x00'
        locs = [{'push_record_offset_uncompressed': 0, 'push_element_index': 0, 'class_label': 'S1'}]
        branch = [{'branch_offset_uncompressed': 7, 'target_offset_uncompressed': 12,
                   'target_classification': 'record_start'}]
        r = trace_body(body, 0, locs, branch)
        ifedge = next(x for x in r['candidate_consumer_edges'] if x['operand_role'] == 'condition')
        self.assertEqual(ifedge['producer_type'], 'variable_read_result')
        self.assertEqual(ifedge['producer_record_offset_uncompressed'], 6)
        self.assertIsNone(ifedge['producer_class_label'])

    def test_mixed_push_element_index(self):
        body = b'\x96\x08\x00\x05\x01\x00x\x00\x00y\x00\x1d\x00'
        locs = [{'push_record_offset_uncompressed': 0, 'push_element_index': 1, 'class_label': 'S1'},
                {'push_record_offset_uncompressed': 0, 'push_element_index': 2, 'class_label': 'S2'}]
        r = trace_body(body, 0, locs, [])
        name = next(x for x in r['candidate_consumer_edges'] if x['operand_role'] == 'variable_name')
        self.assertEqual(name['producer_element_index'], 1)

    def test_reject_missing_verified_branch(self):
        with self.assertRaisesRegex(ValueError, 'Missing or extra verified branch'):
            trace_body(b'\x9d\x02\x00\x00\x00\x00', 0, [], [])

    def test_reject_tampered_string_locations(self):
        with self.assertRaisesRegex(ValueError, 'Missing verified string location'):
            trace_body(b'\x96\x03\x00\x00x\x00\x00', 0, [], [])

    def test_reject_candidate_underflow(self):
        with self.assertRaisesRegex(ValueError, 'underflow'):
            trace_body(b'\x1c\x00', 0, [], [])

    def test_reject_analysis_limit(self):
        with self.assertRaisesRegex(ValueError, 'limit reached'):
            trace_body(b'\x96\x02\x00\x05\x01\x00', 0, [], [], max_states=1)

    def test_incomplete_origin_withholds_edges(self):
        sha = 'a' * 64
        join = {'source_sha256': sha, 'records': [{'button_character_id': 693,
                'bytecode_function_body_ranges': [{'body_start_uncompressed': 0,
                                                   'body_end_uncompressed': 1}]}]}
        origins = {'source_sha256': sha, 'function_body_count': 1,
                   'records': [{'button_character_id': 693, 'function_body_start_uncompressed': 0,
                                'origin_status': 'source_stack_unresolved',
                                'literal_string_locations': None}]}
        branches = {'source_sha256': sha, 'records': []}
        r = build_consumer_map(join, origins, branches, b'\x00', sha)
        self.assertIsNone(r['records'][0]['candidate_consumer_edges'])
        self.assertEqual(r['complete_function_count'], 0)

    def test_cross_report_sha_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            build_consumer_map({'source_sha256': 'x'}, {'source_sha256': 'y'},
                               {'source_sha256': 'x'}, b'', 'x')


if __name__ == '__main__':
    unittest.main()
