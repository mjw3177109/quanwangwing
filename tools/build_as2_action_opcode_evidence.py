#!/usr/bin/env python3
"""Byte-verified legacy SWF action record inventory, without publishing bytecode.

Counts only top-level records in DoAction / DoInitAction tags. Function body
records are nested in payloads and intentionally not interpreted here.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from swf_inventory import load_swf
from build_script_entry_evidence import _check_tag

LEGACY_CODES = {12, 59}
INTERESTING = {0x1c: "GetVariable", 0x1d: "SetVariable", 0x3d: "CallFunction",
               0x40: "NewObject", 0x52: "CallMethod", 0x53: "NewMethod",
               0x88: "ConstantPool", 0x8e: "DefineFunction2", 0x8f: "Try",
               0x94: "With", 0x96: "Push", 0x99: "Jump", 0x9b: "DefineFunction",
               0x9d: "If"}


def _records(body):
    """Return opcode histogram and termination metadata; never decode payloads."""
    pos = 0
    counts = Counter()
    terminated = False
    while pos < len(body):
        opcode = body[pos]
        pos += 1
        if opcode == 0:
            terminated = True
            break
        if opcode >= 0x80:
            if pos + 2 > len(body):
                raise ValueError("Truncated long action length")
            size = struct.unpack_from("<H", body, pos)[0]
            pos += 2
            if pos + size > len(body):
                raise ValueError("Action payload exceeds container")
            pos += size
        counts[opcode] += 1
    return counts, terminated, len(body) - pos


def classify_trailing_bytes(body, trailing):
    """Classify bytes after top-level ActionEnd, without interpreting or emitting them."""
    if trailing < 0 or trailing > len(body):
        raise ValueError("Invalid trailing byte count")
    if not trailing:
        return "none"
    tail = body[-trailing:]
    zero_count = tail.count(0)
    if zero_count == trailing:
        return "zero_only"
    if zero_count == 0:
        return "nonzero_only"
    return "mixed"



def zero_position_mask(body, trailing):
    """Record only zero/nonzero positions; never expose ActionScript or byte values."""
    if trailing < 0 or trailing > len(body):
        raise ValueError("Invalid trailing byte count")
    return "".join("0" if value == 0 else "x" for value in body[-trailing:]) if trailing else ""


def walk_action_tail_shape_candidate(body, trailing):
    """Walk bounded record *shapes* after first ActionEnd, never returning opcodes or payload."""
    if trailing < 0 or trailing > len(body):
        raise ValueError("Invalid trailing byte count")
    if not trailing:
        return "none", ()
    tail = body[-trailing:]
    pos = 0
    shapes = []
    while pos < len(tail):
        opcode = tail[pos]
        pos += 1
        if opcode == 0:
            return ("terminated_at_end" if pos == len(tail) else "terminated_with_remainder"), tuple(shapes)
        if opcode >= 0x80:
            if pos + 2 > len(tail):
                return "invalid_record_boundary", ()
            size = struct.unpack_from("<H", tail, pos)[0]
            pos += 2
            if pos + size > len(tail):
                return "invalid_record_boundary", ()
            shapes.append("L" + str(size))
            pos += size
        else:
            shapes.append("S")
    return "no_terminator", tuple(shapes)


def walk_action_tail_candidate(body, trailing):
    """Preserve the established (status, count) interface for secondary syntax probes."""
    status, shapes = walk_action_tail_shape_candidate(body, trailing)
    return status, len(shapes)


def build_action_opcode_evidence(manifest, data):
    source = manifest.get("source", {}).get("sha256")
    if not isinstance(source, str) or len(source) != 64:
        raise ValueError("Missing source provenance")
    tags = manifest.get("tags")
    scripts = manifest.get("scripts")
    if not isinstance(tags, list) or not isinstance(scripts, list):
        raise ValueError("Missing script/tag inventory")
    selected = [t for t in tags if t.get("tag_code") in LEGACY_CODES]
    expected = [s for s in scripts if s.get("tag_code") in LEGACY_CODES]
    if len(selected) != len(expected):
        raise ValueError("Legacy script container count mismatch")
    totals = Counter()
    tail_classes = Counter()
    tail_bytes = Counter()
    tail_lengths = Counter()
    tail_11_masks = Counter()
    tail_11_zero_counts = Counter()
    tail_11_tag_counts = Counter()
    tail_11_walk_status = Counter()
    tail_11_walk_record_counts = Counter()
    tail_11_record_shapes = Counter()
    entries = []
    for tag, script in zip(selected, expected):
        for field in ("tag_code", "timeline", "frame", "offset_uncompressed", "length"):
            if tag.get(field) != script.get(field):
                raise ValueError("Legacy script inventory provenance mismatch")
        _check_tag(data, tag)
        start = tag["body_offset_uncompressed"]
        body = data[start:start + tag["length"]]
        if tag["tag_code"] == 59:
            if len(body) < 2 or struct.unpack_from("<H", body)[0] != tag.get("init_target_sprite_id"):
                raise ValueError("DoInitAction target mismatch")
            if script.get("init_target_sprite_id") != tag["init_target_sprite_id"]:
                raise ValueError("DoInitAction script target mismatch")
            body = body[2:]
        counts, terminated, trailing = _records(body)
        totals.update(counts)
        tail_class = classify_trailing_bytes(body, trailing)
        tail_classes[tail_class] += 1
        tail_bytes[tail_class] += trailing
        if trailing:
            tail_lengths[trailing] += 1
        if trailing == 11:
            mask = zero_position_mask(body, trailing)
            tail_11_masks[mask] += 1
            tail_11_zero_counts[mask.count("0")] += 1
            tail_11_tag_counts[tag["tag_code"]] += 1
            walk_status, shape = walk_action_tail_shape_candidate(body, trailing)
            walk_count = len(shape)
            if walk_status == "terminated_at_end":
                tail_11_record_shapes[">".join(shape)] += 1
            tail_11_walk_status[walk_status] += 1
            if walk_status != "invalid_record_boundary":
                tail_11_walk_record_counts[walk_count] += 1
        entries.append({"timeline": tag["timeline"], "frame_zero_based": tag["frame"],
                        "tag_code": tag["tag_code"],
                        "offset_uncompressed": tag["offset_uncompressed"],
                        "action_record_count_top_level": sum(counts.values()),
                        "function_record_count_top_level": counts[0x9b] + counts[0x8e],
                        "action_end_found": terminated, "bytes_after_action_end": trailing,
                        "trailing_bytes_class": tail_class})
    histogram = {str(k): totals[k] for k in sorted(totals)}
    return {"source_sha256": source, "legacy_container_count": len(entries),
            "action_record_count_top_level": sum(totals.values()),
            "function_record_count_top_level": totals[0x9b] + totals[0x8e],
            "opcode_counts": histogram,
            "interesting_opcode_counts": {name: totals[code] for code, name in INTERESTING.items()},
            "containers_with_action_end": sum(e["action_end_found"] for e in entries),
            "containers_with_trailing_bytes": sum(e["bytes_after_action_end"] > 0 for e in entries),
            "containers_without_action_end": sum(not e["action_end_found"] for e in entries),
            "trailing_bytes_total": sum(tail_bytes.values()),
            "trailing_class_counts": {name: tail_classes[name] for name in
                                      ("none", "zero_only", "nonzero_only", "mixed")},
            "trailing_bytes_by_class": {name: tail_bytes[name] for name in
                                        ("none", "zero_only", "nonzero_only", "mixed")},
            "trailing_length_histogram": {str(n): tail_lengths[n] for n in sorted(tail_lengths)},
            "trailing_length_11_zero_position_masks": {mask: tail_11_masks[mask] for mask in sorted(tail_11_masks)},
            "trailing_length_11_zero_count_histogram": {str(n): tail_11_zero_counts[n] for n in sorted(tail_11_zero_counts)},
            "trailing_length_11_by_tag_code": {str(n): tail_11_tag_counts[n] for n in sorted(tail_11_tag_counts)},
            "trailing_length_11_candidate_walk_status": {name: tail_11_walk_status[name] for name in
                ("terminated_at_end", "terminated_with_remainder", "no_terminator", "invalid_record_boundary")},
            "trailing_length_11_candidate_record_count_histogram": {str(n): tail_11_walk_record_counts[n] for n in sorted(tail_11_walk_record_counts)},
            "trailing_length_11_candidate_record_shape_histogram": {shape: tail_11_record_shapes[shape] for shape in sorted(tail_11_record_shapes)},
            "entries": entries,
            "limitations": ["Only top-level legacy action records are counted; nested function bodies are not decoded.",
                            "Opcode 0x9B/0x8E is a lexical bytecode function record, not a verified callable function.",
                            "AS1 and AS2 cannot be distinguished by tag/opcode counts alone; AS3 ABC is excluded.",
                            "Zero-only tails are padding candidates, not proven harmless padding.",
                            "Nonzero/mixed tails are not parsed as independent action streams.",
                            "Length-11 masks reveal zero/nonzero positions only, not actual byte values or semantics.",
                            "Secondary ActionRecord walks after the first ActionEnd are syntactic probes only; arbitrary bytes can mimic valid records.",
                            "Record shape histogram contains only short/long categories and payload lengths, not opcode values or executable semantics.",
                            "No bytecode, function names, ActionScript, image or audio bytes are emitted."]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--swf", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("Original SWF SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    report = build_action_opcode_evidence(manifest, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("legacy_container_count", "action_record_count_top_level", "function_record_count_top_level", "containers_without_action_end", "containers_with_trailing_bytes")}))


if __name__ == "__main__":
    main()
