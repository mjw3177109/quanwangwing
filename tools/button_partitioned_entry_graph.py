#!/usr/bin/env python3
"""Bounded syntactic entry graph over structure-partitioned button actions.

No Flash VM state, condition evaluation, or original operand bytes are emitted.
In particular, an entry path is NOT proof of runtime execution.
"""
from __future__ import annotations

from collections import Counter, deque
import struct

from button_action_structure import partition_top_level_actions


TARGET_CLASSES = (
    "pre_end_record", "first_end", "post_end_record", "function_body",
    "record_interior", "before_stream", "after_stream",
)
UNMODELED_CONTROL = (0x8A, 0x8D)


def audit_partitioned_entry_graph(payload: bytes) -> dict:
    """Follow bounded Jump/If/fallthrough edges on true top-level boundaries.

    Function declaration bodies are skipped as one top-level record. Unsupported
    With/Try scopes and malformed records fail closed in the partitioner.
    ActionEnd terminates its own path even when syntactic bytes follow it.
    """
    parsed = partition_top_level_actions(payload)
    first_end = parsed["first_top_level_action_end_offset"]
    if first_end is None:
        raise ValueError("Missing top-level ActionEnd")
    nodes = {rec.start: rec for rec in parsed["records"]}
    if 0 not in nodes or first_end not in nodes:
        raise ValueError("Missing entry or End record")
    bodies = [(rec.body_start, rec.body_end) for rec in nodes.values()
              if rec.body_start is not None]
    classes = Counter({name: 0 for name in TARGET_CLASSES})
    kinds = Counter({"jump": 0, "if": 0})
    unmodeled = Counter({f"0x{op:02x}": 0 for op in UNMODELED_CONTROL})
    queue = deque([0])
    visited = set()
    while queue:
        start = queue.popleft()
        if start in visited:
            continue
        visited.add(start)
        rec = nodes[start]
        if rec.opcode == 0:
            continue
        if rec.opcode in UNMODELED_CONTROL:
            unmodeled[f"0x{rec.opcode:02x}"] += 1
        successors = []
        if rec.opcode in (0x99, 0x9D):
            if rec.header_end - rec.start != 5:
                raise ValueError("Invalid Jump/If operand length")
            kinds["jump" if rec.opcode == 0x99 else "if"] += 1
            target = rec.header_end + struct.unpack_from("<h", payload, rec.start + 3)[0]
            if target in nodes:
                cls = ("pre_end_record" if target < first_end else
                       "first_end" if target == first_end else "post_end_record")
                successors.append(target)
            elif any(lo <= target < hi for lo, hi in bodies):
                cls = "function_body"
            elif target < 0:
                cls = "before_stream"
            elif target >= len(payload):
                cls = "after_stream"
            else:
                cls = "record_interior"
            classes[cls] += 1
            if rec.opcode == 0x9D and rec.end in nodes:
                successors.append(rec.end)
        elif rec.end in nodes:
            successors.append(rec.end)
        queue.extend(target for target in successors if target not in visited)

    post_end = [p for p in visited if p > first_end and nodes[p].opcode != 0]
    return {
        "top_level_record_count": len(nodes),
        "visited_record_count": len(visited),
        "visited_pre_end_record_count": sum(p < first_end for p in visited),
        "visited_first_end": first_end in visited,
        "visited_post_end_record_count": len(post_end),
        "syntactic_entry_path_to_post_end_record": bool(post_end),
        "visited_branch_kind_counts": dict(kinds),
        "visited_branch_target_class_counts": dict(classes),
        "visited_unmodeled_control_opcode_counts": dict(unmodeled),
        "declared_function_count": parsed["declared_function_count"],
        "declared_function_body_byte_total": parsed["declared_function_body_byte_total"],
        "top_level_partition_verified": True,
        "runtime_reachability_verified": False,
        "limitations": [
            "Syntactic entry paths do not prove Flash runtime execution.",
            "Jump/If conditions, VM state and WaitForFrame skip semantics are not modeled.",
            "Declared function bodies are skipped, not interpreted or called.",
            "Unsupported With/Try scopes and malformed branches fail closed.",
            "No original SWF, scripts, operands, images or audio are emitted.",
        ],
    }
