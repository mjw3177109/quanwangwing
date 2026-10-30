#!/usr/bin/env python3
"""Trace unresolved AS2 attachMovie first-argument syntax and prior assignments.

All source files are re-verified against the FFDec export manifest. This is
lexical, metadata-only evidence: no runtime variable resolution is claimed.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from build_as2_semantic_index import mask_comments_strings
from build_runtime_attach_evidence import ATTACH, FUNCTION_DECL, LITERAL

IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*\Z")
MEMBER = re.compile(r"[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)+\Z")
CALL = re.compile(r"(?:[A-Za-z_$][\w$]*\s*\.\s*)*[A-Za-z_$][\w$]*\s*\(")
ASSIGN_TEMPLATE = r"(?<![\w$.])(?:var\s+)?%s\s*=(?!=)"
RHS_LITERAL = re.compile(r"""^\s*(["'])([^"'\\\r\n]*)\1\s*(?:;|,|\r?\n|$)""")
RHS_IDENTIFIER = re.compile(r"^\s*[A-Za-z_$][\w$]*\s*(?:;|,|\r?\n|$)")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _first_arg(source: str, masked: str, start: int) -> tuple[str, str] | None:
    """Return the raw and masked first argument, honoring nested delimiters."""
    depth = []
    closing = {")": "(", "]": "[", "}": "{"}
    for i in range(start, min(len(masked), start + 16384)):
        c = masked[i]
        if not depth and c in ",)":
            return source[start:i].strip(), masked[start:i].strip()
        if c in "([{":
            depth.append(c)
        elif c in closing:
            if not depth or depth[-1] != closing[c]:
                return None
            depth.pop()
    return None



PLAIN_LITERAL = re.compile(r"""^(['"])([^"'\\\r\n]*)\1$""")


def _split_concat(raw: str, masked: str) -> list[tuple[str, str]] | None:
    """Split only top-level binary '+' tokens, never quoted or nested pluses."""
    if len(raw) != len(masked):
        return None
    stack = []
    closes = {")": "(", "]": "[", "}": "{"}
    parts = []
    start = 0
    for i, char in enumerate(masked):
        if char in "([{":
            stack.append(char)
        elif char in closes:
            if not stack or stack.pop() != closes[char]:
                return None
        elif char == "+" and not stack:
            # Increment/decrement and compound operators are not concatenation.
            if (i > 0 and masked[i - 1] == "+") or (
                i + 1 < len(masked) and masked[i + 1] in "+="
            ):
                return None
            parts.append((raw[start:i].strip(), masked[start:i].strip()))
            start = i + 1
    if stack or not parts:
        return None
    parts.append((raw[start:].strip(), masked[start:].strip()))
    if any(not raw_part for raw_part, _ in parts):
        return None
    return parts


def _shape(raw: str, masked: str) -> str:
    if IDENTIFIER.fullmatch(masked):
        return "identifier"
    if MEMBER.fullmatch(masked):
        return "member_reference"
    if _split_concat(raw, masked) is not None:
        return "concatenation"
    if CALL.match(masked):
        return "call_expression"
    if not masked:
        return "opaque_literal_or_empty" if raw else "empty"
    return "other_expression"


def _assignment_candidates(
    source: str, masked: str, identifier: str, before: int,
    start_line: int | None, line_breaks: list[int], names: dict[str, set[int]],
) -> list[dict]:
    # A lexical scope line is a lower-bound hint, NOT a guarantee of binding.
    start_offset = (
        line_breaks[start_line - 2] + 1 if start_line and start_line > 1
        and start_line - 2 < len(line_breaks) else 0
    )
    regex = re.compile(ASSIGN_TEMPLATE % re.escape(identifier))
    candidates = []
    for match in regex.finditer(masked, start_offset, before):
        rhs = source[match.end():]
        literal = RHS_LITERAL.match(rhs)
        if literal:
            value = literal.group(2)
            if value in names:
                kind = "literal_export_match"
                exports = [
                    {"name": value, "character_id": cid}
                    for cid in sorted(names[value])
                ]
                unknown_hash = None
            else:
                kind = "literal_unmatched"
                exports = []
                unknown_hash = _hash(value)
        elif RHS_IDENTIFIER.match(rhs):
            kind = "identifier_assignment"
            exports = []
            unknown_hash = None
        else:
            kind = "expression_or_unresolved"
            exports = []
            unknown_hash = None
        candidates.append({
            "line": bisect_right(line_breaks, match.start() - 1) + 1,
            "rhs_kind": kind,
            "matched_export_assets": exports,
            "unmatched_literal_sha256": unknown_hash,
        })
    return candidates



def _concat_components(
    raw: str, masked: str, source: str, before: int,
    scope_start: int | None, line_breaks: list[int],
    names: dict[str, set[int]],
) -> list[dict]:
    """Describe syntax and lexical assignment hints without leaking source."""
    parts = _split_concat(raw, masked)
    if parts is None:
        return []
    result = []
    for position, (piece, masked_piece) in enumerate(parts):
        literal = PLAIN_LITERAL.fullmatch(piece)
        matches = []
        unknown_literal_sha = None
        identifier_sha = None
        assignments = []
        if literal:
            value = literal.group(2)
            if value in names:
                kind = "literal_export_match"
                matches = [
                    {"name": value, "character_id": cid}
                    for cid in sorted(names[value])
                ]
            else:
                kind = "literal_unmatched"
                unknown_literal_sha = _hash(value)
        elif IDENTIFIER.fullmatch(masked_piece):
            kind = "identifier"
            identifier_sha = _hash(masked_piece)
            assignments = _assignment_candidates(
                source, masked, masked_piece, before,
                scope_start, line_breaks, names,
            )
        elif MEMBER.fullmatch(masked_piece):
            kind = "member_reference"
        elif CALL.match(masked_piece):
            kind = "call_expression"
        else:
            kind = "other_or_unresolved"
        result.append({
            "position": position,
            "kind": kind,
            "component_sha256": _hash(piece),
            "matched_export_assets": matches,
            "unmatched_literal_sha256": unknown_literal_sha,
            "identifier_sha256": identifier_sha,
            "lexical_assignment_candidates": assignments,
            "runtime_value_verified": False,
        })
    return result


def build_dynamic_argument_evidence(
    scripts_root: Path, export_index: dict, attach_report: dict,
    asset_index: dict,
) -> dict:
    sha = export_index.get("source_sha256")
    if not sha or sha != attach_report.get("source_sha256") or sha != asset_index.get("source_sha256"):
        raise ValueError("SWF source SHA-256 mismatch")
    records = export_index.get("files")
    if (not isinstance(records, list) or not records
            or len(records) != export_index.get("script_count")
            or export_index.get("unexpected_empty_count", 0)):
        raise ValueError("Invalid verified script export index")

    names = defaultdict(set)
    for entry in asset_index.get("export_assets", []):
        name, cid = entry.get("name"), entry.get("character_id")
        if not isinstance(name, str) or not name or type(cid) is not int or cid <= 0:
            raise ValueError("Invalid ExportAssets entry")
        names[name].add(cid)

    prior_events = defaultdict(list)
    events = attach_report.get("events")
    if not isinstance(events, list) or len(events) != attach_report.get("attach_call_candidate_count"):
        raise ValueError("Invalid attachMovie evidence report")
    for e in events:
        prior_events[(e["script_path"], e["line"], e["classification"])].append(e)

    observed = Counter()
    kinds = Counter()
    results = []
    seen = set()
    checked_bytes = 0
    for record in records:
        rel = record.get("path")
        if (not isinstance(rel, str) or not rel.startswith("scripts/")
                or not rel.endswith(".as") or ".." in Path(rel).parts
                or rel in seen):
            raise ValueError("Duplicate or invalid AS2 export path")
        seen.add(rel)
        path = scripts_root / rel
        if not path.is_file():
            raise ValueError("Missing verified AS2 script: " + rel)
        raw = path.read_bytes()
        if (len(raw) != record.get("size_bytes")
                or hashlib.sha256(raw).hexdigest() != record.get("sha256")):
            raise ValueError("AS2 export hash/length mismatch: " + rel)
        checked_bytes += len(raw)
        source = raw.decode("utf-8", errors="replace")
        masked = mask_comments_strings(source)
        line_breaks = [i for i, c in enumerate(masked) if c == "\n"]
        for match in ATTACH.finditer(masked):
            if FUNCTION_DECL.search(masked[max(0, match.start() - 40):match.start()]):
                continue
            line = bisect_right(line_breaks, match.start() - 1) + 1
            literal = LITERAL.match(source[match.end():])
            classification = (
                "literal_export_match" if literal and literal.group(2) in names
                else "literal_unmatched" if literal else "dynamic_or_unresolved"
            )
            observed[classification] += 1
            key = (rel, line, classification)
            if not prior_events[key]:
                raise ValueError("attachMovie report/source call mismatch: " + rel)
            prior = prior_events[key].pop(0)
            if classification != "dynamic_or_unresolved":
                continue

            arg = _first_arg(source, masked, match.end())
            raw_arg, masked_arg = arg if arg is not None else ("", "")
            shape = _shape(raw_arg, masked_arg) if arg is not None else "unbalanced_or_oversized"
            scope = prior.get("function_scope_candidate")
            scope_start = scope.get("start_line") if isinstance(scope, dict) else None
            candidates = (
                _assignment_candidates(
                    source, masked, masked_arg, match.start(),
                    scope_start, line_breaks, names,
                ) if shape == "identifier" else []
            )
            component_evidence = (
                _concat_components(
                    raw_arg, masked_arg, source, match.start(),
                    scope_start, line_breaks, names,
                ) if shape == "concatenation" else []
            )
            kinds[shape] += 1
            results.append({
                "script_path": rel,
                "script_sha256": record["sha256"],
                "line": line,
                "argument_shape": shape,
                "argument_sha256": _hash(raw_arg) if arg is not None else None,
                "identifier_sha256": _hash(masked_arg) if shape == "identifier" else None,
                "lexical_assignment_candidates": candidates,
                "concatenation_components": component_evidence,
                "scope_basis": "candidate_function_start" if scope_start else "file_prior_text",
                "runtime_binding_verified": False,
            })

    if any(prior_events.values()):
        raise ValueError("Unmatched attachMovie report events")
    if dict(observed) != attach_report.get("classification_counts"):
        raise ValueError("attachMovie classification counts mismatch")
    if sum(observed.values()) != attach_report["attach_call_candidate_count"]:
        raise ValueError("attachMovie total count mismatch")

    return {
        "source_sha256": sha,
        "verified_script_count": len(records),
        "verified_script_bytes": checked_bytes,
        "attach_call_candidate_count": sum(observed.values()),
        "dynamic_argument_count": len(results),
        "argument_shape_counts": dict(sorted(kinds.items())),
        "events": sorted(results, key=lambda e: (e["script_path"], e["line"], e["argument_sha256"] or "")),
        "limitations": [
            "Prior assignments are lexical candidates only; branches, shadowing, mutation and execution order are not resolved.",
            "A matching ExportAssets string in a prior assignment does not prove the call uses that value at runtime.",
            "Function scope start lines are approximate; no control-flow or data-flow proof is claimed.",
            "Only SWF ExportAssets names may appear in output; all other literals and argument identifiers are hashed.",
            "Concatenation components are lexical evidence, not evaluated runtime strings or proven character loads.",
            "No original ActionScript bodies, images, audio, or asset bytes are published.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--export-index", type=Path, required=True)
    parser.add_argument("--attach-evidence", type=Path, required=True)
    parser.add_argument("--asset-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_dynamic_argument_evidence(
        args.scripts, load(args.export_index), load(args.attach_evidence),
        load(args.asset_index),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "verified_scripts": result["verified_script_count"],
        "dynamic_arguments": result["dynamic_argument_count"],
        "argument_shapes": result["argument_shape_counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
