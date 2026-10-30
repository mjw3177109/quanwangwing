"""Bounded lexical scope context for hashed AS2 identifier references.

This is not a binding resolver. Callers pass masked source (comments/strings blanked)
and never publish original ActionScript or unapproved identifier names.
"""
from __future__ import annotations

from bisect import bisect_right
import hashlib
import re

from as2_scope_evidence import _matching_pairs
from build_as2_semantic_index import FUNCTION, ASSIGNED_FUNCTION


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def lexical_function_scopes(masked: str) -> list[dict]:
    """Return matched function signatures/bodies with private offsets and hashed names."""
    parens = _matching_pairs(masked, "(", ")")
    braces = _matching_pairs(masked, "{", "}")
    newlines = [i for i, c in enumerate(masked) if c == "\n"]

    def line(offset: int) -> int:
        return bisect_right(newlines, offset - 1) + 1

    assigned = list(ASSIGNED_FUNCTION.finditer(masked))
    candidates = [(m.start(), m.end() - 1, m.group("target"), "function_assignment")
                  for m in assigned]
    for m in FUNCTION.finditer(masked):
        if any(a.start() <= m.start() < a.end() for a in assigned):
            continue
        candidates.append((m.start(), m.end() - 1, m.group(1), "named_function"))

    scopes = []
    for start, open_paren, name, kind in candidates:
        close_paren = parens.get(open_paren)
        if close_paren is None:
            continue
        cursor = close_paren + 1
        while cursor < len(masked) and masked[cursor].isspace():
            cursor += 1
        if cursor < len(masked) and masked[cursor] == ":":
            cursor += 1
            while cursor < len(masked) and masked[cursor] not in "{;=":
                cursor += 1
        if cursor >= len(masked) or masked[cursor] != "{":
            continue
        body_end = braces.get(cursor)
        if body_end is None:
            continue
        normalized = re.sub(r"\s*\.\s*", ".", name)
        scopes.append({
            "signature_start": start,
            "params_start": open_paren + 1,
            "params_end": close_paren,
            "body_start": cursor,
            "body_end": body_end,
            "name_sha256": _digest(normalized),
            "kind": kind,
            "start_line": line(start),
            "end_line": line(body_end),
        })
    return scopes


def scope_context(masked: str, scopes: list[dict], start: int, end: int) -> dict:
    """Classify a token by innermost function body or signature, not runtime scope."""
    enclosing = [s for s in scopes if
                 (s["params_start"] <= start and end <= s["params_end"])
                 or (s["body_start"] < start and end <= s["body_end"])]
    if not enclosing:
        return {"context": "outside_recognized_function", "scope_candidate": None}
    scope = max(enclosing, key=lambda s: s["signature_start"])
    in_params = scope["params_start"] <= start and end <= scope["params_end"]
    if in_params:
        before = masked[scope["params_start"]:start].rstrip()
        after = masked[end:scope["params_end"]].lstrip()
        parameter = (not before or before.endswith(",")) and (
            not after or after.startswith((":", ",", "=")))
        context = "parameter_declaration_candidate" if parameter else "signature_reference"
    else:
        context = "function_body_reference"
    return {
        "context": context,
        "scope_candidate": {
            "name_sha256": scope["name_sha256"],
            "kind": scope["kind"],
            "start_line": scope["start_line"],
            "end_line": scope["end_line"],
            "runtime_binding_verified": False,
        },
    }
