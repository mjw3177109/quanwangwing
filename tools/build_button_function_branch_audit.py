#!/usr/bin/env python3
"""Audit source-backed static ActionJump/ActionIf targets inside button functions.

Structural metadata only; no Flash VM execution or FFDec equivalence claims.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from button_action_structure import ActionStructureError, partition_top_level_actions

CLASSES = ("record_start", "body_end", "outside_body", "non_record_boundary", "invalid_operand_length")


def audit_branches(join: dict, decompressed: bytes, source_sha256: str) -> dict:
    if join.get("source_sha256") != source_sha256:
        raise ValueError("SWF source SHA-256 mismatch")
    rows = join.get("records")
    if type(rows) is not list or len(rows) != join.get("compared_button_action_count"):
        raise ValueError("Button source coverage mismatch")
    if join.get("decompiled_semantics_verified") is not False or join.get("runtime_behavior_verified") is not False:
        raise ValueError("Unsupported semantic or runtime claim")
    counts = Counter({k: 0 for k in CLASSES})
    branches = []
    function_count = rejected_count = 0
    for row in rows:
        ranges = row.get("bytecode_function_body_ranges")
        if ranges is None:
            if row.get("comparison_class") != "source_partition_rejected":
                raise ValueError("Missing function body provenance")
            continue
        if type(ranges) is not list:
            raise ValueError("Invalid function body ranges")
        for item in ranges:
            function_count += 1
            start, end = item.get("body_start_uncompressed"), item.get("body_end_uncompressed")
            if (type(start) is not int or type(end) is not int or
                    start < 0 or end < start or end > len(decompressed) or
                    end - start != item.get("body_byte_length")):
                raise ValueError("Invalid source function body bounds")
            if item.get("body_partition_status") == "rejected":
                rejected_count += 1
                continue
            if item.get("body_partition_status") != "partitioned":
                raise ValueError("Unknown body partition status")
            body = decompressed[start:end]
            try:
                parsed = partition_top_level_actions(body)
            except ActionStructureError as exc:
                raise ValueError("Previously verified body no longer partitions") from exc
            records = parsed["records"]
            hist = dict(sorted(Counter(f"0x{rec.opcode:02x}" for rec in records).items()))
            if (len(records) != item.get("body_top_level_record_count") or
                    hist != item.get("body_opcode_histogram")):
                raise ValueError("Function body source opcode inventory mismatch")
            starts = {rec.start for rec in records}
            for rec in records:
                if rec.opcode not in (0x99, 0x9D):
                    continue
                if rec.header_end - rec.start != 5:
                    kind, target = "invalid_operand_length", None
                else:
                    displacement = struct.unpack_from("<h", body, rec.start + 3)[0]
                    target = rec.header_end + displacement
                    kind = ("body_end" if target == len(body) else
                            "record_start" if target in starts else
                            "outside_body" if target < 0 or target > len(body) else
                            "non_record_boundary")
                counts[kind] += 1
                branches.append({
                    "button_character_id": row["button_character_id"],
                    "function_body_start_uncompressed": start,
                    "branch_opcode": f"0x{rec.opcode:02x}",
                    "branch_offset_uncompressed": start + rec.start,
                    "target_offset_uncompressed": start + target if target is not None else None,
                    "target_classification": kind,
                    "execution_verified": False,
                })
    if function_count != join.get("bytecode_declared_function_total_on_partitioned_records"):
        raise ValueError("Function count mismatch")
    if rejected_count != join.get("bytecode_function_body_partition_status_counts", {}).get("rejected"):
        raise ValueError("Rejected body count mismatch")
    return {
        "source_sha256": source_sha256,
        "function_body_count": function_count,
        "rejected_function_body_count": rejected_count,
        "branch_record_count": len(branches),
        "branch_target_classification_counts": dict(counts),
        "decompiled_semantics_verified": False,
        "runtime_behavior_verified": False,
        "records": branches,
        "limitations": [
            "Targets are static byte offsets relative to the enclosing function body.",
            "An outside-body or non-boundary target is an audit finding, not a gameplay conclusion.",
            "No branch condition, stack, execution, FFDec equivalence or 1:1 behavior is verified.",
            "No ActionScript text, operand values, original bytes or media are emitted.",
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
    decompressed, _ = load_swf(args.swf)
    result = audit_branches(json.loads(args.join.read_text(encoding="utf-8")), decompressed, sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
