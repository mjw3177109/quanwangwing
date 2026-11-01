#!/usr/bin/env python3
"""Source-verified, metadata-only button entry graphs from original SWF bytes.

This is syntactic analysis, not Flash VM execution or 1:1 validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from build_button_structure_audit import build_button_structure_audit
from button_action_structure import ActionStructureError
from button_partitioned_entry_graph import (
    TARGET_CLASSES, audit_partitioned_entry_graph,
)

STATUSES = (
    "verified_graph", "unsupported_nested_scope", "malformed_or_unsupported",
    "missing_top_level_end", "graph_rejected",
)
KINDS = ("jump", "if")


def build_source_partitioned_graph(manifest: dict, buttons: dict,
                                   opcodes: dict, data: bytes) -> dict:
    """Reverify opcode bytes and map every ButtonCondAction exactly once."""
    structure = build_button_structure_audit(manifest, buttons, opcodes, data)
    if structure["source_sha256"] != opcodes["source_sha256"]:
        raise ValueError("Source provenance mismatch")
    source = {}
    for button in buttons["buttons"]:
        cid = button["character_id"]
        for record in button["embedded_action_records"]:
            key = (cid, record["offset_uncompressed"])
            if key in source:
                raise ValueError("Duplicate source button action")
            source[key] = record
    if len(source) != structure["embedded_action_record_count"]:
        raise ValueError("Source action coverage mismatch")

    statuses = Counter({name: 0 for name in STATUSES})
    classes = Counter({name: 0 for name in TARGET_CLASSES})
    kinds = Counter({name: 0 for name in KINDS})
    rows = []
    visited_total = post_end_total = paths = 0
    for item in structure["records"]:
        cid, offset = item["button_character_id"], item["action_offset_uncompressed"]
        key = (cid, offset)
        if key not in source:
            raise ValueError("Missing or duplicate verified source action")
        record = source.pop(key)
        length = record["action_bytes_including_terminator"]
        if length != item["action_byte_length"] or offset < 0 or length <= 0:
            raise ValueError("Source action length mismatch")
        start, stop = offset + 4, offset + 4 + length
        if stop > len(data):
            raise ValueError("Source action exceeds SWF bounds")
        row = {
            "button_character_id": cid,
            "action_offset_uncompressed": offset,
            "status": None,
            "graph_verified": False,
            "runtime_reachability_verified": False,
        }
        if item["status"] != "partitioned":
            status = item["status"]
            if status not in STATUSES:
                raise ValueError("Unexpected structural partition status")
        elif item["first_top_level_end_offset"] is None:
            status = "missing_top_level_end"
        else:
            try:
                graph = audit_partitioned_entry_graph(data[start:stop])
            except (ActionStructureError, ValueError):
                status = "graph_rejected"
            else:
                if (graph["top_level_record_count"] != item["top_level_record_count"]
                        or graph["declared_function_count"] != item["declared_function_count"]
                        or graph["declared_function_body_byte_total"] !=
                        item["declared_function_body_byte_total"]
                        or not graph["top_level_partition_verified"]
                        or graph["runtime_reachability_verified"]):
                    raise ValueError("Graph disagrees with verified structural partition")
                branch_classes = graph["visited_branch_target_class_counts"]
                branch_kinds = graph["visited_branch_kind_counts"]
                if (set(branch_classes) != set(TARGET_CLASSES)
                        or set(branch_kinds) != set(KINDS)
                        or sum(branch_classes.values()) != sum(branch_kinds.values())
                        or graph["visited_record_count"] > graph["top_level_record_count"]):
                    raise ValueError("Graph histogram accounting mismatch")
                status = "verified_graph"
                row.update({
                    "graph_verified": True,
                    "visited_record_count": graph["visited_record_count"],
                    "visited_post_end_record_count": graph["visited_post_end_record_count"],
                    "syntactic_entry_path_to_post_end_record":
                        graph["syntactic_entry_path_to_post_end_record"],
                    "visited_branch_kind_counts": branch_kinds,
                    "visited_branch_target_class_counts": branch_classes,
                })
                visited_total += graph["visited_record_count"]
                post_end_total += graph["visited_post_end_record_count"]
                paths += int(graph["syntactic_entry_path_to_post_end_record"])
                kinds.update(branch_kinds)
                classes.update(branch_classes)
        row["status"] = status
        statuses[status] += 1
        rows.append(row)
    if source or len(rows) != structure["embedded_action_record_count"]:
        raise ValueError("Verified source action coverage incomplete")
    return {
        "source_sha256": structure["source_sha256"],
        "embedded_action_record_count": len(rows),
        "graph_status_counts": dict(statuses),
        "graph_verified_count": statuses["verified_graph"],
        "visited_record_total_in_verified_graphs": visited_total,
        "visited_post_end_record_total_in_verified_graphs": post_end_total,
        "graphs_with_syntactic_entry_path_to_post_end_record": paths,
        "visited_branch_kind_totals": dict(kinds),
        "visited_branch_target_class_totals": dict(classes),
        "runtime_reachability_verified": False,
        "records": rows,
        "limitations": [
            "Only structurally partitioned, successfully traversed graphs are verified.",
            "Rejected graphs are reported, never treated as successful.",
            "Syntactic paths do not establish Flash runtime execution.",
            "Conditions, WaitForFrame semantics and function calls are not evaluated.",
            "Legacy flat reports remain provisional and are not overwritten.",
            "No SWF, source code, operands, artwork or audio bytes are published.",
        ],
    }


def main() -> None:
    from swf_inventory import load_swf

    parser = argparse.ArgumentParser()
    for arg in ("swf", "manifest", "buttons", "opcodes", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("SWF source SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    result = build_source_partitioned_graph(
        manifest,
        json.loads(args.buttons.read_text(encoding="utf-8")),
        json.loads(args.opcodes.read_text(encoding="utf-8")),
        data,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
