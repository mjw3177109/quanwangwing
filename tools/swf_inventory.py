#!/usr/bin/env python3
"""Lossless SWF structure inventory (metadata only; does not decompile scripts).

All offsets refer to the *uncompressed* SWF byte stream. The original file is
never modified. For a compressed CWS file, offsets are not on-disk offsets.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zlib

MAX_UNCOMPRESSED = 256 * 1024 * 1024

TAG_NAMES = {
    0: "End", 1: "ShowFrame", 2: "DefineShape", 4: "PlaceObject",
    5: "RemoveObject", 6: "DefineBits", 7: "DefineButton",
    9: "SetBackgroundColor", 10: "DefineFont", 11: "DefineText",
    12: "DoAction", 13: "DefineFontInfo", 14: "DefineSound",
    15: "StartSound", 17: "DefineButtonSound", 18: "SoundStreamHead",
    19: "SoundStreamBlock", 20: "DefineBitsLossless",
    21: "DefineBitsJPEG2", 22: "DefineShape2", 23: "DefineButtonCxform",
    24: "Protect", 26: "PlaceObject2", 28: "RemoveObject2",
    32: "DefineShape3", 33: "DefineText2", 34: "DefineButton2",
    35: "DefineBitsJPEG3", 36: "DefineBitsLossless2",
    37: "DefineEditText", 39: "DefineSprite", 43: "FrameLabel",
    45: "SoundStreamHead2", 46: "DefineMorphShape", 48: "DefineFont2",
    56: "ExportAssets", 57: "ImportAssets", 59: "DoInitAction",
    60: "DefineVideoStream", 61: "VideoFrame", 62: "DefineFontInfo2",
    66: "SetTabIndex", 69: "FileAttributes", 70: "PlaceObject3",
    71: "ImportAssets2", 73: "DefineFontAlignZones",
    74: "CSMTextSettings", 75: "DefineFont3", 76: "SymbolClass",
    77: "Metadata", 78: "DefineScalingGrid", 82: "DoABC",
    83: "DefineShape4", 84: "DefineMorphShape2",
    86: "DefineSceneAndFrameLabelData", 87: "DefineBinaryData",
    88: "DefineFontName", 89: "StartSound2", 90: "DefineBitsJPEG4",
    91: "DefineFont4", 93: "EnableTelemetry",
}
DEFINE_WITH_ID = {
    2, 6, 7, 10, 11, 14, 20, 21, 22, 32, 33, 34, 35, 36, 37,
    39, 46, 48, 60, 75, 83, 84, 87, 90, 91,
}
SCRIPT_TAGS = {12, 59, 72, 82}


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def read_rect(data: bytes, offset: int = 8) -> tuple[list[int], int]:
    if offset >= len(data):
        raise ValueError("Truncated SWF RECT")
    nbits = data[offset] >> 3
    bitcount = 5 + 4 * nbits
    nbytes = (bitcount + 7) // 8
    if nbits == 0 or offset + nbytes > len(data):
        raise ValueError("Invalid SWF RECT")
    value = int.from_bytes(data[offset:offset + nbytes], "big")
    padding = nbytes * 8 - bitcount
    values = []
    for i in range(4):
        shift = padding + (3 - i) * nbits
        values.append(_signed((value >> shift) & ((1 << nbits) - 1), nbits))
    return values, offset + nbytes


def load_swf(path: Path) -> tuple[bytes, str]:
    raw = path.read_bytes()
    if len(raw) < 8:
        raise ValueError("Truncated SWF header")
    signature = raw[:3]
    if signature not in (b"FWS", b"CWS", b"ZWS"):
        raise ValueError("Invalid SWF signature")
    expected = struct.unpack_from("<I", raw, 4)[0]
    if expected > MAX_UNCOMPRESSED:
        raise ValueError("Declared SWF exceeds 256 MiB safety limit")
    if signature == b"ZWS":
        raise ValueError("ZWS/LZMA requires a separate decoder; no incomplete manifest generated")
    if signature == b"CWS":
        decompressor = zlib.decompressobj()
        body = decompressor.decompress(raw[8:], MAX_UNCOMPRESSED)
        if not decompressor.eof or decompressor.unconsumed_tail:
            raise ValueError("Incomplete or oversized CWS zlib stream")
        data = b"FWS" + raw[3:8] + body
    else:
        data = raw
    if len(data) != expected:
        raise ValueError(f"SWF length mismatch: declared {expected}, decoded {len(data)}")
    return data, signature.decode("ascii")


def _names(payload: bytes) -> list[dict]:
    if len(payload) < 2:
        raise ValueError("Truncated symbol/export count")
    count = struct.unpack_from("<H", payload, 0)[0]
    pos = 2
    entries = []
    for _ in range(count):
        if pos + 2 > len(payload):
            raise ValueError("Truncated symbol/export id")
        character_id = struct.unpack_from("<H", payload, pos)[0]
        pos += 2
        end = payload.find(b"\x00", pos)
        if end < 0:
            raise ValueError("Unterminated symbol/export name")
        name = payload[pos:end].decode("utf-8", errors="replace")
        entries.append({"character_id": character_id, "name": name})
        pos = end + 1
    return entries


def inventory(path: Path) -> dict:
    data, signature = load_swf(path)
    rect, pos = read_rect(data)
    if pos + 4 > len(data):
        raise ValueError("Truncated frame metadata")
    frame_rate = struct.unpack_from("<H", data, pos)[0] / 256
    frame_count = struct.unpack_from("<H", data, pos + 2)[0]
    tag_start = pos + 4
    counts = Counter()
    records = []
    symbols = []
    exports = []
    scripts = []
    characters = []

    def parse_tags(start: int, end: int, timeline: str, depth: int = 0) -> None:
        if depth > 32:
            raise ValueError("SWF sprite nesting exceeds 32")
        p = start
        frame = 0
        saw_end = False
        while p < end:
            if p + 2 > end:
                raise ValueError(f"Truncated tag header at {p}")
            offset = p
            short = struct.unpack_from("<H", data, p)[0]
            p += 2
            code, size = short >> 6, short & 0x3f
            if size == 0x3f:
                if p + 4 > end:
                    raise ValueError(f"Truncated long tag size at {p}")
                size = struct.unpack_from("<I", data, p)[0]
                p += 4
            body_start = p
            body_end = p + size
            if body_end > end:
                raise ValueError(f"Tag {code} exceeds timeline boundary at {offset}")
            payload = data[body_start:body_end]
            entry = {
                "timeline": timeline, "frame": frame, "tag_code": code,
                "tag_name": TAG_NAMES.get(code, f"Unknown_{code}"),
                "offset_uncompressed": offset, "body_offset_uncompressed": body_start,
                "length": size,
            }
            if code in DEFINE_WITH_ID and len(payload) >= 2:
                character_id = struct.unpack_from("<H", payload, 0)[0]
                entry["character_id"] = character_id
                characters.append({
                    "character_id": character_id, "tag_code": code,
                    "tag_name": entry["tag_name"], "timeline": timeline,
                    "offset_uncompressed": offset,
                })
            if code == 76:
                symbols.extend(_names(payload))
            elif code == 56:
                exports.extend(_names(payload))
            if code in SCRIPT_TAGS:
                scripts.append({
                    "tag_code": code, "tag_name": entry["tag_name"],
                    "timeline": timeline, "frame": frame,
                    "offset_uncompressed": offset, "length": size,
                })
            counts[str(code)] += 1
            records.append(entry)
            if code == 39:
                if len(payload) < 4:
                    raise ValueError("Truncated DefineSprite")
                sprite_id, sprite_frames = struct.unpack_from("<HH", payload, 0)
                entry["sprite_frame_count"] = sprite_frames
                parse_tags(body_start + 4, body_end, f"sprite:{sprite_id}", depth + 1)
            p = body_end
            if code == 1:
                frame += 1
            if code == 0:
                saw_end = True
                if p != end:
                    raise ValueError(f"Trailing bytes after End tag in {timeline}")
                break
        if not saw_end:
            raise ValueError(f"Missing End tag in {timeline}")

    parse_tags(tag_start, len(data), "main")
    return {
        "source": {
            "filename": path.name, "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "signature": signature, "swf_version": data[3],
            "uncompressed_length": len(data),
        },
        "stage": {
            "rect_twips": rect, "width_px": (rect[1] - rect[0]) / 20,
            "height_px": (rect[3] - rect[2]) / 20,
            "frame_rate": frame_rate, "frame_count": frame_count,
        },
        "tag_count_including_sprites": len(records),
        "tag_counts_by_code": dict(sorted(counts.items(), key=lambda p: int(p[0]))),
        "characters": characters, "symbol_class": symbols,
        "export_assets": exports, "scripts": scripts, "tags": records,
        "notes": [
            "This is structural metadata; it does not reconstruct ActionScript semantics.",
            "All tag offsets refer to the decompressed FWS representation.",
            "Assets and script bodies are not included in this JSON.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, default=Path(__file__).resolve().parents[1] / "拳皇wing1.4.swf")
    parser.add_argument("--output", type=Path, default=Path("build/swf-analysis/swf-manifest.json"))
    args = parser.parse_args()
    result = inventory(args.swf.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "source": result["source"], "stage": result["stage"],
        "tag_count": result["tag_count_including_sprites"],
        "character_count": len(result["characters"]),
        "symbol_count": len(result["symbol_class"]),
        "script_tag_count": len(result["scripts"]),
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
