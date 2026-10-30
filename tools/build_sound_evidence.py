#!/usr/bin/env python3
"""Audit SWF sound definitions and trigger locations, metadata only.

No audio data, SoundInfo envelopes, or source ActionScript are exported.
Frame indices are tag positions, not confirmed audible playback times.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

from build_script_entry_evidence import _check_tag
from swf_inventory import load_swf

SOUND_TAGS = {14, 15, 17, 18, 19, 45, 89}


def _sound_info_end(body: bytes, cursor: int) -> int:
    if cursor >= len(body):
        raise ValueError("Truncated SOUNDINFO flags")
    flags = body[cursor]
    cursor += 1
    if flags & 0x01:
        cursor += 4
    if flags & 0x02:
        cursor += 4
    if flags & 0x04:
        cursor += 2
    if cursor > len(body):
        raise ValueError("Truncated SOUNDINFO fields")
    if flags & 0x08:
        if cursor >= len(body):
            raise ValueError("Truncated SOUNDINFO envelope count")
        points = body[cursor]
        cursor += 1 + points * 8
    if cursor > len(body):
        raise ValueError("Truncated SOUNDINFO envelope")
    return cursor


def build_sound_evidence(manifest: dict, data: bytes) -> dict:
    names = defaultdict(list)
    for item in manifest["export_assets"] + manifest["symbol_class"]:
        names[item["character_id"]].append(item["name"])
    definitions = {}
    starts = []
    buttons = []
    streams = []
    blocks = []
    start_by_name = []
    latest_stream = {}
    counts = Counter()
    for tag in manifest["tags"]:
        code = tag["tag_code"]
        if code not in SOUND_TAGS:
            continue
        _check_tag(data, tag)
        body = data[tag["body_offset_uncompressed"]:tag["body_offset_uncompressed"] + tag["length"]]
        counts[str(code)] += 1
        at = {"timeline": tag["timeline"], "frame_zero_based": tag["frame"],
              "offset_uncompressed": tag["offset_uncompressed"]}
        if code == 14:
            if len(body) < 7:
                raise ValueError("Truncated DefineSound")
            sid = struct.unpack_from("<H", body)[0]
            if sid in definitions:
                raise ValueError("Duplicate DefineSound ID")
            flags = body[2]
            definitions[sid] = {"sound_id": sid, "format": flags >> 4,
                                "rate_code": (flags >> 2) & 3,
                                "sample_bits": 16 if flags & 2 else 8,
                                "channels": 2 if flags & 1 else 1,
                                "sample_count": struct.unpack_from("<I", body, 3)[0],
                                "export_names": names.get(sid, []), **at}
        elif code == 15:
            if len(body) < 3:
                raise ValueError("Truncated StartSound")
            sid = struct.unpack_from("<H", body)[0]
            if _sound_info_end(body, 2) != len(body):
                raise ValueError("Unexpected StartSound trailing data")
            starts.append({"sound_id": sid, "export_names": names.get(sid, []), **at})
        elif code == 17:
            if len(body) < 10:
                raise ValueError("Truncated DefineButtonSound")
            button_id = struct.unpack_from("<H", body)[0]
            cursor = 2
            for slot in ("over_up_to_idle", "idle_to_over_up", "over_up_to_over_down", "over_down_to_over_up"):
                if cursor + 2 > len(body):
                    raise ValueError("Truncated DefineButtonSound ID")
                sid = struct.unpack_from("<H", body, cursor)[0]
                cursor += 2
                if sid:
                    cursor = _sound_info_end(body, cursor)
                    buttons.append({"button_id": button_id, "transition": slot,
                                    "sound_id": sid, "export_names": names.get(sid, []), **at})
            if cursor != len(body):
                raise ValueError("Unexpected DefineButtonSound trailing data")
        elif code in (18, 45):
            if len(body) < 4:
                raise ValueError("Truncated SoundStreamHead")
            stream_flags = body[1]
            head = {"tag_code": code, "stream_format": stream_flags >> 4,
                    "stream_rate_code": (stream_flags >> 2) & 3,
                    "stream_sample_bits": 16 if stream_flags & 2 else 8,
                    "stream_channels": 2 if stream_flags & 1 else 1,
                    "samples_per_block": struct.unpack_from("<H", body, 2)[0], **at}
            streams.append(head)
            latest_stream[tag["timeline"]] = len(streams) - 1
        elif code == 19:
            blocks.append({"stream_head_index": latest_stream.get(tag["timeline"]),
                           "payload_length": tag["length"], **at})
        elif code == 89:
            terminator = body.find(b"\x00")
            if terminator < 0:
                raise ValueError("Unterminated StartSound2 class name")
            if _sound_info_end(body, terminator + 1) != len(body):
                raise ValueError("Unexpected StartSound2 trailing data")
            start_by_name.append({"class_name": body[:terminator].decode("utf-8", errors="replace"), **at})

    unresolved = sorted({r["sound_id"] for r in starts + buttons if r["sound_id"] not in definitions})
    return {
        "source_sha256": manifest["source"]["sha256"],
        "sound_tag_counts": dict(sorted(counts.items(), key=lambda x: int(x[0]))),
        "define_sound_count": len(definitions),
        "start_sound_count": len(starts),
        "button_sound_transition_count": len(buttons),
        "stream_head_count": len(streams),
        "stream_block_count": len(blocks),
        "start_sound2_count": len(start_by_name),
        "unresolved_sound_ids": unresolved,
        "stream_blocks_without_head": sum(b["stream_head_index"] is None for b in blocks),
        "definitions": [definitions[k] for k in sorted(definitions)],
        "start_events": starts,
        "button_transitions": buttons,
        "stream_heads": streams,
        "stream_blocks": blocks,
        "start_by_class_name": start_by_name,
        "limitations": [
            "Tag positions do not establish exact audible playback, latency or loop timing.",
            "Button transitions and stream headers are structural references, not decoded audio.",
            "No sound payload, SOUNDINFO envelope, BGM or effect audio is exported.",
            "Sound trigger events in ActionScript and external assets remain unresolved.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, default=Path(__file__).resolve().parents[1] / "拳皇wing1.4.swf")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("Sound evidence source SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    report = build_sound_evidence(manifest, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("define_sound_count", "start_sound_count", "button_sound_transition_count", "stream_head_count", "stream_block_count", "start_sound2_count", "stream_blocks_without_head")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
