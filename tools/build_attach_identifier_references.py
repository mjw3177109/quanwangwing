#!/usr/bin/env python3
"""Find hash-matched AS2 identifier references for unresolved attachMovie arguments.

Evidence is lexical only; source bytes remain local to the runner. Output contains
script paths, line numbers, hashed identifiers, counts and coarse syntax classes.
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
from as2_reference_scopes import lexical_function_scopes, scope_context

TOKEN = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]*)(?![\w$])")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EXAMPLE_LIMIT = 80


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _kind(masked: str, start: int, end: int) -> str:
    before = masked[max(0, start - 80):start]
    after = masked[end:end + 20]
    if before.rstrip().endswith("."):
        return "member_property"
    if re.search(r"\bvar\s+$", before):
        return "variable_declaration"
    if re.search(r"\bfunction\s+$", before):
        return "function_declaration"
    if re.match(r"\s*=(?!=)", after):
        return "assignment_target_candidate"
    return "other_reference"


def build_identifier_references(scripts_root: Path, export_index: dict,
                                provenance: dict) -> dict:
    source_sha = export_index.get("source_sha256")
    if not source_sha or source_sha != provenance.get("source_sha256"):
        raise ValueError("SWF source SHA-256 mismatch")
    records = export_index.get("files")
    if (not isinstance(records, list) or not records
            or len(records) != export_index.get("script_count")
            or export_index.get("unexpected_empty_count", 0)):
        raise ValueError("Invalid verified script index")
    events = provenance.get("events")
    if not isinstance(events, list) or len(events) != provenance.get("dynamic_argument_count"):
        raise ValueError("Invalid dynamic argument provenance")
    sites = {}
    for event in events:
        if event.get("argument_shape") == "identifier":
            candidates = [(event.get("identifier_sha256"), None)]
        else:
            candidates = [(part.get("identifier_sha256"), part.get("position"))
                          for part in event.get("concatenation_components", [])
                          if part.get("kind") == "identifier"]
        for digest, position in candidates:
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                raise ValueError("Invalid hashed argument identifier")
            path, line = event.get("script_path"), event.get("line")
            if not isinstance(path, str) or type(line) is not int or line < 1:
                raise ValueError("Invalid attachMovie source location")
            sites.setdefault(digest, []).append({"script_path": path,
                                                   "line": line,
                                                   "component_position": position})

    counters = {digest: Counter() for digest in sites}
    kinds = {digest: Counter() for digest in sites}
    contexts = {digest: Counter() for digest in sites}
    same_examples = {digest: [] for digest in sites}
    other_examples = {digest: [] for digest in sites}
    checked_bytes = 0
    seen = set()
    cache = {}
    for record in records:
        rel = record.get("path")
        if (not isinstance(rel, str) or not rel.startswith("scripts/")
                or not rel.endswith(".as") or ".." in Path(rel).parts
                or rel in seen):
            raise ValueError("Duplicate or invalid AS2 script path")
        seen.add(rel)
        path = scripts_root / rel
        if not path.is_file():
            raise ValueError("Missing verified AS2 script: " + rel)
        raw = path.read_bytes()
        if (len(raw) != record.get("size_bytes")
                or hashlib.sha256(raw).hexdigest() != record.get("sha256")):
            raise ValueError("AS2 source hash/length mismatch: " + rel)
        checked_bytes += len(raw)
        if not sites:
            continue
        masked = mask_comments_strings(raw.decode("utf-8", errors="replace"))
        newlines = [i for i, char in enumerate(masked) if char == "\n"]
        scopes = None  # Parse only scripts containing a target identifier.
        for match in TOKEN.finditer(masked):
            name = match.group(1)
            if name not in cache:
                cache[name] = _hash(name)
            digest = cache[name]
            if digest not in sites:
                continue
            line = bisect_right(newlines, match.start() - 1) + 1
            kind = _kind(masked, match.start(), match.end())
            if scopes is None:
                scopes = lexical_function_scopes(masked)
            context = scope_context(masked, scopes, match.start(), match.end())
            same_sites = [s for s in sites[digest] if s["script_path"] == rel]
            is_before = any(line < s["line"] for s in same_sites)
            counts = counters[digest]
            counts["total"] += 1
            bucket = ("same_script_before" if is_before else
                      "same_script_at_or_after" if same_sites else "other_script")
            counts[bucket] += 1
            kinds[digest][kind] += 1
            contexts[digest][context["context"]] += 1
            example = {"script_path": rel, "line": line, "kind": kind,
                       "relation": bucket, **context}
            dest = same_examples[digest] if same_sites else other_examples[digest]
            if len(dest) < EXAMPLE_LIMIT:
                dest.append(example)
    if checked_bytes != provenance.get("verified_script_bytes"):
        raise ValueError("Verified script byte count mismatch")
    for digest, locations in sites.items():
        if not any(s["script_path"] in seen for s in locations):
            raise ValueError("attachMovie source script missing from export")
        if counters[digest]["total"] < 1:
            raise ValueError("Hashed attachMovie identifier not found in source")
    targets = []
    for digest in sorted(sites):
        count = counters[digest]
        targets.append({
            "identifier_sha256": digest,
            "attach_sites": sites[digest],
            "occurrence_count": count["total"],
            "same_script_before_count": count["same_script_before"],
            "same_script_at_or_after_count": count["same_script_at_or_after"],
            "other_script_count": count["other_script"],
            "syntax_counts": dict(sorted(kinds[digest].items())),
            "scope_context_counts": dict(sorted(contexts[digest].items())),
            "examples": (same_examples[digest] + other_examples[digest])[:EXAMPLE_LIMIT],
            "examples_truncated": count["total"] > EXAMPLE_LIMIT,
            "runtime_binding_verified": False,
        })
    return {
        "source_sha256": source_sha,
        "verified_script_count": len(records),
        "verified_script_bytes": checked_bytes,
        "identifier_target_count": len(targets),
        "identifier_occurrence_count": sum(t["occurrence_count"] for t in targets),
        "targets": targets,
        "limitations": [
            "Identifiers are compared by SHA-256 over lexically masked AS2 tokens, not resolved bindings.",
            "Prior text, declarations and assignment syntax do not prove control flow or variable scope.",
            "Function signatures and body ranges are lexical candidates; malformed exports, regex literals and shadowing may affect scope classification.",
            "Examples are bounded and may omit references; aggregate counts include all matches.",
            "No ActionScript bodies, unmatched strings, original image or audio bytes are emitted.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--export-index", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_identifier_references(args.scripts, load(args.export_index),
                                         load(args.provenance))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"verified_scripts": result["verified_script_count"],
                      "targets": result["identifier_target_count"],
                      "occurrences": result["identifier_occurrence_count"]}))


if __name__ == "__main__":
    main()
