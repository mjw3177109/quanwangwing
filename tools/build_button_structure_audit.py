#!/usr/bin/env python3
"""Source-verified structural partition audit for DefineButton2 ActionRecord bytes.

Metadata only. A successful partition is NOT Flash runtime reachability.
Older flat opcode/tail/entry-graph reports remain provisional.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from build_button_opcode_evidence import build_button_opcode_evidence
from build_button_tail_evidence import first_action_end_offset
from button_action_structure import ActionStructureError, partition_top_level_actions


STATUSES = ("partitioned", "unsupported_nested_scope", "malformed_or_unsupported")


def summarize_partitions(buttons: dict, verified_opcodes: dict, data: bytes) -> dict:
    """Use previously byte-verified record offsets; never publish original bytes."""
    records = {}
    for button in buttons["buttons"]:
        cid = button["character_id"]
        for rec in button["embedded_action_records"]:
            key = (cid, rec["offset_uncompressed"])
            if key in records:
                raise ValueError("Duplicate source record offset")
            records[key] = rec
    entries = verified_opcodes["records"]
    if (len(records) != buttons["embedded_action_record_count"]
            or len(entries) != len(records)):
        raise ValueError("Button action record coverage mismatch")

    rows = []
    seen = set()
    status_counts = Counter({key: 0 for key in STATUSES})
    flat_end_disagreements = 0
    declared_functions = 0
    declared_body_bytes = 0
    post_end_records = 0
    missing_top_level_end = 0
    for event in entries:
        cid = event["button_character_id"]
        offset = event["action_offset_uncompressed"]
        key = (cid, offset)
        if key in seen or key not in records:
            raise ValueError("Unmatched or duplicate verified opcode entry")
        seen.add(key)
        length = records[key]["action_bytes_including_terminator"]
        if (type(offset) is not int or type(length) is not int
                or offset < 0 or length <= 0 or offset + 4 + length > len(data)):
            raise ValueError("Action payload out of verified SWF bounds")
        payload = data[offset + 4:offset + 4 + length]
        flat_end = first_action_end_offset(payload)
        row = {
            "button_character_id": cid,
            "action_offset_uncompressed": offset,
            "action_byte_length": length,
            "flat_first_end_offset": flat_end,
            "runtime_reachability_verified": False,
        }
        try:
            parsed = partition_top_level_actions(payload)
        except ActionStructureError as exc:
            status = ("unsupported_nested_scope"
                      if "Unsupported nested With/Try scope" in str(exc)
                      else "malformed_or_unsupported")
            row.update({
                "status": status,
                "top_level_partition_verified": False,
                "first_top_level_end_offset": None,
            })
        else:
            status = "partitioned"
            first_end = parsed["first_top_level_action_end_offset"]
            if first_end is None:
                missing_top_level_end += 1
            if first_end != flat_end:
                flat_end_disagreements += 1
            declared_functions += parsed["declared_function_count"]
            declared_body_bytes += parsed["declared_function_body_byte_total"]
            post_end_records += parsed["top_level_post_end_record_count"]
            row.update({
                "status": status,
                "top_level_partition_verified": True,
                "first_top_level_end_offset": first_end,
                "flat_first_end_matches_top_level": first_end == flat_end,
                "top_level_record_count": parsed["top_level_record_count"],
                "top_level_post_end_record_count": parsed["top_level_post_end_record_count"],
                "declared_function_count": parsed["declared_function_count"],
                "declared_function_body_byte_total": parsed["declared_function_body_byte_total"],
            })
        status_counts[status] += 1
        rows.append(row)
    if len(seen) != len(records):
        raise ValueError("Verified opcode entries omit source records")
    return {
        "source_sha256": verified_opcodes["source_sha256"],
        "embedded_action_record_count": len(rows),
        "partition_status_counts": dict(status_counts),
        "flat_first_end_disagreement_count": flat_end_disagreements,
        "partitioned_without_top_level_end_count": missing_top_level_end,
        "declared_function_count_in_partitioned_records": declared_functions,
        "declared_function_body_bytes_in_partitioned_records": declared_body_bytes,
        "top_level_post_end_record_count_in_partitioned_records": post_end_records,
        "runtime_reachability_verified": False,
        "records": rows,
        "limitations": [
            "The existing flat opcode, tail and entry graph reports remain provisional.",
            "Unsupported With/Try and malformed scopes are reported as unverified, not silently accepted.",
            "Syntactic post-End records are not proven reachable or executable.",
            "No original SWF, script, function names, operands, artwork or audio bytes are emitted.",
        ],
    }


def build_button_structure_audit(manifest: dict, buttons: dict, opcodes: dict,
                                 data: bytes) -> dict:
    verified = build_button_opcode_evidence(manifest, buttons, data)
    if verified != opcodes:
        raise ValueError("Opcode evidence differs from verified original SWF bytes")
    return summarize_partitions(buttons, verified, data)


def main() -> None:
    from swf_inventory import load_swf

    p = argparse.ArgumentParser()
    p.add_argument("--swf", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--buttons", type=Path, required=True)
    p.add_argument("--opcodes", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("SWF source SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    result = build_button_structure_audit(
        manifest,
        json.loads(args.buttons.read_text(encoding="utf-8")),
        json.loads(args.opcodes.read_text(encoding="utf-8")),
        data,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
