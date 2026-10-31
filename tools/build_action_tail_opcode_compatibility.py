#!/usr/bin/env python3
"""Metadata-only operand compatibility probe for bounded 11-byte ActionEnd tails.

A syntactically valid secondary record walk is NOT evidence of execution.
Never emit original opcode bytes, operands, script text or media.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from swf_inventory import load_swf
from build_script_entry_evidence import _check_tag
from build_as2_action_opcode_evidence import _records

# Fixed payload lengths from the SWF legacy ActionRecord definitions.
FIXED_PAYLOAD_LENGTHS = {
    0x81: 2,  # GotoFrame
    0x87: 1,  # StoreRegister
    0x8A: 3,  # WaitForFrame
    0x8D: 1,  # WaitForFrame2
    0x99: 2,  # Jump
    0x9A: 1,  # GetURL2
    0x9D: 2,  # If
    0x9E: 0,  # Call
}
VARIABLE_PAYLOAD_CODES = {
    0x83, 0x88, 0x8B, 0x8C, 0x8E, 0x8F, 0x94, 0x9B, 0x9F
}
CLASS_NAMES = (
    "fixed_length_match", "fixed_length_mismatch",
    "push_payload_well_formed", "push_payload_invalid",
    "known_variable_payload_unchecked", "unlisted_long_opcode"
)


def push_payload_well_formed(payload):
    """Check Push type/length framing only, not operand semantics."""
    pos = 0
    while pos < len(payload):
        kind = payload[pos]
        pos += 1
        if kind == 0:  # null-terminated string
            end = payload.find(b"\x00", pos)
            if end < 0:
                return False
            pos = end + 1
        elif kind in (1, 7):  # Float / Integer
            pos += 4
        elif kind == 6:  # Double
            pos += 8
        elif kind == 9:  # Constant16
            pos += 2
        elif kind in (4, 5, 8):  # Register / Boolean / Constant8
            pos += 1
        elif kind not in (2, 3):  # Null / Undefined
            return False
        if pos > len(payload):
            return False
    return True


def classify_long_action(opcode, payload):
    """Return a coarse compatibility class, never the opcode or payload."""
    if opcode < 0x80:
        raise ValueError("Expected long-format ActionRecord")
    if opcode in FIXED_PAYLOAD_LENGTHS:
        return ("fixed_length_match" if len(payload) == FIXED_PAYLOAD_LENGTHS[opcode]
                else "fixed_length_mismatch")
    if opcode == 0x96:
        return ("push_payload_well_formed" if push_payload_well_formed(payload)
                else "push_payload_invalid")
    if opcode in VARIABLE_PAYLOAD_CODES:
        return "known_variable_payload_unchecked"
    return "unlisted_long_opcode"


def classify_11_byte_tail(tail):
    """Return two coarse classes for exact L2>L2>End syntax, or None."""
    if len(tail) != 11:
        raise ValueError("Expected exactly eleven trailing bytes")
    classes = []
    for offset in (0, 5):
        opcode = tail[offset]
        if opcode < 0x80 or struct.unpack_from("<H", tail, offset + 1)[0] != 2:
            return None
        classes.append(classify_long_action(opcode, tail[offset + 3:offset + 5]))
    if tail[10] != 0:
        return None
    return tuple(classes)


def build_tail_compatibility(manifest, data):
    source = manifest.get("source", {}).get("sha256")
    if not isinstance(source, str) or len(source) != 64:
        raise ValueError("Missing source provenance")
    tags = manifest.get("tags")
    scripts = manifest.get("scripts")
    if not isinstance(tags, list) or not isinstance(scripts, list):
        raise ValueError("Missing tag/script inventory")
    selected = [tag for tag in tags if tag.get("tag_code") in (12, 59)]
    expected = [script for script in scripts if script.get("tag_code") in (12, 59)]
    if len(selected) != len(expected):
        raise ValueError("Legacy script count mismatch")
    classes = Counter()
    pairs = Counter()
    by_tag = Counter()
    length_11 = 0
    nonmatching_shape = 0
    for tag, script in zip(selected, expected):
        for key in ("tag_code", "timeline", "frame", "offset_uncompressed", "length"):
            if tag.get(key) != script.get(key):
                raise ValueError("Script provenance mismatch")
        _check_tag(data, tag)
        start = tag["body_offset_uncompressed"]
        body = data[start:start + tag["length"]]
        if tag["tag_code"] == 59:
            if len(body) < 2 or struct.unpack_from("<H", body)[0] != tag.get("init_target_sprite_id"):
                raise ValueError("DoInitAction target mismatch")
            if script.get("init_target_sprite_id") != tag["init_target_sprite_id"]:
                raise ValueError("DoInitAction script target mismatch")
            body = body[2:]
        _, ended, trailing = _records(body)
        if trailing != 11:
            continue
        if not ended:
            raise ValueError("Eleven-byte tail without ActionEnd")
        length_11 += 1
        pair = classify_11_byte_tail(body[-11:])
        if pair is None:
            nonmatching_shape += 1
            continue
        classes.update(pair)
        pairs[">".join(pair)] += 1
        by_tag[str(tag["tag_code"])] += 1
    eligible = sum(pairs.values())
    return {
        "source_sha256": source,
        "legacy_container_count": len(selected),
        "trailing_length_11_count": length_11,
        "l2_l2_end_candidate_count": eligible,
        "other_shape_count": nonmatching_shape,
        "candidate_record_count": sum(classes.values()),
        "candidate_record_class_histogram": {k: classes[k] for k in CLASS_NAMES},
        "candidate_pair_class_histogram": dict(sorted(pairs.items())),
        "candidate_by_tag_code": dict(sorted(by_tag.items())),
        "limitations": [
            "Only secondary 11-byte L2>L2>End syntax after the FIRST ActionEnd is probed.",
            "Known opcode framing does not prove Flash executes the trailing records.",
            "Variable-length payloads are not semantically decoded.",
            "No opcode values, operand bytes, ActionScript or media are emitted."
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("Original SWF SHA-256 mismatch")
    data, _ = load_swf(args.swf)
    report = build_tail_compatibility(manifest, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "trailing_length_11_count", "l2_l2_end_candidate_count",
        "candidate_record_class_histogram")}))


if __name__ == "__main__":
    main()
