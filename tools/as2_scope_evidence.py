"""Lexical AS2 function-to-marker association; metadata only, not gameplay semantics.

Callers must first mask comments and strings. Brace/parenthesis matching remains a
heuristic: regexp literals and malformed FFDec output can affect the boundaries.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
import re


def _matching_pairs(source: str, opening: str, closing: str) -> dict[int, int]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    for i, char in enumerate(source):
        if char == opening:
            stack.append(i)
        elif char == closing and stack:
            pairs[stack.pop()] = i
    return pairs


def extract_function_scope_evidence(
    masked: str, named_pattern: re.Pattern, assigned_pattern: re.Pattern,
    markers: dict[str, re.Pattern],
) -> dict:
    """Associate call markers with their innermost matched function body.

    Returns only identifiers, line numbers and marker counts/lines;
    never source substrings, argument values or function bodies.
    """
    newlines = [i for i, char in enumerate(masked) if char == "\n"]

    def line(offset: int) -> int:
        return bisect_right(newlines, offset - 1) + 1

    braces = _matching_pairs(masked, "{", "}")
    parens = _matching_pairs(masked, "(", ")")
    candidates: list[dict] = []
    assigned_spans: list[tuple[int, int]] = []
    callbacks = {
        "onEnterFrame", "onLoad", "onKeyDown", "onKeyUp", "onPress", "onRelease",
        "onRollOver", "onRollOut", "onMouseDown", "onMouseUp", "onHit",
    }

    for match in assigned_pattern.finditer(masked):
        target = re.sub(r"\s*\.\s*", ".", match.group("target"))
        kind = (
            "prototype_method" if ".prototype." in target
            else "event_callback" if target.rsplit(".", 1)[-1] in callbacks
            else "function_assignment"
        )
        candidates.append({"name": target, "kind": kind, "offset": match.start(),
                           "open_paren": match.end() - 1})
        assigned_spans.append(match.span())

    for match in named_pattern.finditer(masked):
        # A named function expression belongs to its assignment target.
        if any(start <= match.start() < end for start, end in assigned_spans):
            continue
        candidates.append({"name": match.group(1), "kind": "named_function",
                           "offset": match.start(), "open_paren": match.end() - 1})

    scopes: list[dict] = []
    unmatched = 0
    for item in candidates:
        close_paren = parens.get(item["open_paren"])
        if close_paren is None:
            unmatched += 1
            continue
        cursor = close_paren + 1
        while cursor < len(masked) and masked[cursor].isspace():
            cursor += 1
        # AS2 functions may declare a return type such as :Void or :Number.
        if cursor < len(masked) and masked[cursor] == ":":
            cursor += 1
            while cursor < len(masked) and masked[cursor] not in "{;=":
                cursor += 1
        if cursor >= len(masked) or masked[cursor] != "{":
            unmatched += 1
            continue
        close_brace = braces.get(cursor)
        if close_brace is None:
            unmatched += 1
            continue
        scopes.append({
            "name": item["name"], "kind": item["kind"],
            "start_line": line(item["offset"]), "end_line": line(close_brace),
            "body_start": cursor, "body_end": close_brace,
            "marker_counts": Counter(), "marker_lines": {},
        })

    unscoped = Counter()
    for marker_name, pattern in markers.items():
        for match in pattern.finditer(masked):
            position = match.start()
            enclosing = [s for s in scopes if s["body_start"] <= position < s["body_end"]]
            if not enclosing:
                unscoped[marker_name] += 1
                continue
            scope = max(enclosing, key=lambda s: s["body_start"])
            scope["marker_counts"][marker_name] += 1
            scope["marker_lines"].setdefault(marker_name, []).append(line(position))

    clean = []
    for scope in sorted(scopes, key=lambda s: (s["body_start"], s["body_end"])):
        clean.append({
            "name": scope["name"], "kind": scope["kind"],
            "start_line": scope["start_line"], "end_line": scope["end_line"],
            "marker_counts": dict(sorted(scope["marker_counts"].items())),
            "marker_lines": {
                k: sorted(set(v)) for k, v in sorted(scope["marker_lines"].items())
            },
        })
    return {
        "function_scopes": clean,
        "unmatched_function_candidates": unmatched,
        "unscoped_marker_counts": dict(sorted(unscoped.items())),
    }
