#!/usr/bin/env python3
"""Audit SWF script container tags and entry frames without publishing bytecode.

Tag 12/59 contains legacy AS1/AS2 actions; tag 72/82 is ABC-bearing.
A container count is NOT a function count, nor an AS1-vs-AS2 distinction.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from swf_inventory import load_swf

SCRIPT_CODES = {12, 59, 72, 82}


def _check_tag(data: bytes, entry: dict) -> None:
    offset = entry["offset_uncompressed"]
    body = entry["body_offset_uncompressed"]
    size = entry["length"]
    code = entry["tag_code"]
    if any(type(v) is not int or v < 0 for v in (offset, body, size, code)):
        raise ValueError("Invalid tag offset, code or length")
    if offset + 2 > len(data):
        raise ValueError("Tag header out of bounds")
    word = struct.unpack_from("<H", data, offset)[0]
    observed_code, observed_size = word >> 6, word & 63
    header_size = 2
    if observed_size == 63:
        if offset + 6 > len(data):
            raise ValueError("Long tag header out of bounds")
        observed_size = struct.unpack_from("<I", data, offset + 2)[0]
        header_size = 6
    if (observed_code != code or observed_size != size or
            body != offset + header_size or body + size > len(data)):
        raise ValueError("Manifest tag does not match SWF bytes")


def build_script_entry_evidence(manifest: dict, data: bytes) -> dict:
    tags = manifest["tags"]
    scripts = manifest["scripts"]
    expected = [{k: t[k] for k in ("tag_code", "tag_name", "timeline", "frame",
                                    "offset_uncompressed", "length")}
                | ({"init_target_sprite_id": t["init_target_sprite_id"]}
                   if t["tag_code"] == 59 else {})
                for t in tags if t["tag_code"] in SCRIPT_CODES]
    if expected != scripts:
        raise ValueError("Script inventory and tag list disagree")
    file_attrs = [t for t in tags if t["tag_code"] == 69]
    for t in tags:
        if t["tag_code"] in SCRIPT_CODES or t["tag_code"] == 69:
            _check_tag(data, t)
    flags = []
    for t in file_attrs:
        if t["length"] != 4:
            raise ValueError("Invalid FileAttributes length")
        flags.append(struct.unpack_from("<I", data, t["body_offset_uncompressed"])[0])
    if len(set(flags)) > 1:
        raise ValueError("Conflicting FileAttributes tags")
    counts = Counter(str(t["tag_code"]) for t in scripts)
    entries = []
    for t in scripts:
        if type(t["frame"]) is not int or t["frame"] < 0 or not isinstance(t["timeline"], str):
            raise ValueError("Invalid script timeline/frame")
        event = {"timeline": t["timeline"], "frame_zero_based": t["frame"],
                 "frame_one_based": t["frame"] + 1, "tag_code": t["tag_code"],
                 "offset_uncompressed": t["offset_uncompressed"],
                 "length": t["length"]}
        if t["tag_code"] == 59:
            event["init_target_sprite_id"] = t["init_target_sprite_id"]
        entries.append(event)
    return {
        "source_sha256": manifest["source"]["sha256"],
        "script_container_count": len(entries),
        "script_container_counts_by_tag": dict(sorted(counts.items(), key=lambda x: int(x[0]))),
        "legacy_action_container_count": counts["12"] + counts["59"],
        "abc_container_count": counts["72"] + counts["82"],
        "file_attributes_count": len(flags),
        "file_attributes_as3_flag": bool(flags[0] & 0x08) if flags else None,
        "entries": entries,
        "limitations": [
            "Tag 12/59 containers cannot distinguish AS1 from AS2 or count functions.",
            "Tag 72/82 counts are ABC-bearing containers, not AS3 classes or methods.",
            "FileAttributes AS3 bit is a declaration, not proof of runtime execution.",
            "Button embedded actions, dynamic code and externally loaded SWFs are not enumerated.",
            "Offsets are in decompressed SWF bytes; no script or asset payload is emitted.",
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
        raise SystemExit("SWF source SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    report = build_script_entry_evidence(manifest, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("script_container_count", "legacy_action_container_count",
                                             "abc_container_count", "file_attributes_as3_flag")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
