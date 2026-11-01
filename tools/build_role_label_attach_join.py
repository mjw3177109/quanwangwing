#!/usr/bin/env python3
"""Join verified role FrameLabel candidates to ExportAssets and literal attachMovie targets.

This is a metadata-only, lexical cross-check, NOT a runtime MovieClip binding.
Original labels, symbol names, target IDs, script bodies and media never leave the runner.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from build_role_frame_label_evidence import _literal_arguments
from build_role_timeline_call_evidence import scan_calls

SHA = re.compile(r"[0-9a-f]{64}\Z")
KINDS = ("no_sprite_label_candidate", "sprite_not_exported",
         "exported_no_literal_attach", "literal_attach_overlap")


def _positive_id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("Invalid SWF character ID")
    return value


def build_join(scripts_root: Path, export: dict, crosswalk: dict, calls: dict,
               frame_evidence: dict, timeline: dict, assets: dict,
               attach: dict) -> dict:
    source = export.get("source_sha256")
    if not isinstance(source, str) or not SHA.fullmatch(source) or any(
        d.get("source_sha256") != source
        for d in (crosswalk, calls, frame_evidence, timeline, assets, attach)
    ):
        raise ValueError("SWF source SHA-256 mismatch")
    files = export.get("files")
    if (not isinstance(files, list) or len(files) != export.get("script_count")
            or export.get("unexpected_empty_count", 0)
            or attach.get("verified_script_count") != len(files)
            or attach.get("verified_script_bytes") != export.get("total_bytes")):
        raise ValueError("Verified AS2 export coverage mismatch")
    file_map = {}
    for item in files:
        path = item.get("path")
        if (not isinstance(path, str) or not path.startswith("scripts/")
                or not path.endswith(".as") or ".." in Path(path).parts
                or path in file_map):
            raise ValueError("Invalid or duplicate verified AS2 path")
        file_map[path] = item

    definitions = {}
    for item in assets.get("assets", []):
        cid = _positive_id(item.get("character_id"))
        if cid in definitions:
            raise ValueError("Duplicate SWF asset definition")
        definitions[cid] = item.get("category")
    exports_by_id = defaultdict(set)
    exports = assets.get("export_assets")
    if not isinstance(exports, list) or len(exports) != assets.get("exported_symbol_count"):
        raise ValueError("ExportAssets coverage mismatch")
    for item in exports:
        cid = _positive_id(item.get("character_id"))
        name = item.get("name")
        if cid not in definitions or not isinstance(name, str) or not name:
            raise ValueError("Invalid ExportAssets reference")
        exports_by_id[cid].add(name)

    events = attach.get("events")
    if (not isinstance(events, list)
            or len(events) != attach.get("attach_call_candidate_count")
            or sum(attach.get("classification_counts", {}).values()) != len(events)):
        raise ValueError("attachMovie event coverage mismatch")
    literal_attach_sprites = set()
    for event in events:
        matched = event.get("matched_export_assets")
        kind = event.get("classification")
        if not isinstance(matched, list):
            raise ValueError("Invalid attachMovie matches")
        if kind == "literal_export_match" and not matched:
            raise ValueError("Missing literal attachMovie symbol")
        if kind != "literal_export_match" and matched:
            raise ValueError("Unexpected attachMovie symbol")
        for item in matched:
            cid = _positive_id(item.get("character_id"))
            if item.get("name") not in exports_by_id.get(cid, set()):
                raise ValueError("attachMovie symbol provenance mismatch")
            if definitions[cid] == "sprite":
                literal_attach_sprites.add(cid)

    label_sprites = defaultdict(set)
    timelines = timeline.get("timelines")
    if not isinstance(timelines, list) or len(timelines) != timeline.get("timeline_count"):
        raise ValueError("SWF timeline coverage mismatch")
    seen_timelines = set()
    for item in timelines:
        key = item.get("timeline")
        if not isinstance(key, str) or key in seen_timelines:
            raise ValueError("Invalid or duplicate timeline")
        seen_timelines.add(key)
        match = re.fullmatch(r"sprite:([1-9][0-9]*)", key)
        if match is None:
            continue
        cid = int(match.group(1))
        if definitions.get(cid) != "sprite":
            raise ValueError("FrameLabel timeline lacks Sprite definition")
        for label in item.get("frame_labels", []):
            if not isinstance(label.get("label"), str):
                raise ValueError("Invalid original FrameLabel")
            label_sprites[label["label"]].add(cid)

    role_sources = crosswalk.get("roles")
    role_calls = calls.get("roles")
    role_frames = frame_evidence.get("roles")
    if not all(isinstance(x, list) for x in (role_sources, role_calls, role_frames)):
        raise ValueError("Invalid role evidence")
    n = crosswalk.get("role_variant_count")
    if (len(role_sources) != n or len(role_calls) != n or len(role_frames) != n
            or calls.get("role_variant_count") != n
            or frame_evidence.get("role_variant_count") != n):
        raise ValueError("Role evidence coverage mismatch")

    def keyed(items: list) -> dict:
        result = {}
        for role in items:
            key = (role.get("character_candidate"), role.get("variant"))
            if (key in result or not all(isinstance(x, str) and x for x in key)):
                raise ValueError("Duplicate or invalid role")
            result[key] = role
        return result

    call_map, frame_map = keyed(role_calls), keyed(role_frames)
    counts = Counter({kind: 0 for kind in KINDS})
    output = []
    checked_calls = 0
    for role in role_sources:
        key = (role.get("character_candidate"), role.get("variant"))
        if key not in call_map or key not in frame_map:
            raise ValueError("Missing role call or FrameLabel evidence")
        call_role, frame_role = call_map[key], frame_map[key]
        path = role.get("verified_as2_script_path")
        if path not in file_map or call_role.get("verified_as2_script_path") != path:
            raise ValueError("Role script path mismatch")
        raw = (scripts_root / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if (digest != file_map[path].get("sha256")
                or digest != role.get("verified_as2_script_sha256")
                or digest != call_role.get("verified_as2_script_sha256")
                or digest != frame_role.get("verified_as2_script_sha256")
                or len(raw) != file_map[path].get("size_bytes")
                or len(raw) != role.get("verified_as2_script_size_bytes")):
            raise ValueError("Role script hash/length mismatch")
        parsed, literals = scan_calls(raw), _literal_arguments(raw)
        indexed = call_role.get("calls")
        frame_rows = frame_role.get("calls")
        if (not isinstance(indexed, list) or not isinstance(frame_rows, list)
                or len(parsed) != len(indexed) or len(literals) != len(parsed)
                or len(indexed) != call_role.get("call_candidate_count")):
            raise ValueError("Role callsite coverage mismatch")
        checked_calls += len(parsed)
        rows = []
        cursor = 0
        for call, recorded, literal in zip(parsed, indexed, literals):
            if any(call[k] != recorded.get(k)
                   for k in ("line", "method", "receiver_kind", "argument_kind")):
                raise ValueError("Role callsite provenance mismatch")
            if call["argument_kind"] != "string_literal":
                continue
            if cursor >= len(frame_rows):
                raise ValueError("Missing FrameLabel call row")
            frame = frame_rows[cursor]
            cursor += 1
            if call["line"] != frame.get("line") or call["method"] != frame.get("method"):
                raise ValueError("FrameLabel callsite provenance mismatch")
            candidates = label_sprites.get(literal, set()) if literal is not None else set()
            if len(candidates) != frame.get("matching_sprite_timeline_count"):
                raise ValueError("Original FrameLabel candidate count mismatch")
            exported = candidates & exports_by_id.keys()
            attached = exported & literal_attach_sprites
            if not candidates:
                kind = "no_sprite_label_candidate"
            elif not exported:
                kind = "sprite_not_exported"
            elif attached:
                kind = "literal_attach_overlap"
            else:
                kind = "exported_no_literal_attach"
            counts[kind] += 1
            rows.append({
                "line": call["line"], "method": call["method"],
                "candidate_sprite_count": len(candidates),
                "exported_candidate_sprite_count": len(exported),
                "literal_attach_candidate_sprite_count": len(attached),
                "classification": kind, "runtime_binding_verified": False,
            })
        if cursor != len(frame_rows) or cursor != frame_role.get("string_call_count"):
            raise ValueError("FrameLabel row accounting mismatch")
        output.append({"character_candidate": key[0], "variant": key[1],
                       "verified_as2_script_sha256": digest,
                       "string_call_count": len(rows), "calls": rows})
    if (set(call_map) != {(r["character_candidate"], r["variant"]) for r in role_sources}
            or set(frame_map) != set(call_map)
            or checked_calls != calls.get("call_candidate_count")
            or checked_calls != frame_evidence.get("call_candidate_count")
            or sum(counts.values()) != frame_evidence.get("string_literal_call_count")):
        raise ValueError("Crosswalk accounting mismatch")
    return {
        "source_sha256": source,
        "verified_script_count": len(files),
        "role_variant_count": n,
        "call_candidate_count": checked_calls,
        "string_literal_call_count": sum(counts.values()),
        "classification_counts": dict(counts),
        "literal_attach_sprite_symbol_count": len(literal_attach_sprites),
        "unresolved_attach_call_count": attach.get("classification_counts", {}).get(
            "dynamic_or_unresolved", 0),
        "roles": sorted(output, key=lambda x: (x["character_candidate"], x["variant"])),
        "limitations": [
            "ExportAssets and literal attachMovie overlap is only static lexical evidence.",
            "Dynamic attachMovie arguments and runtime MovieClip receivers are unresolved.",
            "No action frames, combat moves, collisions or playable character state inferred.",
            "No original FrameLabel text, symbol names, candidate Sprite IDs, AS2 bodies or media emitted.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    for name in ("scripts", "export-index", "role-crosswalk", "call-evidence",
                 "frame-label-evidence", "timeline-index", "asset-index",
                 "attach-evidence", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_join(
        a.scripts, *(load(getattr(a, name.replace("-", "_"))) for name in (
            "export-index", "role-crosswalk", "call-evidence", "frame-label-evidence",
            "timeline-index", "asset-index", "attach-evidence")))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("roles", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
