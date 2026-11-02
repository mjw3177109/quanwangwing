#!/usr/bin/env python3
"""Conservative syntactic CFG candidates from source-backed SWF button functions."""
from __future__ import annotations
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
from button_action_structure import partition_top_level_actions
from build_button_function_branch_audit import audit_branches

SEQUENTIAL = frozenset((0x96, 0x0C, 0x1C, 0x1D, 0x3F))
TERMINATORS = frozenset((0x00, 0x3E))
BRANCHES = frozenset((0x99, 0x9D))
# SWF ActionPush (0x96) element types; lengths only, never decoded values.
PUSH_TYPES = {0: "string", 1: "float", 2: "null", 3: "undefined",
              4: "register", 5: "boolean", 6: "double", 7: "integer",
              8: "constant8", 9: "constant16"}
PUSH_WIDTHS = {1: 4, 2: 0, 3: 0, 4: 1, 5: 1, 6: 8, 7: 4, 8: 1, 9: 2}


def _push_type_counts(payload: bytes) -> Counter | None:
    """Check every ActionPush element boundary; emit types, never operand values."""
    pos = 0
    counts = Counter()
    while pos < len(payload):
        kind = payload[pos]
        pos += 1
        if kind == 0:
            terminator = payload.find(b"\x00", pos)
            if terminator < 0:
                return None
            pos = terminator + 1
        else:
            width = PUSH_WIDTHS.get(kind)
            if width is None or pos + width > len(payload):
                return None
            pos += width
        counts[PUSH_TYPES[kind]] += 1
    return counts



def audit_function_cfg(join: dict, decompressed: bytes, source_sha256: str) -> dict:
    audit = audit_branches(join, decompressed, source_sha256)
    branch_index = {}
    for branch in audit["records"]:
        key = (branch["function_body_start_uncompressed"], branch["branch_offset_uncompressed"])
        if key in branch_index:
            raise ValueError("Duplicate source branch offset")
        branch_index[key] = branch
    results = []
    statuses = Counter({"complete_syntactic_graph": 0,
                        "unresolved_opcode_or_target": 0,
                        "source_partition_rejected": 0})
    seen_bodies = set()
    total = complete = reachable = unreachable = 0
    push_totals = Counter()
    invalid_push_total = 0
    for row in join["records"]:
        for item in row.get("bytecode_function_body_ranges") or []:
            start, end = item["body_start_uncompressed"], item["body_end_uncompressed"]
            if (start, end) in seen_bodies:
                raise ValueError("Duplicate function body range")
            seen_bodies.add((start, end))
            if item["body_partition_status"] == "rejected":
                statuses["source_partition_rejected"] += 1
                results.append({"button_character_id": row["button_character_id"],
                                "function_body_start_uncompressed": start,
                                "graph_status": "source_partition_rejected",
                                "static_entry_reachable_record_count": None,
                                "static_entry_unreachable_record_count": None,
                                "runtime_reachability_verified": False,
                                "invalid_push_payload_count": None,
                                "push_operand_type_counts": None})
                continue
            body = decompressed[start:end]
            records = partition_top_level_actions(body)["records"]
            starts = {rec.start for rec in records}
            total += len(records)
            edges = {}
            unknown = invalid = conditional = unconditional = terminal = 0
            invalid_push = 0
            push_types = Counter()
            for rec in records:
                if rec.opcode in TERMINATORS:
                    terminal += 1
                    edges[rec.start] = ()
                elif rec.opcode == 0x96:
                    types = _push_type_counts(body[rec.start + 3:rec.end])
                    if types is None:
                        invalid_push += 1
                    else:
                        push_types.update(types)
                    edges[rec.start] = (rec.end,)
                elif rec.opcode in SEQUENTIAL:
                    edges[rec.start] = (rec.end,)
                elif rec.opcode in BRANCHES:
                    branch = branch_index.get((start, start + rec.start))
                    if branch is None or branch["branch_opcode"] != f"0x{rec.opcode:02x}":
                        raise ValueError("Missing source-verified branch record")
                    if rec.opcode == 0x9D:
                        conditional += 1
                    else:
                        unconditional += 1
                    if branch["target_classification"] not in ("record_start", "body_end"):
                        invalid += 1
                        edges[rec.start] = ()
                    else:
                        target = branch["target_offset_uncompressed"] - start
                        edges[rec.start] = (target, rec.end) if rec.opcode == 0x9D else (target,)
                else:
                    unknown += 1
                    edges[rec.start] = ()
            if invalid or unknown or invalid_push:
                status = "unresolved_opcode_or_target"
                count_reached = count_missing = None
            else:
                status = "complete_syntactic_graph"
                visited = set()
                pending = deque([records[0].start] if records else [])
                while pending:
                    node = pending.popleft()
                    if node == len(body) or node in visited:
                        continue
                    if node not in starts:
                        raise ValueError("Graph edge is not a record boundary")
                    visited.add(node)
                    pending.extend(edges[node])
                count_reached = len(visited)
                count_missing = len(records) - count_reached
                complete += len(records)
                reachable += count_reached
                unreachable += count_missing
            push_totals.update(push_types)
            invalid_push_total += invalid_push
            statuses[status] += 1
            results.append({
                "button_character_id": row["button_character_id"],
                "function_body_start_uncompressed": start,
                "graph_status": status,
                "top_level_record_count": len(records),
                "conditional_branch_count": conditional,
                "unconditional_branch_count": unconditional,
                "terminal_record_count": terminal,
                "unmodeled_opcode_count": unknown,
                "invalid_push_payload_count": invalid_push,
                "push_operand_type_counts": dict(sorted(push_types.items())),
                "invalid_branch_target_count": invalid,
                "static_entry_reachable_record_count": count_reached,
                "static_entry_unreachable_record_count": count_missing,
                "runtime_reachability_verified": False,
            })
    if len(results) != audit["function_body_count"]:
        raise ValueError("Function body coverage mismatch")
    if sum(x["conditional_branch_count"] + x["unconditional_branch_count"]
           for x in results if x["graph_status"] != "source_partition_rejected") != audit["branch_record_count"]:
        raise ValueError("Branch accounting mismatch")
    return {
        "source_sha256": source_sha256,
        "function_body_count": len(results),
        "graph_status_counts": dict(statuses),
        "partitioned_record_total": total,
        "complete_graph_record_total": complete,
        "static_entry_reachable_candidate_total": reachable,
        "static_entry_unreachable_candidate_total": unreachable,
        "invalid_push_payload_total": invalid_push_total,
        "push_operand_type_totals": dict(sorted(push_totals.items())),
        "decompiled_semantics_verified": False,
        "runtime_reachability_verified": False,
        "records": results,
        "limitations": [
            "ActionIf includes both syntactic paths; conditions and stack are not evaluated.",
            "Unknown control opcodes, invalid branch targets or malformed ActionPush operands invalidate complete graph claims.",
            "ActionPush type and length checks do not interpret pushed values or branch conditions.",
            "Static entry paths are candidates, not Flash VM execution or gameplay behavior.",
            "No original operands, script text, SWF bytes, or media are emitted.",
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
    report = audit_function_cfg(json.loads(args.join.read_text(encoding="utf-8")), data, sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
