#!/usr/bin/env python3
"""Validate and index unknown SWF tags without publishing original payload bytes.

The evidence is structural only. A repeated payload hash is not a decoded tag.
All offsets are in the decompressed FWS byte stream.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

from swf_inventory import load_swf

UNKNOWN_CODES = (253, 255)


def build_unknown_tag_evidence(swf_path: Path, manifest: dict) -> dict:
    original = swf_path.read_bytes()
    source_sha256 = hashlib.sha256(original).hexdigest()
    if manifest.get("source", {}).get("sha256") != source_sha256:
        raise ValueError("SWF SHA-256 does not match manifest")
    data, _ = load_swf(swf_path)
    grouped = defaultdict(list)
    for tag in manifest["tags"]:
        grouped[tag["timeline"]].append(tag)

    occurrences = []
    hashes = Counter()
    length_by_code = defaultdict(Counter)
    neighbor_pairs = defaultdict(Counter)
    seen_offsets = set()
    for timeline, tags in grouped.items():
        for i, tag in enumerate(tags):
            code = tag["tag_code"]
            if code not in UNKNOWN_CODES:
                continue
            offset = tag["offset_uncompressed"]
            if offset in seen_offsets:
                raise ValueError(f"Duplicate unknown-tag offset {offset}")
            seen_offsets.add(offset)
            if offset < 8 or offset + 2 > len(data):
                raise ValueError(f"Unknown-tag header outside SWF at {offset}")
            packed = struct.unpack_from("<H", data, offset)[0]
            actual_code, size = packed >> 6, packed & 63
            body_start = offset + 2
            if size == 63:
                if body_start + 4 > len(data):
                    raise ValueError(f"Truncated long tag header at {offset}")
                size = struct.unpack_from("<I", data, body_start)[0]
                body_start += 4
            if (actual_code != code or size != tag["length"] or
                    body_start != tag["body_offset_uncompressed"] or
                    body_start + size > len(data)):
                raise ValueError(f"Unknown-tag header/manifest mismatch at {offset}")
            digest = hashlib.sha256(memoryview(data)[body_start:body_start + size]).hexdigest()
            prev_code = tags[i - 1]["tag_code"] if i else None
            next_code = tags[i + 1]["tag_code"] if i + 1 < len(tags) else None
            hashes[(code, digest)] += 1
            length_by_code[code][size] += 1
            neighbor_pairs[code][(prev_code, next_code)] += 1
            occurrences.append({
                "timeline": timeline,
                "frame": tag["frame"],
                "tag_code": code,
                "offset_uncompressed": offset,
                "length": size,
                "payload_sha256": digest,
                "previous_tag_code_same_timeline": prev_code,
                "next_tag_code_same_timeline": next_code,
            })

    for code in UNKNOWN_CODES:
        expected = manifest.get("tag_counts_by_code", {}).get(str(code), 0)
        observed = sum(length_by_code[code].values())
        if expected != observed:
            raise ValueError(f"Unknown tag {code} count mismatch: manifest={expected} observed={observed}")

    summary = {}
    for code in UNKNOWN_CODES:
        by_hash = [(digest, count) for (c, digest), count in hashes.items() if c == code]
        by_hash.sort(key=lambda pair: (-pair[1], pair[0]))
        summary[str(code)] = {
            "count": sum(length_by_code[code].values()),
            "unique_payload_hashes": len(by_hash),
            "repeated_payload_occurrences": sum(n for _, n in by_hash if n > 1),
            "length_counts": {str(k): v for k, v in sorted(length_by_code[code].items())},
            "top_repeated_payload_hashes": [
                {"sha256": digest, "count": n} for digest, n in by_hash if n > 1
            ][:20],
            "neighbor_code_pair_counts": [
                {"previous": prev, "next": nxt, "count": n}
                for (prev, nxt), n in sorted(
                    neighbor_pairs[code].items(),
                    key=lambda x: (-x[1], str(x[0]))
                )
            ],
        }
    return {
        "source_sha256": source_sha256,
        "unknown_codes": list(UNKNOWN_CODES),
        "verified_occurrence_count": len(occurrences),
        "summary_by_code": summary,
        "occurrences": occurrences,
        "limitations": [
            "Payload hashes, lengths, offsets and adjacency are structural evidence only.",
            "Tag 253/255 semantics remain unknown; no bytes or decoded asset bodies are included.",
            "Offsets refer to the uncompressed FWS representation, not the CWS on-disk offsets.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = build_unknown_tag_evidence(args.swf, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "verified_occurrences": result["verified_occurrence_count"],
        "codes": {k: {"count": v["count"], "unique_hashes": v["unique_payload_hashes"]}
                  for k, v in result["summary_by_code"].items()},
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
