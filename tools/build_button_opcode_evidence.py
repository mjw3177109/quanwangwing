#!/usr/bin/env python3
"""Metadata-only audit of legacy ActionRecord framing in DefineButton2."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from build_button_action_evidence import _verify_tag

STATUSES = (
    "terminated_at_end", "early_action_end_with_trailing_bytes",
    "missing_action_end", "truncated_extended_header",
    "extended_payload_out_of_bounds",
)


def walk_action_records(payload):
    """Read opcode boundaries, never emit original operands or infer behavior."""
    counts = Counter()
    pos = 0
    parsed = 0
    while pos < len(payload):
        opcode = payload[pos]
        if opcode == 0:
            pos += 1
            return counts, parsed, ("terminated_at_end" if pos == len(payload)
                                    else "early_action_end_with_trailing_bytes"), len(payload) - pos
        if opcode >= 0x80:
            if pos + 3 > len(payload):
                return counts, parsed, "truncated_extended_header", len(payload) - pos
            length = struct.unpack_from("<H", payload, pos + 1)[0]
            next_pos = pos + 3 + length
            if next_pos > len(payload):
                return counts, parsed, "extended_payload_out_of_bounds", len(payload) - pos
        else:
            next_pos = pos + 1
        counts[f"0x{opcode:02X}"] += 1
        parsed += 1
        pos = next_pos
    return counts, parsed, "missing_action_end", 0


def build_button_opcode_evidence(manifest, buttons, data):
    source = manifest.get("source", {}).get("sha256")
    if not isinstance(source, str) or len(source) != 64 or any(c not in "0123456789abcdef" for c in source):
        raise ValueError("Invalid source hash")
    if buttons.get("source_sha256") != source:
        raise ValueError("Button evidence source mismatch")
    tags = {t.get("character_id"): t for t in manifest.get("tags", []) if t.get("tag_code") == 34}
    if len(tags) != manifest.get("tag_counts_by_code", {}).get("34", 0):
        raise ValueError("DefineButton2 inventory mismatch")
    rows = buttons.get("buttons")
    if not isinstance(rows, list) or len(rows) != len(tags):
        raise ValueError("Button evidence coverage mismatch")
    opcode_counts = Counter()
    status_counts = Counter({key: 0 for key in STATUSES})
    action_bytes = 0
    parsed_records = 0
    unparsed_bytes = 0
    entries = []
    seen = set()
    for row in rows:
        cid = row.get("character_id")
        if type(cid) is not int or cid not in tags or cid in seen:
            raise ValueError("Unknown or duplicate button ID")
        seen.add(cid)
        tag = tags[cid]
        body, end = _verify_tag(data, tag)
        if (row.get("tag_offset_uncompressed") != tag.get("offset_uncompressed")
                or row.get("timeline") != tag.get("timeline")
                or row.get("frame_zero_based") != tag.get("frame")):
            raise ValueError("Button definition provenance mismatch")
        if struct.unpack_from("<H", data, body)[0] != cid:
            raise ValueError("Button ID bytes mismatch")
        records = row.get("embedded_action_records")
        if not isinstance(records, list) or row.get("embedded_action_record_count") != len(records):
            raise ValueError("Embedded action record coverage mismatch")
        previous_end = None
        for record in records:
            offset = record.get("offset_uncompressed")
            length = record.get("action_bytes_including_terminator")
            flags = record.get("condition_flags")
            if (type(offset) is not int or type(length) is not int or type(flags) is not int
                    or offset < body + 6 or length <= 0 or not 0 <= flags <= 65535
                    or offset + 4 + length > end):
                raise ValueError("Invalid ButtonCondAction bounds")
            if previous_end is not None and offset != previous_end:
                raise ValueError("Noncontiguous ButtonCondAction records")
            raw_size, raw_flags = struct.unpack_from("<HH", data, offset)
            if raw_flags != flags or (raw_size == 0) != (record.get("is_last_by_zero_size") is True):
                raise ValueError("ButtonCondAction header mismatch")
            next_pos = offset + 4 + length
            if raw_size and raw_size != 4 + length:
                raise ValueError("ButtonCondAction size mismatch")
            if raw_size == 0 and next_pos != end:
                raise ValueError("Final ButtonCondAction does not cover tag")
            payload = data[offset + 4:next_pos]
            if (payload[-1] == 0) != record.get("ends_with_action_end"):
                raise ValueError("ActionEnd provenance mismatch")
            opcodes, count, status, tail = walk_action_records(payload)
            opcode_counts.update(opcodes)
            status_counts[status] += 1
            action_bytes += length
            parsed_records += count
            unparsed_bytes += tail
            entries.append({"button_character_id": cid, "action_offset_uncompressed": offset,
                            "condition_flags": flags, "parse_status": status,
                            "parsed_opcode_count": count, "unparsed_tail_bytes": tail})
            previous_end = next_pos
        if records and previous_end != end:
            raise ValueError("Button action area not fully covered")
    if len(seen) != len(tags) or len(entries) != buttons.get("embedded_action_record_count"):
        raise ValueError("Button action inventory incomplete")
    if action_bytes != buttons.get("embedded_action_bytes"):
        raise ValueError("Button action byte total mismatch")
    return {
        "source_sha256": source,
        "button_definition_count": len(tags),
        "embedded_action_record_count": len(entries),
        "embedded_action_bytes": action_bytes,
        "parsed_opcode_count": parsed_records,
        "unparsed_tail_bytes": unparsed_bytes,
        "opcode_histogram": dict(sorted(opcode_counts.items())),
        "parse_status_counts": dict(status_counts),
        "records": entries,
        "limitations": [
            "Opcode framing is structural evidence, not AS1/AS2 function or game behavior classification.",
            "A first ActionEnd may leave trailing bytes; these are not interpreted as executed instructions.",
            "No original operand bytes, ActionScript source, SWF, artwork, music or audio are emitted.",
        ],
    }


def main():
    from swf_inventory import load_swf
    p = argparse.ArgumentParser()
    p.add_argument("--swf", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--buttons", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    raw = args.swf.read_bytes()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != manifest.get("source", {}).get("sha256"):
        raise SystemExit("SWF source SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    buttons = json.loads(args.buttons.read_text(encoding="utf-8"))
    result = build_button_opcode_evidence(manifest, buttons, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
