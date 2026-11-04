#!/usr/bin/env python3
"""Trace lexical assignments feeding dynamic role gotoAndPlay/Stop arguments.

The report is metadata-only: source text, identifier spellings, labels and media
remain on the runner. Hash/line/scope evidence is lexical, never runtime proof.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from as2_reference_scopes import lexical_function_scopes, scope_context
from build_as2_semantic_index import mask_comments_strings
from build_role_timeline_call_evidence import CALL, scan_calls

SHA = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"(?<![\w$])([A-Za-z_$][\w$]*)(?![\w$])")
IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*\Z")
MEMBER = re.compile(r"[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)+\Z")
PLAIN_STRING = re.compile(r"""^\s*(['"])([^'"\\\r\n]*)\1\s*(?:;|,|\)|\}|$)""")
ASSIGN = re.compile(r"\s*(>>>=|>>=|<<=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|=(?!=|>))")
EXCLUDED = {
    "this", "_root", "_parent", "_global", "true", "false", "null",
    "undefined", "NaN", "Infinity", "new", "function", "return", "var",
    "typeof", "delete", "void", "instanceof", "in", "if", "else", "for",
    "while", "do", "switch", "case", "break", "continue", "throw", "try",
    "catch", "finally", "with", "as", "is", "and", "or", "not",
}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _check_sha(value, label):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def _count(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid " + label)
    return value


def _valid_path(value):
    return (isinstance(value, str) and value.startswith("scripts/")
            and value.endswith(".as") and ".." not in Path(value).parts
            and not Path(value).is_absolute() and "\\" not in value)


def _first_arg(source: str, masked: str, start: int):
    depth = []
    closing = {")": "(", "]": "[", "}": "{"}
    for i in range(start, min(len(masked), start + 16384)):
        char = masked[i]
        if not depth and char in ",)":
            segment = source[start:i]
            left = len(segment) - len(segment.lstrip())
            right = len(segment.rstrip())
            return segment[left:right], masked[start + left:start + right]
        if char in "([{":
            depth.append(char)
        elif char in closing:
            if not depth or depth[-1] != closing[char]:
                return None
            depth.pop()
    return None


def _split_concat(raw: str, masked: str):
    if len(raw) != len(masked):
        return None
    stack = []
    closing = {")": "(", "]": "[", "}": "{"}
    parts = []
    start = 0
    for i, char in enumerate(masked):
        if char in "([{":
            stack.append(char)
        elif char in closing:
            if not stack or stack.pop() != closing[char]:
                return None
        elif char == "+" and not stack:
            if ((i > 0 and masked[i - 1] == "+")
                    or (i + 1 < len(masked) and masked[i + 1] in "+=")):
                return None
            parts.append((raw[start:i].strip(), masked[start:i].strip()))
            start = i + 1
    if stack or not parts:
        return None
    parts.append((raw[start:].strip(), masked[start:].strip()))
    return parts if all(piece for piece, _ in parts) else None


def _shape(raw: str, masked: str) -> str:
    value = masked.strip()
    if IDENTIFIER.fullmatch(value):
        return "identifier"
    if MEMBER.fullmatch(value):
        return "member_reference"
    if _split_concat(raw, masked) is not None:
        return "concatenation"
    if not value:
        return "opaque_literal_or_empty"
    return "other_expression"


def _line_offsets(masked: str):
    offsets = [0]
    offsets.extend(i + 1 for i, char in enumerate(masked) if char == "\n")
    return offsets


def _offset_for_line(offsets, line: int, text_length: int):
    if type(line) is not int or line < 1:
        raise ValueError("Invalid scope line")
    return offsets[line - 1] if line - 1 < len(offsets) else text_length


def _literal_component(raw: str):
    match = re.fullmatch(r"""\s*(['"])([^'"\\\r\n]*)\1\s*""", raw)
    if not match:
        return None
    return _sha(match.group(2))


def _argument_components(raw: str, masked: str, shape: str):
    if shape == "concatenation":
        return _split_concat(raw, masked) or []
    return [(raw, masked)]


def _label_index(timeline_index: dict):
    timelines = timeline_index.get("timelines")
    if (not isinstance(timelines, list)
            or len(timelines) != _count(timeline_index.get("timeline_count"), "timeline count")):
        raise ValueError("Timeline coverage mismatch")
    result = defaultdict(set)
    seen = set()
    for timeline in timelines:
        key = timeline.get("timeline")
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("Invalid or duplicate timeline")
        seen.add(key)
        for row in timeline.get("frame_labels", []):
            label = row.get("label")
            if not isinstance(label, str):
                raise ValueError("Invalid FrameLabel metadata")
            result[_sha(label)].add(key)
    return {key: sorted(value) for key, value in result.items()}


def _component_evidence(raw: str, masked: str, position: int, label_map: dict):
    literal_hash = _literal_component(raw)
    if literal_hash is not None:
        matches = label_map.get(literal_hash, [])
        return {
            "position": position, "kind": "string_literal_candidate",
            "literal_sha256": literal_hash,
            "matching_timeline_count": len(matches),
            "matching_sprite_timeline_count": sum(x.startswith("sprite:") for x in matches),
            "runtime_binding_verified": False,
        }, []
    refs = []
    for token_position, match in enumerate(TOKEN.finditer(masked)):
        name = match.group(1)
        if name in EXCLUDED:
            continue
        refs.append({
            "position": token_position,
            "identifier_sha256": _sha(name),
            "token_role": "member_component" if "." in masked else "expression_identifier",
            "_identifier": name,
        })
    if IDENTIFIER.fullmatch(masked.strip()):
        kind = "identifier"
    elif MEMBER.fullmatch(masked.strip()):
        kind = "member_reference"
    else:
        kind = "expression"
    return {
        "position": position, "kind": kind,
        "identifier_reference_count": len(refs),
        "runtime_binding_verified": False,
    }, refs


def _rhs_evidence(source: str, masked: str, rhs_start: int, label_map: dict):
    raw_tail = source[rhs_start:]
    literal = PLAIN_STRING.match(raw_tail)
    if literal:
        digest = _sha(literal.group(2))
        matches = label_map.get(digest, [])
        return {
            "rhs_kind": "string_literal_candidate",
            "rhs_sha256": digest,
            "matching_timeline_count": len(matches),
            "matching_sprite_timeline_count": sum(x.startswith("sprite:") for x in matches),
        }
    masked_tail = masked[rhs_start:].lstrip()
    identifier = TOKEN.match(masked_tail)
    if identifier and re.fullmatch(r"\s*(?:;|,|\)|\}|$)", masked_tail[identifier.end():]):
        return {"rhs_kind": "identifier_candidate",
                "rhs_sha256": _sha(identifier.group(1))}
    if not masked_tail:
        return {"rhs_kind": "empty_or_masked"}
    return {"rhs_kind": "expression_or_unresolved"}


def _prior_assignments(source: str, masked: str, identifier: str,
                       scope: dict, call_offset: int, offsets: list,
                       label_map: dict):
    body_start = scope["body_start"] + 1
    body_end = min(scope["body_end"], call_offset)
    rows = []
    parameter_count = 0
    for match in TOKEN.finditer(masked, scope["params_start"], scope["params_end"]):
        if match.group(1) == identifier:
            context = scope_context(masked, [scope], match.start(), match.end())
            if context["context"] == "parameter_declaration_candidate":
                parameter_count += 1
    for match in TOKEN.finditer(masked, body_start, body_end):
        if match.group(1) != identifier:
            continue
        operator = ASSIGN.match(masked, match.end())
        if operator is None:
            continue
        op = operator.group(1)
        before = masked[max(body_start, match.start() - 48):match.start()]
        if before.rstrip().endswith("."):
            lhs = "member_property_candidate"
        elif re.search(r"\bvar\s+$", before):
            lhs = "variable_declaration_candidate"
        else:
            lhs = "direct_assignment_candidate"
        rhs = (_rhs_evidence(source, masked, operator.end(), label_map)
               if op == "=" else {"rhs_kind": "compound_assignment"})
        rows.append({
            "line": bisect_right(offsets, match.start()),
            "lhs_kind": lhs, "operator": op, **rhs,
            "runtime_binding_verified": False,
        })
    return parameter_count, rows


def build_evidence(scripts_root: Path, export_index: dict, role_crosswalk: dict,
                   call_evidence: dict, scope_evidence: dict,
                   timeline_index: dict) -> dict:
    source = _check_sha(export_index.get("source_sha256"), "source SHA-256")
    if any(report.get("source_sha256") != source for report in
           (role_crosswalk, call_evidence, scope_evidence, timeline_index)):
        raise ValueError("SWF source SHA-256 mismatch")
    files = export_index.get("files")
    if (not isinstance(files, list)
            or len(files) != _count(export_index.get("script_count"), "script count", 1)
            or _count(export_index.get("unexpected_empty_count", 0), "unexpected empty count") != 0):
        raise ValueError("Incomplete FFDec export index")
    by_path = {}
    for record in files:
        rel = record.get("path")
        if not _valid_path(rel) or rel in by_path:
            raise ValueError("Duplicate or invalid AS2 export path")
        by_path[rel] = record
    for report, key in ((role_crosswalk, "role_variant_count"),
                        (call_evidence, "role_variant_count"),
                        (scope_evidence, "role_variant_count")):
        if not isinstance(report.get("roles"), list) or len(report["roles"]) != _count(report.get(key), key, 1):
            raise ValueError("Role evidence coverage mismatch")
    role_map = {}
    call_map = {}
    scope_map = {}
    for report, target in ((role_crosswalk, role_map),
                           (call_evidence, call_map),
                           (scope_evidence, scope_map)):
        for role in report["roles"]:
            key = (role.get("character_candidate"), role.get("variant"))
            if not all(isinstance(x, str) and x for x in key) or key in target:
                raise ValueError("Duplicate or invalid role identity")
            target[key] = role
    if set(role_map) != set(call_map) or set(role_map) != set(scope_map):
        raise ValueError("Role crosswalk mismatch")
    label_map = _label_index(timeline_index)
    events = []
    shape_counts = Counter()
    total_calls = 0
    checked_bytes = 0
    seen_calls = set()
    for key in sorted(role_map):
        role = role_map[key]
        calls_role = call_map[key]
        scopes_role = scope_map[key]
        rel = role.get("verified_as2_script_path")
        record = by_path.get(rel)
        if record is None:
            raise ValueError("Missing verified role script")
        raw = (scripts_root / rel).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if (digest != record.get("sha256")
                or digest != role.get("verified_as2_script_sha256")
                or len(raw) != record.get("size_bytes")
                or len(raw) != role.get("verified_as2_script_size_bytes")):
            raise ValueError("Role script hash/length mismatch")
        checked_bytes += len(raw)
        source_text = raw.decode("utf-8", errors="replace")
        masked = mask_comments_strings(source_text)
        parsed = scan_calls(raw)
        source_calls = []
        for match in CALL.finditer(masked):
            if re.search(r"\bfunction\s+$", masked[max(0, match.start() - 64):match.start()]):
                continue
            source_calls.append({
                "start": match.start(), "arg_start": match.end(),
                "line": bisect_right([i for i, c in enumerate(masked) if c == "\n"], match.start() - 1) + 1,
                "method": match.group("method"),
            })
        indexed_calls = calls_role.get("calls")
        scope_calls = scopes_role.get("calls")
        if (len(source_calls) != len(parsed)
                or not isinstance(indexed_calls, list)
                or len(indexed_calls) != len(parsed)
                or len(scope_calls) != len(parsed)
                or len(indexed_calls) != calls_role.get("call_candidate_count")
                or len(scope_calls) != scopes_role.get("call_candidate_count")):
            raise ValueError("Role callsite coverage mismatch")
        offsets = _line_offsets(masked)
        lexical_scopes = lexical_function_scopes(masked)
        for site, parsed_call, indexed, scope_call in zip(source_calls, parsed, indexed_calls, scope_calls):
            total_calls += 1
            for field in ("line", "method", "receiver_kind", "argument_kind"):
                if parsed_call.get(field) != indexed.get(field):
                    raise ValueError("Role callsite provenance mismatch")
            for field in ("line", "method", "receiver_kind"):
                if parsed_call.get(field) != scope_call.get(field):
                    raise ValueError("Role scope callsite provenance mismatch")
            if parsed_call["argument_kind"] != "dynamic_or_unresolved":
                continue
            argument = _first_arg(source_text, masked, site["arg_start"])
            if argument is None:
                raw_arg, masked_arg = "", ""
                shape = "unbalanced_or_oversized"
            else:
                raw_arg, masked_arg = argument
                shape = _shape(raw_arg, masked_arg)
            shape_counts[shape] += 1
            scope_start = scope_call.get("scope_start_line")
            scope_end = scope_call.get("scope_end_line")
            scope_matches = [
                item for item in lexical_scopes
                if item.get("start_line") == scope_start and item.get("end_line") == scope_end
            ] if scope_start is not None and scope_end is not None else []
            scope = scope_matches[0] if len(scope_matches) == 1 else None
            component_rows = []
            identifier_rows = []
            for position, (component_raw, component_masked) in enumerate(
                    _argument_components(raw_arg, masked_arg, shape)):
                component, refs = _component_evidence(
                    component_raw, component_masked, position, label_map)
                component_rows.append(component)
                for ref in refs:
                    identifier = ref.pop("_identifier")
                    if scope is None:
                        parameter_count, assignments = 0, []
                    else:
                        parameter_count, assignments = _prior_assignments(
                            source_text, masked, identifier, scope, site["start"],
                            offsets, label_map)
                    identifier_rows.append({
                        **ref, "parameter_declaration_candidate_count": parameter_count,
                        "prior_assignment_candidate_count": len(assignments),
                        "prior_string_assignment_candidate_count": sum(
                            x.get("rhs_kind") == "string_literal_candidate" for x in assignments),
                        "prior_frame_label_assignment_candidate_count": sum(
                            x.get("rhs_kind") == "string_literal_candidate"
                            and x.get("matching_timeline_count", 0) > 0 for x in assignments),
                        "prior_assignments": assignments,
                        "runtime_binding_verified": False,
                    })
            events.append({
                "character_candidate": key[0], "variant": key[1],
                "script_path_sha256": _sha(rel), "script_sha256": digest,
                "line": site["line"], "method": site["method"],
                "receiver_kind": parsed_call["receiver_kind"],
                "scope_relation": scope_call.get("scope_relation"),
                "scope_target_kind": scope_call.get("scope_target_kind"),
                "scope_start_line": scope_start, "scope_end_line": scope_end,
                "scope_name_sha256": scope.get("name_sha256") if scope else None,
                "scope_resolution": ("unique_lexical_function" if scope else
                                     "ambiguous_or_unresolved_lexical_function"),
                "argument_shape": shape,
                "argument_sha256": _sha(raw_arg) if argument is not None else None,
                "literal_component_count": sum(
                    x["kind"] == "string_literal_candidate" for x in component_rows),
                "literal_components": component_rows,
                "identifier_reference_count": len(identifier_rows),
                "identifier_references": identifier_rows,
                "runtime_binding_verified": False,
            })
    expected = _count(call_evidence.get("call_candidate_count"), "call count")
    if total_calls != expected or total_calls != _count(scope_evidence.get("call_candidate_count"), "scope call count"):
        raise ValueError("Role call total accounting mismatch")
    dynamic_expected = call_evidence.get("argument_kind_counts", {}).get("dynamic_or_unresolved")
    if dynamic_expected != len(events) or sum(shape_counts.values()) != len(events):
        raise ValueError("Dynamic role argument accounting mismatch")
    return {
        "source_sha256": source,
        "verified_script_count": len(files),
        "verified_script_bytes": _count(export_index.get("total_bytes"), "export bytes", 1),
        "checked_role_script_count": len(role_map),
        "checked_role_script_bytes": checked_bytes,
        "role_variant_count": len(role_map),
        "call_candidate_count": total_calls,
        "dynamic_call_count": len(events),
        "argument_shape_counts": dict(sorted(shape_counts.items())),
        "identifier_reference_count": sum(x["identifier_reference_count"] for x in events),
        "prior_assignment_candidate_count": sum(
            ref["prior_assignment_candidate_count"]
            for event in events for ref in event["identifier_references"]),
        "prior_frame_label_assignment_candidate_count": sum(
            ref["prior_frame_label_assignment_candidate_count"]
            for event in events for ref in event["identifier_references"]),
        "calls_with_prior_frame_label_assignment_candidate_count": sum(
            any(ref["prior_frame_label_assignment_candidate_count"] > 0
                for ref in event["identifier_references"]) for event in events),
        "events": sorted(events, key=lambda x: (
            x["character_candidate"], x["variant"], x["line"], x["method"])),
        "limitations": [
            "Assignments are lexical candidates inside a uniquely matched function interval; no control-flow, shadowing or runtime data-flow proof is made.",
            "A literal matching a FrameLabel does not prove the called MovieClip or frame is the runtime target.",
            "Member receivers, computed expressions, escaped strings and dynamic evaluation may remain unresolved.",
            "No original ActionScript text, identifier spelling, frame-label text, raw script path or media bytes are emitted.",
            "All runtime binding and execution verification flags remain false.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripts", type=Path, required=True)
    for name in ("export-index", "role-crosswalk", "call-evidence",
                 "scope-evidence", "timeline-index", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_evidence(
        args.scripts, load(args.export_index), load(args.role_crosswalk),
        load(args.call_evidence), load(args.scope_evidence),
        load(args.timeline_index))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("events", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
