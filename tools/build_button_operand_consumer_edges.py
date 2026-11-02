#!/usr/bin/env python3
"""Metadata-only source-backed ActionPush -> operand consumer candidate edges."""
from __future__ import annotations
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path

PUSH_TYPES = {0: 'literal_string', 1: 'literal_float', 2: 'literal_null',
              3: 'literal_undefined', 4: 'literal_register', 5: 'literal_boolean',
              6: 'literal_double', 7: 'literal_integer', 8: 'literal_constant8',
              9: 'literal_constant16'}
PUSH_WIDTHS = {1: 4, 2: 0, 3: 0, 4: 1, 5: 1, 6: 8, 7: 4, 8: 1, 9: 2}
OPCODES = {0x1C: 'GetVariable', 0x1D: 'SetVariable', 0x9D: 'ActionIf'}


def _records(body):
    """Parse top-level ActionRecords; never decode literal values."""
    records = []
    pos = 0
    while pos < len(body):
        opcode = body[pos]
        if opcode >= 0x80:
            if pos + 3 > len(body):
                raise ValueError('Truncated ActionRecord header')
            end = pos + 3 + int.from_bytes(body[pos + 1:pos + 3], 'little')
        else:
            end = pos + 1
        if end > len(body):
            raise ValueError('ActionRecord extends beyond function body')
        records.append((pos, end, opcode))
        pos = end
    return records


def _push_sources(payload, record_abs, labels):
    sources = []
    pos = index = 0
    while pos < len(payload):
        kind = payload[pos]
        pos += 1
        if kind not in PUSH_TYPES:
            raise ValueError('Unknown ActionPush element type')
        if kind == 0:
            end = payload.find(b'\x00', pos)
            if end < 0:
                raise ValueError('Unterminated ActionPush string')
            pos = end + 1
            label = labels.get((record_abs, index))
            if label is None:
                raise ValueError('Missing verified string location')
        else:
            width = PUSH_WIDTHS[kind]
            if pos + width > len(payload):
                raise ValueError('Truncated ActionPush element')
            pos += width
            label = None
        sources.append((PUSH_TYPES[kind], record_abs, index, label))
        index += 1
    return sources


def trace_body(body, start, locations, branches, max_states=4096, max_depth=128):
    """Trace producer candidates through both edges of source-verified ActionIf."""
    if any(type(x) is not int or x < 1 for x in (max_states, max_depth)):
        raise ValueError('Positive integer analysis limits required')
    labels = {}
    for loc in locations:
        key = (loc['push_record_offset_uncompressed'], loc['push_element_index'])
        label = loc['class_label']
        if (type(key[0]) is not int or type(key[1]) is not int or key[1] < 0
                or not isinstance(label, str) or not label.startswith('S') or key in labels):
            raise ValueError('Invalid or duplicate string location')
        labels[key] = label
    records = _records(body)
    by_offset = {r[0]: r for r in records}
    boundaries = set(by_offset) | {len(body)}
    branch_targets = {}
    for row in branches:
        offset = row['branch_offset_uncompressed'] - start
        target = row['target_offset_uncompressed'] - start
        if (offset in branch_targets or offset not in by_offset
                or by_offset[offset][2] not in (0x99, 0x9D)
                or row['target_classification'] not in ('record_start', 'body_end')
                or target not in boundaries):
            raise ValueError('Invalid source-backed branch target')
        # Verify the branch's encoded signed SWF displacement, not just the
        # report's claimed target and its ActionRecord boundary.
        _, record_end, _ = by_offset[offset]
        if record_end - offset != 5:
            raise ValueError('Invalid ActionBranch payload length')
        encoded_target = record_end + int.from_bytes(
            body[offset + 3:record_end], 'little', signed=True)
        if target != encoded_target:
            raise ValueError('Branch target does not match source ActionRecord displacement')
        # Verify the report's boundary class against the original function bytes.
        expected_class = 'body_end' if target == len(body) else 'record_start'
        if row['target_classification'] != expected_class:
            raise ValueError('Branch target classification does not match source boundary')
        branch_targets[offset] = target
    if set(branch_targets) != {pos for pos, _, op in records if op in (0x99, 0x9D)}:
        raise ValueError('Missing or extra verified branch')
    pending = deque([(records[0][0], ())] if records else [])
    seen = set()
    edges = set()
    used_labels = set()
    while pending:
        pos, stack = pending.popleft()
        if pos == len(body) or (pos, stack) in seen:
            continue
        if pos not in by_offset:
            raise ValueError('Candidate edge not on ActionRecord boundary')
        if len(seen) >= max_states or len(stack) > max_depth:
            raise ValueError('Consumer provenance analysis limit reached')
        seen.add((pos, stack))
        _, end, op = by_offset[pos]
        next_stack = list(stack)
        if op == 0x96:
            items = _push_sources(body[pos + 3:end], start + pos, labels)
            used_labels.update((x[1], x[2]) for x in items if x[0] == 'literal_string')
            next_stack.extend(items)
        else:
            pops = {0x00: 0, 0x0C: 2, 0x1C: 1, 0x1D: 2,
                    0x3E: 1, 0x3F: 2, 0x99: 0, 0x9D: 1}.get(op)
            if pops is None:
                raise ValueError('Unmodeled source opcode')
            if len(next_stack) < pops:
                raise ValueError('Candidate stack underflow')
            popped = [next_stack.pop() for _ in range(pops)]
            roles = {0x1C: ('variable_name',), 0x1D: ('variable_value', 'variable_name'),
                     0x9D: ('condition',)}.get(op, ())
            for role, producer in zip(roles, popped):
                edges.add((start + pos, OPCODES[op], role, *producer))
            if op == 0x1C:
                next_stack.append(('variable_read_result', start + pos, None, None))
            elif op in (0x0C, 0x3F):
                next_stack.append(('arithmetic_result', start + pos, None, None))
        if len(next_stack) > max_depth:
            raise ValueError('Consumer provenance analysis limit reached')
        if op in (0x00, 0x3E):
            targets = ()
        elif op == 0x99:
            targets = (branch_targets[pos],)
        elif op == 0x9D:
            targets = (branch_targets[pos], end)
        else:
            targets = (end,)
        pending.extend((target, tuple(next_stack)) for target in targets)
    static_labels = set()
    for pos, end, op in records:
        if op == 0x96:
            for x in _push_sources(body[pos + 3:end], start + pos, labels):
                if x[0] == 'literal_string':
                    static_labels.add((x[1], x[2]))
    if static_labels != set(labels):
        raise ValueError('String location coverage mismatch')
    result = [dict(consumer_offset_uncompressed=e[0], consumer_opcode=e[1],
                   operand_role=e[2], producer_type=e[3],
                   producer_record_offset_uncompressed=e[4],
                   producer_element_index=e[5], producer_class_label=e[6])
              for e in sorted(edges, key=lambda x: (x[0], x[2], x[4], -1 if x[5] is None else x[5]))]
    return {'candidate_consumer_edges': result,
            'explored_candidate_state_count': len(seen),
            'reachable_string_location_count': len(used_labels),
            'static_string_location_count': len(static_labels)}


