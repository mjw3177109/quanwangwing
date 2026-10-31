#!/usr/bin/env python3
"""Locate lexical gotoAndPlay/Stop callsites in hash-verified FFDec role scripts.

Only call kind, argument shape, numeric frame candidates and source locations
are published. No original ActionScript source, string arguments or assets.
These are NOT verified animation frames or executable gameplay transitions.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from build_as2_semantic_index import mask_comments_strings

CALL = re.compile(r"(?<![\w$])(?P<method>gotoAndPlay|gotoAndStop)\s*\(")
INTEGER = re.compile(r"\s*(?P<number>\d+)\s*\)")
QUOTED = re.compile(r"\s*(['\"])(?:\\.|(?!\1)[^\\])*?\1\s*\)", re.S)


RECEIVER_KINDS = (
    "this_direct", "root_direct", "parent_direct", "identifier_direct",
    "member_chain_or_expression", "computed_or_expression",
    "unqualified_or_unresolved",
)


def classify_receiver(masked: str, method_start: int) -> str:
    """Classify lexical receiver shape without retaining source identifiers.

    This is not a resolved MovieClip instance or a verified timeline target.
    """
    prefix = masked[max(0, method_start - 160):method_start]
    dot = re.search(r"\.\s*$", prefix)
    if dot is None:
        return "unqualified_or_unresolved"
    left = prefix[:dot.start()]
    last = re.search(r"([A-Za-z_$][\w$]*)\s*$", left)
    if last is None:
        return "computed_or_expression"
    earlier = left[:last.start()].rstrip()
    if earlier.endswith((".", "]", ")")):
        return "member_chain_or_expression"
    name = last.group(1)
    return {
        "this": "this_direct",
        "_root": "root_direct",
        "_parent": "parent_direct",
    }.get(name, "identifier_direct")


def scan_calls(raw: bytes) -> list[dict]:
    source = raw.decode("utf-8", errors="replace")
    masked = mask_comments_strings(source)
    newlines = [i for i, char in enumerate(masked) if char == "\n"]
    calls = []
    for match in CALL.finditer(masked):
        # Skip method declarations: function gotoAndPlay(...) is not a call.
        if re.search(r"\bfunction\s+$", masked[max(0, match.start() - 64):match.start()]):
            continue
        start = match.end()
        number = INTEGER.match(masked, start)
        quoted = QUOTED.match(source[start:start + 512]) if not number else None
        if number:
            kind = "integer_literal"
            frame = int(number.group("number"))
        elif quoted:
            kind = "string_literal"
            frame = None
        else:
            kind = "dynamic_or_unresolved"
            frame = None
        calls.append({
            "line": bisect_right(newlines, match.start() - 1) + 1,
            "method": match.group("method"),
            "receiver_kind": classify_receiver(masked, match.start()),
            "argument_kind": kind,
            "literal_frame_candidate": frame,
        })
    return calls


def build_evidence(scripts_root: Path, export: dict, crosswalk: dict) -> dict:
    sha = export.get("source_sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha) or sha != crosswalk.get("source_sha256"):
        raise ValueError("SWF source SHA-256 mismatch")
    records = export.get("files")
    if not isinstance(records, list) or export.get("script_count") != len(records) or export.get("unexpected_empty_count", 0):
        raise ValueError("Incomplete FFDec export index")
    by_path = {}
    for record in records:
        path = record.get("path")
        if (not isinstance(path, str) or not path.startswith("scripts/") or not path.endswith(".as")
                or ".." in Path(path).parts or path in by_path):
            raise ValueError("Invalid or duplicate FFDec export path")
        by_path[path] = record
    roles = crosswalk.get("roles")
    if not isinstance(roles, list) or not roles or crosswalk.get("role_variant_count") != len(roles):
        raise ValueError("Invalid role crosswalk count")
    seen = set()
    result = []
    counts = Counter({"integer_literal": 0, "string_literal": 0, "dynamic_or_unresolved": 0})
    receiver_counts = Counter({kind: 0 for kind in RECEIVER_KINDS})
    for role in roles:
        key = (role.get("character_candidate"), role.get("variant"))
        if key in seen:
            raise ValueError("Duplicate role variant")
        seen.add(key)
        rel = role.get("verified_as2_script_path")
        record = by_path.get(rel)
        if record is None:
            raise ValueError("Missing role script in verified FFDec index")
        path = scripts_root / rel
        if not path.is_file():
            raise ValueError("Missing role script source")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if (type(record.get("size_bytes")) is not int or record["size_bytes"] != len(raw)
                or digest != record.get("sha256")
                or digest != role.get("verified_as2_script_sha256")
                or len(raw) != role.get("verified_as2_script_size_bytes")):
            raise ValueError("Role script hash/length mismatch")
        calls = scan_calls(raw)
        counts.update(c["argument_kind"] for c in calls)
        receiver_counts.update(c["receiver_kind"] for c in calls)
        result.append({
            "character_candidate": key[0],
            "variant": key[1],
            "verified_as2_script_path": rel,
            "verified_as2_script_sha256": digest,
            "call_candidate_count": len(calls),
            "calls": calls,
        })
    return {
        "source_sha256": sha,
        "role_variant_count": len(result),
        "call_candidate_count": sum(r["call_candidate_count"] for r in result),
        "argument_kind_counts": dict(counts),
        "receiver_kind_counts": dict(receiver_counts),
        "roles": sorted(result, key=lambda r: (r["character_candidate"], r["variant"])),
        "limitations": [
            "Lexical gotoAndPlay/Stop matches do not prove runtime execution or animation semantics.",
            "A numeric argument is not verified against its actual target MovieClip timeline.",
            "Receiver shapes are lexical only; no MovieClip identity or property binding is resolved.",
            "String labels and original ActionScript bodies are not published.",
            "Nested expressions, comments, regex literals and FFDec syntax anomalies can affect detection.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scripts", type=Path, required=True)
    p.add_argument("--export-index", type=Path, required=True)
    p.add_argument("--role-crosswalk", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = build_evidence(
        a.scripts,
        json.loads(a.export_index.read_text(encoding="utf-8")),
        json.loads(a.role_crosswalk.read_text(encoding="utf-8")),
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("role_variant_count", "call_candidate_count", "argument_kind_counts", "receiver_kind_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
