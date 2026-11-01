#!/usr/bin/env python3
"""Audit bytes after the first ActionEnd in verified DefineButton2 streams.

Trailing bytes are NOT presumed executable. Only bounded structural metadata
is emitted; original operand bytes and scripts remain local.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from build_button_opcode_evidence import build_button_opcode_evidence, walk_action_records


def first_action_end_offset(payload: bytes) -> int | None:
    """Locate the first opcode-boundary ActionEnd, skipping long operands."""
    pos = 0
    while pos < len(payload):
        opcode = payload[pos]
        if opcode == 0:
            return pos
        if opcode < 0x80:
            pos += 1
        else:
            if pos + 3 > len(payload):
                return None
            operand_length = struct.unpack_from("<H", payload, pos + 1)[0]
            pos += 3 + operand_length
            if pos > len(payload):
                return None
    return None


def build_button_tail_evidence(manifest: dict, buttons: dict, opcode_report: dict,
                               data: bytes) -> dict:
    # Recompute the upstream audit from original bytes: do not trust supplied
    # metadata counts or offsets without source-structure verification.
    verified = build_button_opcode_evidence(manifest, buttons, data)
    if opcode_report != verified:
        raise ValueError("Button opcode report does not match verified SWF bytes")
    definitions = {b["character_id"]: b for b in buttons["buttons"]}
    records = {
        (b["character_id"], r["offset_uncompressed"]): r
        for b in buttons["buttons"] for r in b["embedded_action_records"]
    }
    if len(records) != buttons["embedded_action_record_count"]:
        raise ValueError("Duplicate ButtonCondAction record offsets")
    rows = []
    byte_classes = Counter()
    candidate_statuses = Counter()
    zero_total = 0
    nonzero_total = 0
    for event in verified["records"]:
        if event["parse_status"] != "early_action_end_with_trailing_bytes":
            continue
        cid = event["button_character_id"]
        offset = event["action_offset_uncompressed"]
        record = records[(cid, offset)]
        length = record["action_bytes_including_terminator"]
        payload = data[offset + 4:offset + 4 + length]
        end_pos = first_action_end_offset(payload)
        if end_pos is None:
            raise ValueError("Expected first ActionEnd not found")
        tail = payload[end_pos + 1:]
        if not tail or len(tail) != event["unparsed_tail_bytes"]:
            raise ValueError("ActionEnd tail length mismatch")
        zeros = tail.count(0)
        nonzeros = len(tail) - zeros
        byte_class = ("zero_only" if nonzeros == 0 else
                      "nonzero_only" if zeros == 0 else "mixed")
        # This is a syntactic probe starting AFTER an ActionEnd, not an
        # executable control-flow or function classification.
        _, candidate_count, candidate_status, candidate_remainder = walk_action_records(tail)
        rows.append({
            "button_character_id": cid,
            "action_offset_uncompressed": offset,
            "trailing_bytes": len(tail),
            "zero_byte_count": zeros,
            "nonzero_byte_count": nonzeros,
            "byte_class": byte_class,
            "post_end_candidate_record_count": candidate_count,
            "post_end_candidate_status": candidate_status,
            "post_end_candidate_unparsed_bytes": candidate_remainder,
            "runtime_reachability_verified": False,
        })
        byte_classes[byte_class] += 1
        candidate_statuses[candidate_status] += 1
        zero_total += zeros
        nonzero_total += nonzeros
    if (len(rows) != verified["parse_status_counts"]["early_action_end_with_trailing_bytes"]
            or zero_total + nonzero_total != verified["unparsed_tail_bytes"]):
        raise ValueError("Button ActionEnd tail accounting mismatch")
    return {
        "source_sha256": verified["source_sha256"],
        "embedded_action_record_count": verified["embedded_action_record_count"],
        "trailing_record_count": len(rows),
        "trailing_byte_total": zero_total + nonzero_total,
        "trailing_zero_byte_total": zero_total,
        "trailing_nonzero_byte_total": nonzero_total,
        "trailing_byte_class_counts": {k: byte_classes[k] for k in
                                       ("zero_only", "nonzero_only", "mixed")},
        "post_end_candidate_status_counts": dict(sorted(candidate_statuses.items())),
        "tail_records": rows,
        "limitations": [
            "Post-ActionEnd bytes are unparsed trailing regions, not proven executable instructions.",
            "A syntactically valid candidate walk does not establish control-flow reachability.",
            "No original operands, scripts, SWF, artwork or audio bytes are emitted.",
        ],
    }


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
    result = build_button_tail_evidence(
        manifest,
        json.loads(args.buttons.read_text(encoding="utf-8")),
        json.loads(args.opcodes.read_text(encoding="utf-8")),
        data,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("tail_records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
