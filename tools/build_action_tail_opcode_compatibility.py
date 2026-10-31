#!/usr/bin/env python3
"""Metadata-only operand compatibility probe for bounded 11-byte ActionEnd tails.

A syntactically valid secondary record walk is NOT evidence of execution.
Never emit original opcode bytes, operands, script text or media.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from swf_inventory import load_swf
from build_script_entry_evidence import _check_tag
from build_as2_action_opcode_evidence import _records

# Fixed payload lengths from the SWF legacy ActionRecord definitions.
FIXED_PAYLOAD_LENGTHS = {
    0x81: 2,  # GotoFrame
    0x87: 1,  # StoreRegister
    0x8A: 3,  # WaitForFrame
    0x8D: 1,  # WaitForFrame2
    0x99: 2,  # Jump
    0x9A: 1,  # GetURL2
    0x9D: 2,  # If
    0x9E: 0,  # Call
}
VARIABLE_PAYLOAD_CODES = {
    0x83, 0x88, 0x8B, 0x8C, 0x8E, 0x8F, 0x94, 0x9B, 0x9F
}
CLASS_NAMES = (
    "fixed_length_match", "fixed_length_mismatch",
    "push_payload_well_formed", "push_payload_invalid",
    "known_variable_payload_unchecked", "unlisted_long_opcode"
)


def push_payload_well_formed(payload):
    """Check Push type/length framing only, not operand semantics."""
    pos = 0
    while pos < len(payload):
        kind = payload[pos]
        pos += 1
        if kind == 0:  # null-terminated string
            end = payload.find(b"\x00", pos)
            if end < 0:
                return False
            pos = end + 1
        elif kind in (1, 7):  # Float / Integer
            pos += 4
        elif kind == 6:  # Double
            pos += 8
        elif kind == 9:  # Constant16
            pos += 2
        elif kind in (4, 5, 8):  # Register / Boolean / Constant8
            pos += 1
        elif kind not in (2, 3):  # Null / Undefined
            return False
        if pos > len(payload):
            return False
    return True


def classify_long_action(opcode, payload):
    """Return a coarse compatibility class, never the opcode or payload."""
    if opcode < 0x80:
        raise ValueError("Expected long-format ActionRecord")
    if opcode in FIXED_PAYLOAD_LENGTHS:
        return ("fixed_length_match" if len(payload) == FIXED_PAYLOAD_LENGTHS[opcode]
                else "fixed_length_mismatch")
    if opcode == 0x96:
        return ("push_payload_well_formed" if push_payload_well_formed(payload)
                else "push_payload_invalid")
    if opcode in VARIABLE_PAYLOAD_CODES:
        return "known_variable_payload_unchecked"
    return "unlisted_long_opcode"


def classify_11_byte_tail(tail):
    """Return two coarse classes for exact L2>L2>End syntax, or None."""
    if len(tail) != 11:
        raise ValueError("Expected exactly eleven trailing bytes")
    classes = []
    for offset in (0, 5):
        opcode = tail[offset]
        if opcode < 0x80 or struct.unpack_from("<H", tail, offset + 1)[0] != 2:
            return None
        classes.append(classify_long_action(opcode, tail[offset + 3:offset + 5]))
    if tail[10] != 0:
        return None
    return tuple(classes)



BRANCH_CODES = {0x99: "jump", 0x9D: "if"}
UNRESOLVED_TARGET_CLASSES = (
    "pre_end_record_interior", "tail_record_interior",
    "outside_before", "outside_after", "invalid_operand_length"
)
PRE_END_INTERIOR_REGIONS = ("length_field", "payload", "unclassified")

TAIL_ACTION_KINDS = ("goto_frame", "jump", "if", "other")
TAIL_BRANCH_TARGETS = ("record_boundary", "record_interior", "before_tail", "after_tail")
PRE_END_TARGETS = ("record_boundary", "record_interior", "first_action_end",
                   "before_first_action_end", "outside_before", "outside_after")


def audit_11_byte_tail_control_flow(body):
    """Return static branch classifications, never opcode bytes or offsets."""
    tail_start = len(body) - 11
    if tail_start < 1 or classify_11_byte_tail(body[-11:]) is None:
        raise ValueError("Expected bounded L2>L2>End tail")
    pre_kinds, pre_targets = Counter(), Counter()
    pos = 0
    while pos < tail_start:
        opcode = body[pos]
        pos += 1
        if opcode == 0:
            if pos != tail_start:
                raise ValueError("First ActionEnd offset mismatch")
            break
        length = 0
        if opcode >= 0x80:
            if pos + 2 > tail_start - 1:
                raise ValueError("Truncated pre-End action header")
            length = struct.unpack_from("<H", body, pos)[0]
            pos += 2
            if pos + length > tail_start - 1:
                raise ValueError("Pre-End action crosses first ActionEnd")
        if opcode in BRANCH_CODES and length == 2:
            target = pos + length + struct.unpack_from("<h", body, pos)[0]
            pre_kinds[BRANCH_CODES[opcode]] += 1
            if target in (tail_start, tail_start + 5, tail_start + 10):
                category = "record_boundary"
            elif tail_start <= target < len(body):
                category = "record_interior"
            elif target == tail_start - 1:
                category = "first_action_end"
            elif target < 0:
                category = "outside_before"
            elif target >= len(body):
                category = "outside_after"
            else:
                category = "before_first_action_end"
            pre_targets[category] += 1
        pos += length
    else:
        raise ValueError("No first ActionEnd at expected offset")
    tail_kinds, tail_targets = Counter(), Counter()
    tail = body[-11:]
    for offset in (0, 5):
        opcode = tail[offset]
        kind = ("goto_frame" if opcode == 0x81 else BRANCH_CODES.get(opcode, "other"))
        tail_kinds[kind] += 1
        if opcode in BRANCH_CODES:
            target = tail_start + offset + 5 + struct.unpack_from("<h", tail, offset + 3)[0]
            if target in (tail_start, tail_start + 5, tail_start + 10):
                category = "record_boundary"
            elif tail_start <= target < len(body):
                category = "record_interior"
            elif target < tail_start:
                category = "before_tail"
            else:
                category = "after_tail"
            tail_targets[category] += 1
    return tail_kinds, tail_targets, pre_kinds, pre_targets

def classify_pre_end_record_interior(target, nodes, tail_start):
    """Classify a branch target inside a parsed top-level record, not runtime behavior."""
    for start, (opcode, next_pos, _) in nodes.items():
        if start >= tail_start:
            continue
        if start < target < next_pos:
            if opcode >= 0x80:
                return "length_field" if target < start + 3 else "payload"
            return "unclassified"
    return "unclassified"


def audit_11_byte_tail_reachability(body):
    """Bounded top-level Jump/If/fallthrough graph; NOT Flash runtime reachability.

    Nested function bodies, WaitForFrame skip behavior and dynamic execution are
    deliberately not modeled. Invalid branch targets are counted, not followed.
    """
    tail_start = len(body) - 11
    if tail_start < 1 or classify_11_byte_tail(body[-11:]) is None:
        raise ValueError("Expected bounded L2>L2>End tail")
    nodes = {}
    pos = 0
    while pos < tail_start:
        start = pos
        opcode = body[pos]
        pos += 1
        if opcode == 0:
            if pos != tail_start:
                raise ValueError("First ActionEnd offset mismatch")
            nodes[start] = (opcode, pos, None)
            break
        length = 0
        if opcode >= 0x80:
            if pos + 2 > tail_start - 1:
                raise ValueError("Truncated pre-End action header")
            length = struct.unpack_from("<H", body, pos)[0]
            pos += 2
            if pos + length > tail_start - 1:
                raise ValueError("Pre-End action crosses first ActionEnd")
        target = (pos + length + struct.unpack_from("<h", body, pos)[0]
                  if opcode in BRANCH_CODES and length == 2 else None)
        pos += length
        nodes[start] = (opcode, pos, target)
    if pos != tail_start:
        raise ValueError("No first ActionEnd at expected offset")
    for offset in (0, 5):
        opcode = body[tail_start + offset]
        target = (tail_start + offset + 5
                  + struct.unpack_from("<h", body, tail_start + offset + 3)[0]
                  if opcode in BRANCH_CODES else None)
        nodes[tail_start + offset] = (opcode, tail_start + offset + 5, target)
    nodes[tail_start + 10] = (0, len(body), None)

    graph = {}
    unresolved = 0
    unresolved_targets = Counter()
    interior_regions = Counter()
    unresolved_sources = {}
    for start, (opcode, next_pos, target) in nodes.items():
        if opcode in (0, 0x2A, 0x3E):  # ActionEnd / Throw / Return
            edges = []
        elif opcode in BRANCH_CODES:
            edges = [target] if target in nodes else []
            if target not in nodes:
                unresolved += 1
                if target is None:
                    category = "invalid_operand_length"
                elif target < 0:
                    category = "outside_before"
                elif target >= len(body):
                    category = "outside_after"
                elif target < tail_start:
                    category = "pre_end_record_interior"
                else:
                    category = "tail_record_interior"
                unresolved_targets[category] += 1
                if category == "pre_end_record_interior":
                    interior_regions[
                        classify_pre_end_record_interior(target, nodes, tail_start)
                    ] += 1
                unresolved_sources[start] = category
            if opcode == 0x9D and next_pos in nodes:
                edges.append(next_pos)
        else:
            edges = [next_pos] if next_pos in nodes else []
        graph[start] = edges

    reached = set()
    pending = [0]
    while pending:
        node = pending.pop()
        if node in reached or node not in graph:
            continue
        reached.add(node)
        pending.extend(graph[node])
    reachable_unresolved = Counter(unresolved_sources[node] for node in reached
                                   if node in unresolved_sources)
    boundaries = {tail_start, tail_start + 5, tail_start + 10}
    pre_edges = [(start, target) for start, (opcode, _, target) in nodes.items()
                 if start < tail_start - 1 and opcode in BRANCH_CODES
                 and target in boundaries]
    return {
        "tail_record_count": sum(node in reached for node in (tail_start, tail_start + 5)),
        "tail_end_reachable": tail_start + 10 in reached,
        "first_end_reachable": tail_start - 1 in reached,
        "pre_end_to_tail_edges": len(pre_edges),
        "reachable_pre_end_to_tail_edges": sum(start in reached for start, _ in pre_edges),
        "unresolved_branch_edges": unresolved,
        "unresolved_branch_target_histogram": {
            key: unresolved_targets[key] for key in UNRESOLVED_TARGET_CLASSES
        },
        "reachable_unresolved_branch_target_histogram": {
            key: reachable_unresolved[key] for key in UNRESOLVED_TARGET_CLASSES
        },
        "unresolved_pre_end_interior_region_histogram": {
            key: interior_regions[key] for key in PRE_END_INTERIOR_REGIONS
        },
    }


def build_tail_compatibility(manifest, data):
    source = manifest.get("source", {}).get("sha256")
    if not isinstance(source, str) or len(source) != 64:
        raise ValueError("Missing source provenance")
    tags = manifest.get("tags")
    scripts = manifest.get("scripts")
    if not isinstance(tags, list) or not isinstance(scripts, list):
        raise ValueError("Missing tag/script inventory")
    selected = [tag for tag in tags if tag.get("tag_code") in (12, 59)]
    expected = [script for script in scripts if script.get("tag_code") in (12, 59)]
    if len(selected) != len(expected):
        raise ValueError("Legacy script count mismatch")
    classes = Counter()
    pairs = Counter()
    by_tag = Counter()
    length_11 = 0
    nonmatching_shape = 0
    tail_kinds, tail_targets = Counter(), Counter()
    pre_kinds, pre_targets = Counter(), Counter()
    reachability = Counter()
    reach_tail_end = reach_first_end = pre_tail_edges = reached_pre_tail_edges = unresolved_edges = 0
    unresolved_targets = Counter()
    reachable_unresolved_targets = Counter()
    interior_regions = Counter()
    for tag, script in zip(selected, expected):
        for key in ("tag_code", "timeline", "frame", "offset_uncompressed", "length"):
            if tag.get(key) != script.get(key):
                raise ValueError("Script provenance mismatch")
        _check_tag(data, tag)
        start = tag["body_offset_uncompressed"]
        body = data[start:start + tag["length"]]
        if tag["tag_code"] == 59:
            if len(body) < 2 or struct.unpack_from("<H", body)[0] != tag.get("init_target_sprite_id"):
                raise ValueError("DoInitAction target mismatch")
            if script.get("init_target_sprite_id") != tag["init_target_sprite_id"]:
                raise ValueError("DoInitAction script target mismatch")
            body = body[2:]
        _, ended, trailing = _records(body)
        if trailing != 11:
            continue
        if not ended:
            raise ValueError("Eleven-byte tail without ActionEnd")
        length_11 += 1
        pair = classify_11_byte_tail(body[-11:])
        if pair is None:
            nonmatching_shape += 1
            continue
        candidate_k, candidate_t, prior_k, prior_t = audit_11_byte_tail_control_flow(body)
        reach = audit_11_byte_tail_reachability(body)
        reachability[str(reach["tail_record_count"])] += 1
        reach_tail_end += int(reach["tail_end_reachable"])
        reach_first_end += int(reach["first_end_reachable"])
        pre_tail_edges += reach["pre_end_to_tail_edges"]
        reached_pre_tail_edges += reach["reachable_pre_end_to_tail_edges"]
        unresolved_edges += reach["unresolved_branch_edges"]
        unresolved_targets.update(reach["unresolved_branch_target_histogram"])
        reachable_unresolved_targets.update(reach["reachable_unresolved_branch_target_histogram"])
        interior_regions.update(reach["unresolved_pre_end_interior_region_histogram"])
        tail_kinds.update(candidate_k)
        tail_targets.update(candidate_t)
        pre_kinds.update(prior_k)
        pre_targets.update(prior_t)
        classes.update(pair)
        pairs[">".join(pair)] += 1
        by_tag[str(tag["tag_code"])] += 1
    eligible = sum(pairs.values())
    return {
        "source_sha256": source,
        "legacy_container_count": len(selected),
        "trailing_length_11_count": length_11,
        "l2_l2_end_candidate_count": eligible,
        "other_shape_count": nonmatching_shape,
        "candidate_record_count": sum(classes.values()),
        "candidate_record_class_histogram": {k: classes[k] for k in CLASS_NAMES},
        "candidate_pair_class_histogram": dict(sorted(pairs.items())),
        "candidate_by_tag_code": dict(sorted(by_tag.items())),
        "candidate_action_kind_histogram": {k: tail_kinds[k] for k in TAIL_ACTION_KINDS},
        "candidate_branch_target_histogram": {k: tail_targets[k] for k in TAIL_BRANCH_TARGETS},
        "pre_end_branch_count": sum(pre_kinds.values()),
        "pre_end_branch_kind_histogram": {k: pre_kinds[k] for k in ("jump", "if")},
        "pre_end_branch_target_histogram": {k: pre_targets[k] for k in PRE_END_TARGETS},
        "candidate_tail_static_reachability_histogram": {
            str(k): reachability[str(k)] for k in range(3)},
        "candidate_tail_end_static_reachable_count": reach_tail_end,
        "candidate_first_end_static_reachable_count": reach_first_end,
        "candidate_pre_end_to_tail_boundary_edges": pre_tail_edges,
        "candidate_reachable_pre_end_to_tail_boundary_edges": reached_pre_tail_edges,
        "candidate_unresolved_branch_edges": unresolved_edges,
        "candidate_unresolved_branch_target_histogram": {
            key: unresolved_targets[key] for key in UNRESOLVED_TARGET_CLASSES
        },
        "candidate_reachable_unresolved_branch_target_histogram": {
            key: reachable_unresolved_targets[key] for key in UNRESOLVED_TARGET_CLASSES
        },
        "candidate_unresolved_pre_end_interior_region_histogram": {
            key: interior_regions[key] for key in PRE_END_INTERIOR_REGIONS
        },
        "limitations": [
            "Only secondary 11-byte L2>L2>End syntax after the FIRST ActionEnd is probed.",
            "Known opcode framing does not prove Flash executes the trailing records.",
            "Variable-length payloads are not semantically decoded.",
            "A static branch target does not establish Flash runtime reachability.",
            "Reachability is only a top-level Jump/If/fallthrough graph from the first record.",
            "WaitForFrame skip behavior, nested bodies and dynamic execution are not modeled.",
            "Unresolved branch targets are classified but not followed; graph absence does not prove runtime unreachability.",
            "Reachable unresolved edges count graph-reached source records, not executable Flash behavior.",
            "Pre-End interior regions describe byte positions in top-level records, not valid jump targets.",
            "GotoFrame operands are frame numbers, not relative branch offsets.",
            "Only top-level pre-End branches are scanned; nested function bodies are excluded.",
            "No opcode values, operand bytes, ActionScript or media are emitted."
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("Original SWF SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    report = build_tail_compatibility(manifest, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "trailing_length_11_count", "l2_l2_end_candidate_count",
        "candidate_record_class_histogram")}))


if __name__ == "__main__":
    main()