def build_consumer_map(join, origins, branch_audit, decompressed, source_sha256):
    if any(d.get('source_sha256') != source_sha256 for d in (join, origins, branch_audit)):
        raise ValueError('Cross-report SWF SHA mismatch')
    origin_index = {}
    for row in origins['records']:
        key = (row['button_character_id'], row['function_body_start_uncompressed'])
        if key in origin_index:
            raise ValueError('Duplicate origin function')
        origin_index[key] = row
    branch_index = {}
    for row in branch_audit['records']:
        key = (row['button_character_id'], row['function_body_start_uncompressed'])
        branch_index.setdefault(key, []).append(row)
    output = []
    visited = set()
    for row in join['records']:
        for body in row.get('bytecode_function_body_ranges') or []:
            start, end = body['body_start_uncompressed'], body['body_end_uncompressed']
            key = (row['button_character_id'], start)
            if key in visited or key not in origin_index or not (0 <= start <= end <= len(decompressed)):
                raise ValueError('Invalid or missing source function range')
            visited.add(key)
            origin = origin_index[key]
            complete = origin['origin_status'] == 'bounded_origin_candidates'
            result = {'button_character_id': key[0],
                      'function_body_start_uncompressed': start,
                      'origin_status': origin['origin_status'],
                      'candidate_consumer_edges': None,
                      'explored_candidate_state_count': None,
                      'runtime_behavior_verified': False,
                      'decompiled_semantics_verified': False}
            if complete:
                trace = trace_body(decompressed[start:end], start,
                                   origin['literal_string_locations'], branch_index.get(key, []))
                result.update(trace)
            output.append(result)
    if visited != set(origin_index) or len(output) != origins['function_body_count']:
        raise ValueError('Source function coverage mismatch')
    return {'source_sha256': source_sha256,
            'function_body_count': len(output),
            'complete_function_count': sum(x['candidate_consumer_edges'] is not None for x in output),
            'candidate_consumer_edge_count': sum(len(x['candidate_consumer_edges'] or []) for x in output),
            'runtime_behavior_verified': False,
            'decompiled_semantics_verified': False,
            'records': output,
            'limitations': ['Both conditional edges are candidate paths, not VM execution.',
                            'Only original bytecode and anonymous producer locations are reported.',
                            'An edge does not prove variable meaning, branch truth or FFDec equivalence.',
                            'No literal bytes, hashes, ActionScript, images or audio are serialized.']}


def main():
    from swf_inventory import load_swf
    parser = argparse.ArgumentParser()
    for name in ('swf', 'join', 'origins', 'branches', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    sha = hashlib.sha256(args.swf.read_bytes()).hexdigest()
    decompressed, _ = load_swf(args.swf)
    report = build_consumer_map(*[json.loads(getattr(args, k).read_text(encoding='utf-8'))
                                  for k in ('join', 'origins', 'branches')], decompressed, sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('records', 'limitations')}))


if __name__ == '__main__':
    main()
