#!/usr/bin/env python3
"""Byte-verify DefineButton2 embedded legacy action containers; emit metadata only.

ActionOffset is relative to the start of its two-byte field. CondActionSize
is relative to its own two-byte field; zero denotes the final record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


def _verify_tag(data: bytes, tag: dict) -> tuple[int, int]:
    offset, body, size = (tag.get(k) for k in
                          ("offset_uncompressed", "body_offset_uncompressed", "length"))
    if any(type(v) is not int or v < 0 for v in (offset, body, size)):
        raise ValueError("Invalid DefineButton2 tag metadata")
    if offset + 2 > len(data):
        raise ValueError("DefineButton2 header out of bounds")
    word = struct.unpack_from("<H", data, offset)[0]
    code, actual_size = word >> 6, word & 63
    header_size = 2
    if actual_size == 63:
        if offset + 6 > len(data):
            raise ValueError("Truncated long DefineButton2 header")
        actual_size = struct.unpack_from("<I", data, offset + 2)[0]
        header_size = 6
    if (code != 34 or tag.get("tag_code") != 34 or actual_size != size
            or body != offset + header_size or body + size > len(data)):
        raise ValueError("DefineButton2 manifest/header mismatch")
    if size < 6:
        raise ValueError("Truncated DefineButton2 body")
    return body, body + size


def build_button_action_evidence(manifest: dict, data: bytes) -> dict:
    tags = [tag for tag in manifest.get("tags", []) if tag.get("tag_code") == 34]
    if len(tags) != manifest.get("tag_counts_by_code", {}).get("34", 0):
        raise ValueError("DefineButton2 tag count mismatch")
    rows = []
    record_total = 0
    action_bytes_total = 0
    with_actions = 0
    without_final_end = 0
    nonzero_last_size = 0
    for tag in tags:
        body, end = _verify_tag(data, tag)
        character_id, = struct.unpack_from("<H", data, body)
        action_offset, = struct.unpack_from("<H", data, body + 3)
        if character_id != tag.get("character_id"):
            raise ValueError("DefineButton2 character ID mismatch")
        events = []
        if action_offset:
            with_actions += 1
            first = body + 3 + action_offset
            if first < body + 6 or first + 4 > end:
                raise ValueError("DefineButton2 ActionOffset out of bounds")
            cursor = first
            while cursor < end:
                if cursor + 4 > end:
                    raise ValueError("Truncated ButtonCondAction header")
                size, conditions = struct.unpack_from("<HH", data, cursor)
                next_cursor = end if size == 0 else cursor + size
                if next_cursor <= cursor + 4 or next_cursor > end:
                    raise ValueError("Invalid ButtonCondAction size")
                ends_with_action_end = data[next_cursor - 1] == 0
                if not ends_with_action_end:
                    without_final_end += 1
                action_bytes = next_cursor - (cursor + 4)
                action_bytes_total += action_bytes
                record_total += 1
                events.append({
                    "offset_uncompressed": cursor,
                    "condition_flags": conditions,
                    "action_bytes_including_terminator": action_bytes,
                    "ends_with_action_end": ends_with_action_end,
                    "is_last_by_zero_size": size == 0,
                })
                cursor = next_cursor
                if size == 0:
                    break
            if cursor != end:
                raise ValueError("ButtonCondAction records do not cover action area")
            if events and not events[-1]["is_last_by_zero_size"]:
                nonzero_last_size += 1
        rows.append({
            "character_id": character_id,
            "timeline": tag.get("timeline"),
            "frame_zero_based": tag.get("frame"),
            "tag_offset_uncompressed": tag["offset_uncompressed"],
            "action_offset": action_offset,
            "embedded_action_record_count": len(events),
            "embedded_action_records": events,
        })
    if record_total != sum(r["embedded_action_record_count"] for r in rows):
        raise ValueError("Button action record accounting mismatch")
    return {
        "source_sha256": manifest["source"]["sha256"],
        "define_button2_count": len(rows),
        "buttons_with_actions": with_actions,
        "buttons_without_actions": len(rows) - with_actions,
        "embedded_action_record_count": record_total,
        "embedded_action_bytes": action_bytes_total,
        "records_without_terminal_action_end": without_final_end,
        "buttons_without_zero_sized_final_record": nonzero_last_size,
        "buttons": rows,
        "limitations": [
            "ButtonCondAction is an embedded legacy-action container, not a function or move count.",
            "Condition flags are raw metadata, not a proven button/input behavior map.",
            "ActionEnd byte checks are structural hints; embedded ActionRecord opcodes are not decoded.",
            "No AS1/AS2 distinction, original scripts, art, audio or source SWF bytes are emitted.",
        ],
    }


def main() -> None:
    from swf_inventory import load_swf
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, default=Path(__file__).resolve().parents[1] / "拳皇wing1.4.swf")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("SWF source SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    result = build_button_action_evidence(manifest, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("buttons", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
