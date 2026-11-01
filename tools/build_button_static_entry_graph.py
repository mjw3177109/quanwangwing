#!/usr/bin/env python3
"""Bounded top-level AS1/AS2 button ActionRecord entry graph (metadata only).

This graph is an over-approximation of syntactic paths, NOT Flash runtime
reachability. Nested bodies, conditions and VM state are not evaluated.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import struct

from build_button_tail_evidence import build_button_tail_evidence, first_action_end_offset

# These opcodes can change control flow in ways this bounded graph does not
# interpret. Their presence is explicitly counted rather than silently ignored.
UNMODELED_CONTROL_OPCODES = {0x8A, 0x8D, 0x8F, 0x94, 0x9B, 0x8E}
DEFINE_FUNCTION_HEADER_STATUSES = ("complete", "code_size_mismatch", "malformed_header")
INVALID_TARGET_CLASSES = (
    "invalid_operand_length", "before_stream", "after_stream", "record_interior",
)



def classify_define_function_header(payload: bytes, operand: int, length: int) -> tuple:
    """Classify ActionDefineFunction (0x9B) framing without exporting names/body."""
    limit = operand + length
    name_end = payload.find(b"\x00", operand, limit)
    if name_end < 0 or name_end + 3 > limit:
        return "malformed_header", 0, 0, False
    cursor = name_end + 1
    param_count = struct.unpack_from("<H", payload, cursor)[0]
    cursor += 2
    if param_count > limit - cursor:
        return "malformed_header", 0, 0, False
    for _ in range(param_count):
        end = payload.find(b"\x00", cursor, limit)
        if end < 0:
            return "malformed_header", 0, 0, False
        cursor = end + 1
    if cursor + 2 > limit:
        return "malformed_header", 0, 0, False
    code_size = struct.unpack_from("<H", payload, cursor)[0]
    cursor += 2
    if cursor + code_size != limit:
        return "code_size_mismatch", 0, 0, False
    return "complete", param_count, code_size, name_end == operand


def audit_top_level_entry_graph(payload: bytes, first_end: int) -> dict:
    """Follow valid top-level record boundaries from byte offset zero.

    ActionEnd terminates a path. Jump has only a target edge, If has both
    target and fallthrough edges. All other records get a syntactic fallthrough
    edge, including opcodes with unmodeled VM semantics. No operand bytes,
    branch displacements or source text are returned.
    """
    if not payload or not 0 <= first_end < len(payload) or payload[first_end] != 0:
        raise ValueError("Invalid verified first ActionEnd boundary")
    nodes = {}
    pos = 0
    while pos < len(payload):
        start = pos
        opcode = payload[pos]
        if opcode < 0x80:
            pos += 1
            operand_start = pos
            operand_length = 0
        else:
            if pos + 3 > len(payload):
                raise ValueError("Truncated ActionRecord header")
            operand_length = struct.unpack_from("<H", payload, pos + 1)[0]
            operand_start = pos + 3
            pos = operand_start + operand_length
            if pos > len(payload):
                raise ValueError("ActionRecord operand exceeds verified action range")
        nodes[start] = (opcode, pos, operand_start, operand_length)
    if first_end not in nodes:
        raise ValueError("First ActionEnd is not an ActionRecord boundary")

    queue = deque([0])
    visited = set()
    invalid_branch_target_classes = {key: 0 for key in INVALID_TARGET_CLASSES}
    reached_tail_branch_edges = 0
    reached_tail_end_branch_edges = 0
    unmodeled_reached = 0
    unmodeled_reached_counts = {f"0x{op:02x}": 0 for op in sorted(UNMODELED_CONTROL_OPCODES)}
    function_status_counts = {key: 0 for key in DEFINE_FUNCTION_HEADER_STATUSES}
    function_parameter_total = 0
    function_declared_body_byte_total = 0
    anonymous_function_count = 0
    while queue:
        start = queue.popleft()
        if start in visited:
            continue
        visited.add(start)
        opcode, end, operand, length = nodes[start]
        if opcode in UNMODELED_CONTROL_OPCODES:
            unmodeled_reached += 1
            unmodeled_reached_counts[f"0x{opcode:02x}"] += 1
        if opcode == 0x9B:
            status, parameters, code_bytes, anonymous = classify_define_function_header(
                payload, operand, length)
            function_status_counts[status] += 1
            if status == "complete":
                function_parameter_total += parameters
                function_declared_body_byte_total += code_bytes
                anonymous_function_count += int(anonymous)
        if opcode == 0:
            continue
        successors = []
        if opcode in (0x99, 0x9D):
            if length != 2:
                invalid_branch_target_classes["invalid_operand_length"] += 1
            else:
                displacement = struct.unpack_from("<h", payload, operand)[0]
                target = end + displacement
                if target in nodes:
                    successors.append(target)
                    if target > first_end:
                        if nodes[target][0] == 0:
                            reached_tail_end_branch_edges += 1
                        else:
                            reached_tail_branch_edges += 1
                else:
                    if target < 0:
                        target_class = "before_stream"
                    elif target >= len(payload):
                        target_class = "after_stream"
                    else:
                        target_class = "record_interior"
                    invalid_branch_target_classes[target_class] += 1
            if opcode == 0x9D and end in nodes:
                successors.append(end)
        elif end in nodes:
            successors.append(end)
        queue.extend(x for x in successors if x not in visited)

    tail_candidates = [p for p in visited if p > first_end and nodes[p][0] != 0]
    tail_end_nodes = [p for p in visited if p > first_end and nodes[p][0] == 0]
    return {
        "top_level_record_count": len(nodes),
        "visited_top_level_record_count": len(visited),
        "visited_pre_end_record_count": sum(p < first_end for p in visited),
        "visited_first_action_end": first_end in visited,
        "visited_post_end_candidate_record_count": len(tail_candidates),
        "visited_post_end_action_end_count": len(tail_end_nodes),
        "syntactic_entry_path_to_post_end_candidate": bool(tail_candidates),
        "visited_branch_edges_to_post_end_candidate": reached_tail_branch_edges,
        "visited_branch_edges_to_post_end_action_end": reached_tail_end_branch_edges,
        "invalid_visited_branch_target_count": sum(invalid_branch_target_classes.values()),
        "invalid_visited_branch_target_class_counts": invalid_branch_target_classes,
        "unmodeled_visited_control_opcode_count": unmodeled_reached,
        "unmodeled_visited_control_opcode_counts": unmodeled_reached_counts,
        "visited_define_function_header_status_counts": function_status_counts,
        "visited_define_function_parameter_total": function_parameter_total,
        "visited_define_function_declared_body_byte_total": function_declared_body_byte_total,
        "visited_anonymous_define_function_count": anonymous_function_count,
        "runtime_reachability_verified": False,
    }


def build_button_static_entry_graph(manifest: dict, buttons: dict, opcodes: dict,
                                    tails: dict, data: bytes) -> dict:
    # Fail closed if any upstream evidence differs from original SWF bytes.
    verified = build_button_tail_evidence(manifest, buttons, opcodes, data)
    if verified != tails:
        raise ValueError("Tail report does not match verified SWF bytes")
    record_lookup = {
        (b["character_id"], rec["offset_uncompressed"]): rec
        for b in buttons["buttons"] for rec in b["embedded_action_records"]
    }
    rows = []
    for row in verified["tail_records"]:
        cid = row["button_character_id"]
        offset = row["action_offset_uncompressed"]
        record = record_lookup[(cid, offset)]
        length = record["action_bytes_including_terminator"]
        payload = data[offset + 4:offset + 4 + length]
        first_end = first_action_end_offset(payload)
        if first_end is None or first_end + 1 >= len(payload):
            raise ValueError("Verified tail boundary is missing")
        graph = audit_top_level_entry_graph(payload, first_end)
        rows.append({
            "button_character_id": cid,
            "action_offset_uncompressed": offset,
            "post_end_candidate_status": row["post_end_candidate_status"],
            **graph,
        })
    invalid_class_totals = {key: sum(
        r["invalid_visited_branch_target_class_counts"][key] for r in rows
    ) for key in INVALID_TARGET_CLASSES}
    return {
        "source_sha256": verified["source_sha256"],
        "trailing_record_count": verified["trailing_record_count"],
        "graph_record_count": len(rows),
        "graphs_with_syntactic_entry_path_to_post_end_candidate": sum(
            r["syntactic_entry_path_to_post_end_candidate"] for r in rows),
        "visited_post_end_candidate_record_total": sum(
            r["visited_post_end_candidate_record_count"] for r in rows),
        "invalid_visited_branch_target_total": sum(
            r["invalid_visited_branch_target_count"] for r in rows),
        "invalid_visited_branch_target_class_totals": invalid_class_totals,
        "unmodeled_visited_control_opcode_total": sum(
            r["unmodeled_visited_control_opcode_count"] for r in rows),
        "unmodeled_visited_control_opcode_totals": {
            f"0x{op:02x}": sum(r["unmodeled_visited_control_opcode_counts"][f"0x{op:02x}"]
                                 for r in rows)
            for op in sorted(UNMODELED_CONTROL_OPCODES)
        },
        "visited_define_function_header_status_totals": {
            key: sum(r["visited_define_function_header_status_counts"][key] for r in rows)
            for key in DEFINE_FUNCTION_HEADER_STATUSES
        },
        "visited_define_function_parameter_total": sum(
            r["visited_define_function_parameter_total"] for r in rows),
        "visited_define_function_declared_body_byte_total": sum(
            r["visited_define_function_declared_body_byte_total"] for r in rows),
        "visited_anonymous_define_function_total": sum(
            r["visited_anonymous_define_function_count"] for r in rows),
        "runtime_reachability_verified": False,
        "graphs": rows,
        "limitations": [
            "Syntactic top-level paths are NOT proof of Flash runtime execution.",
            "Conditional values, WaitForFrame, nested functions, With, Try and VM state are not modeled.",
            "Invalid branch target classes describe byte positions, not VM execution or safety.",
            "No original operand bytes, ActionScript, artwork, SWF or audio are emitted.",
        ],
    }


def main() -> None:
    from swf_inventory import load_swf
    parser = argparse.ArgumentParser()
    for key in ("swf", "manifest", "buttons", "opcodes", "tails", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("SWF source SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    result = build_button_static_entry_graph(
        manifest,
        json.loads(args.buttons.read_text(encoding="utf-8")),
        json.loads(args.opcodes.read_text(encoding="utf-8")),
        json.loads(args.tails.read_text(encoding="utf-8")),
        data,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("graphs", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
