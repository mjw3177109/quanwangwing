#!/usr/bin/env python3
"""Metadata-only evidence for AS2 attachMovie linkage calls.

Verifies every FFDec-exported script against its SHA-256 manifest. Only names
already present in the SWF ExportAssets table may appear in output; other
literal arguments are hashed. This is lexical evidence, not a call graph.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from build_as2_semantic_index import mask_comments_strings

ATTACH = re.compile(r"(?<![\w$])attachMovie\s*\(")
LITERAL = re.compile(r"""^\s*(["'])([^"'\\\r\n]*)\1\s*(?:,|\))""")
FUNCTION_DECL = re.compile(r"\bfunction\s+$")


def _require_sha(*items: dict) -> str:
    values = [item.get("source_sha256") for item in items]
    if not values[0] or len(set(values)) != 1:
        raise ValueError("SWF source SHA-256 mismatch")
    return values[0]


def _scope_for_line(scopes: list[dict], line: int) -> dict | None:
    containing = [
        s for s in scopes
        if type(s.get("start_line")) is int and type(s.get("end_line")) is int
        and s["start_line"] <= line <= s["end_line"]
    ]
    if not containing:
        return None
    chosen = min(containing, key=lambda s: (s["end_line"] - s["start_line"], -s["start_line"]))
    return {
        "name": chosen["name"], "kind": chosen["kind"],
        "start_line": chosen["start_line"], "end_line": chosen["end_line"],
        "scope_is_lexical_candidate": True,
    }


def build_attach_evidence(
    scripts_root: Path, export_index: dict, asset_index: dict,
    crosswalk: dict, semantic_index: dict,
) -> dict:
    sha = _require_sha(export_index, asset_index, crosswalk, semantic_index)
    records = export_index.get("files")
    if not isinstance(records, list) or not records or len(records) != export_index.get("script_count"):
        raise ValueError("Invalid verified script file index")
    if export_index.get("unexpected_empty_count", 0):
        raise ValueError("Unexplained empty FFDec script exports")
    roles = crosswalk.get("roles", [])
    if not roles or len(roles) != crosswalk.get("role_variant_count"):
        raise ValueError("Invalid verified role crosswalk")
    role_ids = {r["export_assets_character_id"] for r in roles}
    names = defaultdict(set)
    for entry in asset_index.get("export_assets", []):
        name, cid = entry.get("name"), entry.get("character_id")
        if not isinstance(name, str) or not name or type(cid) is not int or cid <= 0:
            raise ValueError("Invalid ExportAssets symbol")
        names[name].add(cid)
    scopes_by_path = {
        s["path"]: s.get("function_scopes", [])
        for s in semantic_index.get("candidate_scripts", [])
    }

    seen = set()
    events = []
    kinds = Counter()
    checked_bytes = 0
    for record in records:
        rel = record.get("path")
        if (not isinstance(rel, str) or not rel.startswith("scripts/")
                or not rel.endswith(".as") or ".." in Path(rel).parts or rel in seen):
            raise ValueError("Duplicate or invalid AS2 export path")
        seen.add(rel)
        path = scripts_root / rel
        if not path.is_file():
            raise ValueError("Missing verified AS2 source: " + rel)
        raw = path.read_bytes()
        if (len(raw) != record.get("size_bytes")
                or hashlib.sha256(raw).hexdigest() != record.get("sha256")):
            raise ValueError("AS2 export hash/length mismatch: " + rel)
        checked_bytes += len(raw)
        source = raw.decode("utf-8", errors="replace")
        masked = mask_comments_strings(source)
        line_breaks = [i for i, c in enumerate(masked) if c == "\n"]
        for match in ATTACH.finditer(masked):
            # Exclude declarations such as "function attachMovie(...)"; they
            # are not call sites.
            if FUNCTION_DECL.search(masked[max(0, match.start() - 40):match.start()]):
                continue
            lineno = bisect_right(line_breaks, match.start() - 1) + 1
            arg = source[match.end():]
            literal = LITERAL.match(arg)
            if literal:
                value = literal.group(2)
                if value in names:
                    classification = "literal_export_match"
                    matched = [
                        {"name": value, "character_id": cid, "role_candidate": cid in role_ids}
                        for cid in sorted(names[value])
                    ]
                    unknown_hash = None
                else:
                    classification = "literal_unmatched"
                    matched = []
                    unknown_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
            else:
                classification = "dynamic_or_unresolved"
                matched = []
                unknown_hash = None
            kinds[classification] += 1
            event = {
                "script_path": rel,
                "script_sha256": record["sha256"],
                "line": lineno,
                "classification": classification,
                "matched_export_assets": matched,
                "unmatched_literal_sha256": unknown_hash,
                "function_scope_candidate": _scope_for_line(scopes_by_path.get(rel, []), lineno),
            }
            events.append(event)

    return {
        "source_sha256": sha,
        "verified_script_count": len(records),
        "verified_script_bytes": checked_bytes,
        "attach_call_candidate_count": len(events),
        "classification_counts": dict(sorted(kinds.items())),
        "matched_role_candidate_count": sum(
            any(m["role_candidate"] for m in e["matched_export_assets"]) for e in events
        ),
        "events": sorted(events, key=lambda e: (e["script_path"], e["line"], e["classification"])),
        "limitations": [
            "Only lexical attachMovie call candidates; dynamic arguments cannot be resolved here.",
            "Literal matching uses the first plain quoted argument; escaped strings and expressions remain unresolved.",
            "Only ExportAssets names already present in SWF metadata may be emitted as text.",
            "Function scope attribution is approximate and is not a verified call graph.",
            "A matched role symbol does not prove selectability, runtime instantiation, move semantics or collision data.",
            "No original ActionScript bodies, unmatched literal strings, bitmap, sound or game assets are published.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--export-index", type=Path, required=True)
    parser.add_argument("--asset-index", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--semantic-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    result = build_attach_evidence(
        args.scripts, load(args.export_index), load(args.asset_index),
        load(args.crosswalk), load(args.semantic_index),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "verified_scripts": result["verified_script_count"],
        "attach_candidates": result["attach_call_candidate_count"],
        "classifications": result["classification_counts"],
        "matched_role_candidates": result["matched_role_candidate_count"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
