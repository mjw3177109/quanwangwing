#!/usr/bin/env python3
"""Type-only candidate operand origins for source-verified button function CFGs.

Abstract syntax analysis only: no VM execution, operand values or FFDec equivalence.
"""
from __future__ import annotations
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
from button_action_structure import partition_top_level_actions
from build_button_function_branch_audit import audit_branches
from build_button_function_cfg_audit import PUSH_TYPES, PUSH_WIDTHS
from build_button_function_stack_audit import audit_stack_candidates


def _push_origins(payload: bytes) -> tuple[str, ...]:
    """Read ActionPush element type tags and boundaries; discard values."""
    origins = []
    pos = 0
    while pos < len(payload):
        kind = payload[pos]
        pos += 1
        if kind == 0:
            end = payload.find(b"\x00", pos)
            if end < 0:
                raise ValueError("Unterminated ActionPush string")
            pos = end + 1
        else:
            width = PUSH_WIDTHS.get(kind)
            if width is None or pos + width > len(payload):
                raise ValueError("Invalid ActionPush element boundary")
            pos += width
        origins.append("literal_" + PUSH_TYPES[kind])
    return tuple(origins)


def _push_string_locations(payload: bytes) -> tuple[tuple[int, bytes], ...]:
    """Private string element indices and raw equality keys; values never serialized."""
    locations = []
    pos = 0
    element_index = 0
    while pos < len(payload):
        kind = payload[pos]
        pos += 1
        if kind == 0:
            end = payload.find(b"\x00", pos)
            if end < 0:
                raise ValueError("Unterminated ActionPush string")
            locations.append((element_index, payload[pos:end]))
            pos = end + 1
        else:
            width = PUSH_WIDTHS.get(kind)
            if width is None or pos + width > len(payload):
                raise ValueError("Invalid ActionPush element boundary")
            pos += width
        element_index += 1
    return tuple(locations)


def _push_string_values(payload: bytes) -> tuple[bytes, ...]:
    """Private raw-byte equality keys for ActionPush strings; never serialize values."""
    return tuple(raw for _, raw in _push_string_locations(payload))


