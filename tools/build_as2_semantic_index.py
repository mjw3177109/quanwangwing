#!/usr/bin/env python3
"""Evidence-only AS2 entry map from locally exported FFDec sources.

Source bodies are read for validation and lexical hints, but never written to
the report. All findings are candidates, not proof of gameplay semantics.
"""
from __future__ import annotations

import argparse
from collections import Counter
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import re

FUNCTION = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(")
# AS2 often declares methods as prototype/function-expression assignments rather
# than "function name(...)". Keep these as lexical evidence only.
ASSIGNED_FUNCTION = re.compile(
    r"(?<![\\w$])(?P<target>[A-Za-z_$][\\w$]*(?:\\s*\\.\\s*[A-Za-z_$][\\w$]*){0,12})"
    r"\\s*=\\s*function\\s*(?:[A-Za-z_$][\\w$]*\\s*)?\\("
)
CALLBACK_NAMES = frozenset({
    "onEnterFrame", "onLoad", "onKeyDown", "onKeyUp", "onPress", "onRelease",
    "onRollOver", "onRollOut", "onMouseDown", "onMouseUp", "onHit",
})

CLASS = re.compile(r"\bclass\s+([A-Za-z_$][\w.$]*)\b")
EXTENDS = re.compile(r"\bextends\s+([A-Za-z_$][\w.$]*)\b")
MARKERS = {
    "keyboard": re.compile(r"\bKey\s*\.\s*(?:isDown|addListener)\b"),
    "hit_test": re.compile(r"\bhitTest\s*\("),
    "timeline_jump": re.compile(r"\bgotoAnd(?:Play|Stop)\s*\("),
    "sprite_attach": re.compile(r"\battachMovie\s*\("),
    "frame_callback": re.compile(r"\bonEnterFrame\b"),
    "clip_event": re.compile(r"\bonClipEvent\b"),
    "timer": re.compile(r"\b(?:setInterval|getTimer)\s*\("),
}
SYSTEM_NAME = re.compile(
    r"(?:hitcheck|input|key|player|cpu|stage|game|battle|fight|attack|damage|guard|combo)", re.I
)


def mask_comments_strings(source: str) -> str:
    """Mask AS2 strings/comments, retaining newlines and character offsets.

    This is a lexical heuristic, not a full ActionScript parser.
    """
    out = list(source)
    i = 0
    state = "code"
    while i < len(source):
        c = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "code":
            if c == "/" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "line"
                continue
            if c == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                i += 2
                state = "block"
                continue
            if c in "\"'":
                out[i] = " "
                state = c
                i += 1
                continue
        elif state == "line":
            if c == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
            continue
        elif state == "block":
            if c == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "code"
                continue
            if c != "\n":
                out[i] = " "
            i += 1
            continue
        else:
            if c == "\\" and nxt:
                out[i] = " "
                if nxt != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if c == state:
                state = "code"
            if c != "\n":
                out[i] = " "
            i += 1
            continue
        i += 1
    return "".join(out)


def inspect_source(raw: bytes) -> dict:
    masked = mask_comments_strings(raw.decode("utf-8", errors="replace"))
    newlines = [i for i, char in enumerate(masked) if char == "\n"]
    line = lambda offset: bisect_right(newlines, offset - 1) + 1
    assigned = []
    for match in ASSIGNED_FUNCTION.finditer(masked):
        target = re.sub(r"\\s*\\.\\s*", ".", match.group("target"))
        kind = (
            "prototype_method" if ".prototype." in target
            else "event_callback" if target.rsplit(".", 1)[-1] in CALLBACK_NAMES
            else "function_assignment"
        )
        assigned.append({"target": target, "line": line(match.start()), "kind": kind})
    return {
        "assigned_functions": assigned,
        "declared_classes": [
            {"name": m.group(1), "line": line(m.start())} for m in CLASS.finditer(masked)
        ],
        "extends_candidates": [m.group(1) for m in EXTENDS.finditer(masked)],
        "named_functions": [
            {"name": m.group(1), "line": line(m.start())} for m in FUNCTION.finditer(masked)
        ],
        "marker_counts": {
            name: len(pattern.findall(masked)) for name, pattern in MARKERS.items()
        },
    }


def build_index(scripts_root: Path, export_index: dict, asset_index: dict) -> dict:
    if export_index.get("source_sha256") != asset_index.get("source_sha256"):
        raise ValueError("SWF SHA-256 mismatch between export and asset indexes")
    if export_index.get("unexpected_empty_count", 0):
        raise ValueError("Unexplained empty AS2 exports present")
    records = export_index["files"]
    if len(records) != export_index["script_count"]:
        raise ValueError("Script count does not match index")
    if len({r["path"] for r in records}) != len(records):
        raise ValueError("Duplicate script paths in export index")

    expected_roles = {
        f"scripts/__Packages/{prefix}{c['class_name']}_role.as": (c["class_name"], prefix)
        for c in asset_index.get("character_class_candidates", [])
        for prefix in ("", "Type2_")
        if c.get("type2_role_character_id" if prefix else "base_role_character_id") is not None
    }
    indexed_paths = {r["path"] for r in records}
    critical = "scripts/__Packages/role_corn/Role.as"
    if len(records) >= 7000 and critical not in indexed_paths:
        raise ValueError("Critical Role.as script missing from original AS2 export")
    role_map = [
        {
            "character_candidate": character,
            "variant": "type2" if prefix else "base",
            "expected_script_path": path,
            "export_present": path in indexed_paths,
        }
        for path, (character, prefix) in sorted(expected_roles.items())
    ]
    script_summaries = []
    aggregate = Counter()
    for record in records:
        rel = record["path"]
        if not rel.startswith("scripts/") or not rel.endswith(".as") or ".." in Path(rel).parts:
            raise ValueError("Invalid script relative path: " + rel)
        path = scripts_root / rel
        if not path.is_file():
            raise ValueError("Export missing: " + rel)
        raw = path.read_bytes()
        if len(raw) != record["size_bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Export hash/length mismatch: " + rel)
        if rel == "scripts/__Packages/role_corn/Role.as" and len(raw) < 100000:
            raise ValueError("Critical Role.as export is unexpectedly short; likely partial FFDec output")
        is_role = rel in expected_roles
        is_core = rel == critical
        is_system = rel.startswith("scripts/__Packages/") and SYSTEM_NAME.search(Path(rel).stem) is not None
        is_frame = "/frame_" in rel and len(raw) >= 32768
        if is_role or is_core or is_system or is_frame:
            hints = inspect_source(raw)
            aggregate.update(hints["marker_counts"])
            script_summaries.append({
                "path": rel,
                "sha256": record["sha256"],
                "size_bytes": len(raw),
                "role_candidate": is_role,
                "core_runtime_candidate": is_core,
                "system_name_candidate": bool(is_system),
                "large_frame_script_candidate": is_frame,
                **hints,
            })
    by_path = {r["path"]: r for r in script_summaries}
    for entry in role_map:
        if entry["export_present"]:
            match = by_path[entry["expected_script_path"]]
            entry["declared_classes"] = match["declared_classes"]
            entry["named_function_count"] = len(match["named_functions"])
            entry["assigned_function_count"] = len(match["assigned_functions"])
    return {
        "source_sha256": export_index["source_sha256"],
        "verified_script_count": len(records),
        "verified_script_bytes": sum(r["size_bytes"] for r in records),
        "verified_noop_empty_count": export_index.get("verified_noop_empty_count"),
        "role_script_candidates": role_map,
        "candidate_script_count": len(script_summaries),
        "assigned_function_count_in_candidate_scripts": sum(
            len(item["assigned_functions"]) for item in script_summaries
        ),
        "assigned_function_kinds_in_candidate_scripts": dict(sorted(Counter(
            item["kind"] for summary in script_summaries
            for item in summary["assigned_functions"]
        ).items())),
        "marker_counts_in_candidate_scripts": dict(sorted(aggregate.items())),
        "candidate_scripts": sorted(script_summaries, key=lambda x: x["path"]),
        "limitations": [
            "Names, paths, line numbers and lexical markers only; no ActionScript bodies are published.",
            "Method and keyword matches are heuristics, not verified gameplay semantics.",
            "Function assignment targets are lexical candidates; computed properties and regex literals may be missed.",
            "Role path matches do not prove selectability, hitboxes, damage or move timings.",
            "Source files remain on the runner and are not included in the artifact.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--export-index", type=Path, required=True)
    parser.add_argument("--asset-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_index = json.loads(args.export_index.read_text(encoding="utf-8"))
    asset_index = json.loads(args.asset_index.read_text(encoding="utf-8"))
    result = build_index(args.scripts, export_index, asset_index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "verified_script_count": result["verified_script_count"],
        "role_script_candidates": len(result["role_script_candidates"]),
        "role_scripts_present": sum(r["export_present"] for r in result["role_script_candidates"]),
        "candidate_script_count": result["candidate_script_count"],
        "assigned_function_count": result["assigned_function_count_in_candidate_scripts"],
        "assigned_function_kinds": result["assigned_function_kinds_in_candidate_scripts"],
        "marker_counts": result["marker_counts_in_candidate_scripts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
