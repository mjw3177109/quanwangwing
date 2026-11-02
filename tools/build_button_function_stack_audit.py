#!/usr/bin/env python3
"""Bounded, source-backed *candidate* stack-depth analysis for button functions.

Both ActionIf edges are explored. No values, executable semantics, or runtime
reachability are inferred from this over-approximation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path

from button_action_structure import partition_top_level_actions
from build_button_function_branch_audit import audit_branches
from build_button_function_cfg_audit import audit_function_cfg, _push_type_counts

# Minimum pops and resulting pushes for the small, explicitly supported AS1/2
# action subset. ActionPush is handled separately because its arity varies.
STACK_EFFECTS = {
    0x00: (0, 0),  # End
    0x0C: (2, 1),  # Multiply
    0x1C: (1, 1),  # GetVariable
    0x1D: (2, 0),  # SetVariable
    0x3E: (1, 0),  # Return
    0x3F: (2, 1),  # Modulo
    0x99: (0, 0),  # Jump
    0x9D: (1, 0),  # If
}
TERMINATORS = frozenset((0x00, 0x3E))


def audit_stack_candidates(join: dict, decompressed: bytes, source_sha256: str,
                           max_states: int = 4096, max_depth: int = 128) -> dict:
    if type(max_states) is not int or type(max_depth) is not int or max_states < 1 or max_depth < 1:
        raise ValueError("Positive integer analysis limits required")
    cfg = audit_function_cfg(join, decompressed, source_sha256)
    branches = audit_branches(join, decompressed, source_sha256)
    branch_index = {(r["function_body_start_uncompressed"], r["branch_offset_uncompressed"]): r
                    for r in branches["records"]}
    if len(branch_index) != branches["branch_record_count"]:
        raise ValueError("Duplicate branch provenance")
    cfg_index = {(r["button_character_id"], r["function_body_start_uncompressed"]): r
                 for r in cfg["records"]}
    if len(cfg_index) != cfg["function_body_count"]:
        raise ValueError("Duplicate CFG provenance")
    statuses = Counter({"bounded_candidate_paths": 0, "analysis_limit_reached": 0,
                        "source_cfg_unresolved": 0})
    output = []
    for row in join["records"]:
        for item in row.get("bytecode_function_body_ranges") or []:
            start, end = item["body_start_uncompressed"], item["body_end_uncompressed"]
            key = (row["button_character_id"], start)
            source_cfg = cfg_index.get(key)
            if source_cfg is None:
                raise ValueError("Missing source CFG provenance")
            result = {
                "button_character_id": row["button_character_id"],
                "function_body_start_uncompressed": start,
                "stack_status": "source_cfg_unresolved",
                "explored_candidate_state_count": None,
                "potential_underflow_record_count": None,
                "divergent_entry_depth_record_count": None,
                "max_candidate_stack_depth": None,
                "entry_stack_depth_assumption": 0,
                "runtime_stack_verified": False,
            }
            if source_cfg["graph_status"] != "complete_syntactic_graph":
                statuses["source_cfg_unresolved"] += 1
                output.append(result)
                continue
            body = decompressed[start:end]
            records = partition_top_level_actions(body)["records"]
            record_by_start = {r.start: r for r in records}
            edges, effects = {}, {}
            for rec in records:
                if rec.opcode == 0x96:
                    counts = _push_type_counts(body[rec.start + 3:rec.end])
                    if counts is None:
                        raise ValueError("Complete CFG contains invalid ActionPush")
                    effects[rec.start] = (0, sum(counts.values()))
                else:
                    if rec.opcode not in STACK_EFFECTS:
                        raise ValueError("Complete CFG contains unmodeled opcode")
                    effects[rec.start] = STACK_EFFECTS[rec.opcode]
                if rec.opcode in TERMINATORS:
                    edges[rec.start] = ()
                elif rec.opcode in (0x99, 0x9D):
                    branch = branch_index.get((start, start + rec.start))
                    if branch is None or branch["target_classification"] not in ("record_start", "body_end"):
                        raise ValueError("Missing verified branch target")
                    target = branch["target_offset_uncompressed"] - start
                    edges[rec.start] = (target, rec.end) if rec.opcode == 0x9D else (target,)
                else:
                    edges[rec.start] = (rec.end,)
            pending = deque([(records[0].start, 0)] if records else [])
            seen = set()
            entry_depths = defaultdict(set)
            potential_underflows = set()
            maximum = 0
            limit_reached = False
            while pending:
                offset, depth = pending.popleft()
                if offset == len(body) or (offset, depth) in seen:
                    continue
                if offset not in record_by_start:
                    raise ValueError("Candidate edge is not a source record boundary")
                if len(seen) >= max_states or depth > max_depth:
                    limit_reached = True
                    break
                seen.add((offset, depth))
                entry_depths[offset].add(depth)
                maximum = max(maximum, depth)
                pops, pushes = effects[offset]
                if depth < pops:
                    potential_underflows.add(offset)
                    continue
                next_depth = depth - pops + pushes
                maximum = max(maximum, next_depth)
                if next_depth > max_depth:
                    limit_reached = True
                    break
                pending.extend((target, next_depth) for target in edges[offset])
            result.update({
                "stack_status": "analysis_limit_reached" if limit_reached else "bounded_candidate_paths",
                "explored_candidate_state_count": len(seen),
                "potential_underflow_record_count": len(potential_underflows),
                "divergent_entry_depth_record_count": sum(len(v) > 1 for v in entry_depths.values()),
                "max_candidate_stack_depth": maximum,
            })
            statuses[result["stack_status"]] += 1
            output.append(result)
    if len(output) != cfg["function_body_count"]:
        raise ValueError("Stack audit function coverage mismatch")
    return {
        "source_sha256": source_sha256,
        "function_body_count": len(output),
        "stack_status_counts": dict(statuses),
        "explored_candidate_state_total": sum(r["explored_candidate_state_count"] or 0 for r in output),
        "potential_underflow_record_total": sum(r["potential_underflow_record_count"] or 0 for r in output),
        "divergent_entry_depth_record_total": sum(r["divergent_entry_depth_record_count"] or 0 for r in output),
        "runtime_stack_verified": False,
        "decompiled_semantics_verified": False,
        "records": output,
        "limitations": [
            "The function entry operand stack is assumed empty, not observed at runtime.",
            "Both ActionIf edges are followed, including potentially infeasible paths.",
            "Potential underflow and depth divergence are static candidates, not VM failures.",
            "Exploration is bounded by state/depth caps; reaching either cap is explicitly incomplete.",
            "No pushed values, source text, SWF bytes, gameplay, or FFDec semantic equivalence are emitted or verified.",
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
    report = audit_stack_candidates(json.loads(args.join.read_text(encoding="utf-8")), data, sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
