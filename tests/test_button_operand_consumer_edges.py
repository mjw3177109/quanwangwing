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

    def test_reject_forged_in_bounds_branch_target(self):
        # Source ActionIf displacement is zero (target 10), not the reported 11.
        body = b'\x96\x02\x00\x05\x01\x9d\x02\x00\x00\x00\x00'
        branch = [{'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 11,
                   'target_classification': 'body_end'}]
        with self.assertRaisesRegex(ValueError, 'does not match source'):
            trace_body(body, 0, [], branch)

    def test_reject_nonstandard_actionif_payload_length(self):
        body = b'\x96\x02\x00\x05\x01\x9d\x03\x00\x00\x00\x00\x00'
        branch = [{'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 11,
                   'target_classification': 'record_start'}]
        with self.assertRaisesRegex(ValueError, 'payload length'):
            trace_body(body, 0, [], branch)

    def test_signed_backward_branch_is_verified(self):
        body = b'\x96\x02\x00\x05\x01\x9d\x02\x00\xf6\xff\x00'
        branch = [{'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 0,
                   'target_classification': 'record_start'}]
        result = trace_body(body, 0, [], branch)
        self.assertEqual(result['candidate_consumer_edges'][0]['operand_role'], 'condition')

    def test_reject_forged_record_start_at_body_end(self):
        body = b'\x96\x02\x00\x05\x01\x9d\x02\x00\x01\x00\x00'
        branch = [{'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 11,
                   'target_classification': 'record_start'}]
        with self.assertRaisesRegex(ValueError, 'classification does not match'):
            trace_body(body, 0, [], branch)

    def test_reject_forged_body_end_at_record_start(self):
        body = b'\x96\x02\x00\x05\x01\x9d\x02\x00\x00\x00\x00'
        branch = [{'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 10,
                   'target_classification': 'body_end'}]
        with self.assertRaisesRegex(ValueError, 'classification does not match'):
            trace_body(body, 0, [], branch)

    def test_accept_verified_body_end_branch(self):
        body = b'\x96\x02\x00\x05\x01\x9d\x02\x00\x01\x00\x00'
        branch = [{'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 11,
                   'target_classification': 'body_end'}]
        result = trace_body(body, 0, [], branch)
        self.assertEqual(result['candidate_consumer_edges'][0]['operand_role'], 'condition')

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
        branches = {'source_sha256': sha, 'branch_record_count': 0, 'records': []}
        r = build_consumer_map(join, origins, branches, b'\x00', sha)
        self.assertIsNone(r['records'][0]['candidate_consumer_edges'])
        self.assertEqual(r['complete_function_count'], 0)

    def test_cross_report_sha_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            build_consumer_map({'source_sha256': 'x'}, {'source_sha256': 'y'},
                               {'source_sha256': 'x'}, b'', 'x')


    def test_reject_branch_report_count_mismatch(self):
        sha = 'a' * 64
        join = {'source_sha256': sha, 'records': []}
        origins = {'source_sha256': sha, 'function_body_count': 0, 'records': []}
        branches = {'source_sha256': sha, 'branch_record_count': 1, 'records': []}
        with self.assertRaisesRegex(ValueError, 'Branch report count mismatch'):
            build_consumer_map(join, origins, branches, b'', sha)

    def test_reject_orphan_branch_provenance(self):
        sha = 'a' * 64
        join = {'source_sha256': sha, 'records': []}
        origins = {'source_sha256': sha, 'function_body_count': 0, 'records': []}
        row = {'button_character_id': 693, 'function_body_start_uncompressed': 0,
               'branch_offset_uncompressed': 0, 'branch_opcode': '0x9d',
               'execution_verified': False}
        branches = {'source_sha256': sha, 'branch_record_count': 1, 'records': [row]}
        with self.assertRaisesRegex(ValueError, 'Orphan branch provenance'):
            build_consumer_map(join, origins, branches, b'', sha)

    def test_reject_duplicate_branch_provenance(self):
        sha = 'a' * 64
        join = {'source_sha256': sha, 'records': []}
        origins = {'source_sha256': sha, 'function_body_count': 0, 'records': []}
        row = {'button_character_id': 693, 'function_body_start_uncompressed': 0,
               'branch_offset_uncompressed': 0, 'branch_opcode': '0x9d',
               'execution_verified': False}
        branches = {'source_sha256': sha, 'branch_record_count': 2,
                    'records': [row, dict(row)]}
        with self.assertRaisesRegex(ValueError, 'Duplicate branch provenance'):
            build_consumer_map(join, origins, branches, b'', sha)

    def test_reject_forged_branch_opcode(self):
        body = b'\x96\x02\x00\x05\x01\x9d\x02\x00\x00\x00\x00'
        row = {'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 10,
               'target_classification': 'record_start', 'branch_opcode': '0x99',
               'execution_verified': False}
        with self.assertRaisesRegex(ValueError, 'Branch opcode does not match'):
            trace_body(body, 0, [], [row])

    def test_reject_unsupported_branch_execution_claim(self):
        body = b'\x96\x02\x00\x05\x01\x9d\x02\x00\x00\x00\x00'
        row = {'branch_offset_uncompressed': 5, 'target_offset_uncompressed': 10,
               'target_classification': 'record_start', 'branch_opcode': '0x9d',
               'execution_verified': True}
        with self.assertRaisesRegex(ValueError, 'Unsupported branch execution'):
            trace_body(body, 0, [], [row])


if __name__ == '__main__':
    unittest.main()