def audit_operand_origins(join: dict, decompressed: bytes, source_sha256: str,
                          max_states: int = 4096, max_depth: int = 128) -> dict:
    if type(max_states) is not int or type(max_depth) is not int or max_states < 1 or max_depth < 1:
        raise ValueError("Positive integer analysis limits required")
    # Reuse source SHA, byte range, opcode histogram, CFG and branch gates.
    stack = audit_stack_candidates(join, decompressed, source_sha256,
                                   max_states=max_states, max_depth=max_depth)
    branches = audit_branches(join, decompressed, source_sha256)
    branch_index = {}
    for branch in branches["records"]:
        key = (branch["function_body_start_uncompressed"], branch["branch_offset_uncompressed"])
        if key in branch_index:
            raise ValueError("Duplicate branch provenance")
        branch_index[key] = branch
    stack_index = {}
    for item in stack["records"]:
        key = (item["button_character_id"], item["function_body_start_uncompressed"])
        if key in stack_index:
            raise ValueError("Duplicate stack provenance")
        stack_index[key] = item
    output = []
    statuses = Counter({"bounded_origin_candidates": 0, "analysis_limit_reached": 0,
                        "candidate_underflow_detected": 0, "source_stack_unresolved": 0})
    if_totals = Counter()
    variable_totals = Counter()
    literal_classes = {}  # raw values remain in-memory; only local S1/S2 labels leave
    literal_counts = Counter()
    for row in join["records"]:
        for item in row.get("bytecode_function_body_ranges") or []:
            start, end = item["body_start_uncompressed"], item["body_end_uncompressed"]
            source = stack_index.get((row["button_character_id"], start))
            if source is None:
                raise ValueError("Missing verified stack provenance")
            result = {
                "button_character_id": row["button_character_id"],
                "function_body_start_uncompressed": start,
                "origin_status": "source_stack_unresolved",
                "source_get_variable_opcode_count": None,
                "source_set_variable_opcode_count": None,
                "source_if_opcode_count": None,
                "explored_origin_candidate_state_count": None,
                "candidate_underflow_record_count": None,
                "if_operand_origin_counts": None,
                "variable_name_operand_origin_counts": None,
                "literal_string_equivalence_classes_in_push_order": None,
                "literal_string_locations": None,
                "literal_string_count": None,
                "runtime_behavior_verified": False,
            }
            if source["stack_status"] != "bounded_candidate_paths":
                statuses["source_stack_unresolved"] += 1
                output.append(result)
                continue
            body = decompressed[start:end]
            records = partition_top_level_actions(body)["records"]
            by_offset = {rec.start: rec for rec in records}
            result["source_get_variable_opcode_count"] = sum(rec.opcode == 0x1C for rec in records)
            result["source_set_variable_opcode_count"] = sum(rec.opcode == 0x1D for rec in records)
            result["source_if_opcode_count"] = sum(rec.opcode == 0x9D for rec in records)
            edges = {}
            for rec in records:
                if rec.opcode in (0x00, 0x3E):
                    edges[rec.start] = ()
                elif rec.opcode in (0x99, 0x9D):
                    branch = branch_index.get((start, start + rec.start))
                    if branch is None or branch["target_classification"] not in ("record_start", "body_end"):
                        raise ValueError("Missing source-verified branch")
                    target = branch["target_offset_uncompressed"] - start
                    edges[rec.start] = (target, rec.end) if rec.opcode == 0x9D else (target,)
                else:
                    edges[rec.start] = (rec.end,)
            pending = deque([(records[0].start, ())] if records else [])
            seen = set()
            if_sources = set()
            variable_sources = set()
            underflows = set()
            limit_reached = False
            while pending:
                offset, stack_types = pending.popleft()
                if offset == len(body) or (offset, stack_types) in seen:
                    continue
                if offset not in by_offset:
                    raise ValueError("Candidate edge is not a source record boundary")
                if len(seen) >= max_states or len(stack_types) > max_depth:
                    limit_reached = True
                    break
                seen.add((offset, stack_types))
                rec = by_offset[offset]
                next_stack = list(stack_types)
                if rec.opcode == 0x96:
                    next_stack.extend(_push_origins(body[rec.start + 3:rec.end]))
                else:
                    pops = {0x00: 0, 0x0C: 2, 0x1C: 1, 0x1D: 2,
                            0x3E: 1, 0x3F: 2, 0x99: 0, 0x9D: 1}.get(rec.opcode)
                    if pops is None:
                        raise ValueError("Source stack candidate has unmodeled opcode")
                    if len(next_stack) < pops:
                        underflows.add(offset)
                        continue
                    popped = [next_stack.pop() for _ in range(pops)]
                    if rec.opcode == 0x1C:
                        variable_sources.add((offset, popped[0]))
                        next_stack.append("variable_read_result")
                    elif rec.opcode == 0x1D:
                        variable_sources.add((offset, popped[1]))  # value popped before name
                    elif rec.opcode in (0x0C, 0x3F):
                        next_stack.append("arithmetic_result")
                    elif rec.opcode == 0x9D:
                        if_sources.add((offset, popped[0]))
                if len(next_stack) > max_depth:
                    limit_reached = True
                    break
                pending.extend((target, tuple(next_stack)) for target in edges[offset])
            # A truncated or underflowing exploration cannot support complete
            # producer totals, even when some paths yielded valid candidates.
            if limit_reached:
                status = "analysis_limit_reached"
            elif underflows:
                status = "candidate_underflow_detected"
            else:
                status = "bounded_origin_candidates"
            if_counts = dict(sorted(Counter(origin for _, origin in if_sources).items()))
            variable_counts = dict(sorted(Counter(origin for _, origin in variable_sources).items()))
            complete = status == "bounded_origin_candidates"
            if complete:
                if_totals.update(if_counts)
                variable_totals.update(variable_counts)
                # Compare only exact ActionPush string bytes across source-backed
                # function bodies. This does NOT resolve variable bindings.
                sequence = []
                locations = []
                for action in records:
                    if action.opcode != 0x96:
                        continue
                    for element_index, raw in _push_string_locations(body[action.start + 3:action.end]):
                        if raw not in literal_classes:
                            literal_classes[raw] = f"S{len(literal_classes) + 1}"
                        label = literal_classes[raw]
                        sequence.append(label)
                        locations.append({
                            "push_record_offset_uncompressed": start + action.start,
                            "push_element_index": element_index,
                            "class_label": label,
                        })
                        literal_counts[label] += 1
                result["literal_string_equivalence_classes_in_push_order"] = sequence
                result["literal_string_locations"] = locations
                result["literal_string_count"] = len(sequence)
            result.update({
                "origin_status": status,
                "explored_origin_candidate_state_count": len(seen),
                "candidate_underflow_record_count": len(underflows),
                "if_operand_origin_counts": if_counts if complete else None,
                "variable_name_operand_origin_counts": variable_counts if complete else None,
            })
            statuses[result["origin_status"]] += 1
            output.append(result)
    if len(output) != stack["function_body_count"]:
        raise ValueError("Operand origin function coverage mismatch")
    return {
        "source_sha256": source_sha256,
        "function_body_count": len(output),
        "origin_status_counts": dict(statuses),
        "source_get_variable_opcode_total": sum(r["source_get_variable_opcode_count"] or 0 for r in output),
        "source_set_variable_opcode_total": sum(r["source_set_variable_opcode_count"] or 0 for r in output),
        "source_if_opcode_total": sum(r["source_if_opcode_count"] or 0 for r in output),
        "if_operand_origin_totals": dict(sorted(if_totals.items())),
        "variable_name_operand_origin_totals": dict(sorted(variable_totals.items())),
        "literal_string_occurrence_count": sum(literal_counts.values()),
        "distinct_literal_string_class_count": len(literal_classes),
        "literal_string_class_occurrence_counts": dict(literal_counts),
        "runtime_behavior_verified": False,
        "decompiled_semantics_verified": False,
        "records": output,
        "limitations": [
            "Origin categories describe possible stack producers, not operand values or variable names.",
            "S-number equality labels and source locations are static ActionPush evidence, not values or variable bindings.",
            "No ActionPush literal text, bytes or content hashes are serialized.",
            "Both conditional edges are considered; some candidate paths may be infeasible.",
            "The function entry stack is assumed empty; no Flash VM execution is observed.",
            "Analysis limits, candidate underflow and unresolved source CFGs prevent complete provenance claims.",
            "No original SWF bytes, ActionScript source, artwork, audio, or gameplay values are emitted.",
        ],
    }


def main() -> None:
    from swf_inventory import load_swf
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--join", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sha = hashlib.sha256(args.swf.read_bytes()).hexdigest()
    data, _ = load_swf(args.swf)
    report = audit_operand_origins(json.loads(args.join.read_text(encoding="utf-8")), data, sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
