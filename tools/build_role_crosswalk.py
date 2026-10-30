#!/usr/bin/env python3
"""Join verified AS2 role paths to ExportAssets IDs and sprite timelines.

Provenance-only metadata. Does NOT infer gameplay state, attack frames, hitboxes,
damage, keyboard bindings, or character selectability.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def _positive_line(value: object) -> bool:
    return type(value) is int and value > 0


def _scope_evidence(scope: dict, path: str) -> dict:
    start, end = scope.get("start_line"), scope.get("end_line")
    if not _positive_line(start) or not _positive_line(end) or end < start:
        raise ValueError("Invalid AS2 scope line interval: " + path)
    counts = scope.get("marker_counts", {})
    lines = scope.get("marker_lines", {})
    if not isinstance(counts, dict) or not isinstance(lines, dict):
        raise ValueError("Invalid AS2 marker evidence: " + path)
    for kind, positions in lines.items():
        if not isinstance(positions, list) or not all(
            _positive_line(n) and start <= n <= end for n in positions
        ):
            raise ValueError("Marker line outside function scope: " + path)
        if kind not in counts or type(counts[kind]) is not int or counts[kind] < len(set(positions)):
            raise ValueError("Marker count inconsistent with lines: " + path)
    if not isinstance(scope.get("name"), str) or not scope["name"]:
        raise ValueError("Missing function candidate identifier: " + path)
    return {
        "name": scope["name"],
        "kind": scope["kind"],
        "start_line": start,
        "end_line": end,
        "marker_counts": counts,
        "marker_lines": lines,
    }


def build_crosswalk(asset: dict, timeline: dict, semantic: dict) -> dict:
    hashes = [item.get("source_sha256") for item in (asset, timeline, semantic)]
    if not hashes[0] or len(set(hashes)) != 1:
        raise ValueError("SWF source SHA-256 mismatch across evidence indexes")
    if semantic.get("verified_script_count", 0) < 1:
        raise ValueError("No verified AS2 script index")

    script_by_path = {}
    for item in semantic.get("candidate_scripts", []):
        path = item.get("path")
        if not path or path in script_by_path:
            raise ValueError("Duplicate or missing AS2 candidate script path")
        script_by_path[path] = item

    role_by_key = {}
    for item in semantic.get("role_script_candidates", []):
        key = (item.get("character_candidate"), item.get("variant"))
        if key in role_by_key:
            raise ValueError("Duplicate AS2 role candidate: " + str(key))
        role_by_key[key] = item

    timeline_by_id = {}
    for item in timeline.get("timelines", []):
        sprite_id = item.get("sprite_character_id")
        if sprite_id is None:
            continue
        if sprite_id in timeline_by_id:
            raise ValueError("Duplicate sprite timeline character ID")
        timeline_by_id[sprite_id] = item

    result = []
    seen = set()
    for character in asset.get("character_class_candidates", []):
        name = character["class_name"]
        for variant, field in (
            ("base", "base_role_character_id"),
            ("type2", "type2_role_character_id"),
        ):
            sprite_id = character.get(field)
            if sprite_id is None:
                continue
            key = (name, variant)
            if key in seen:
                raise ValueError("Duplicate ExportAssets role class: " + str(key))
            seen.add(key)
            role = role_by_key.get(key)
            if not role or role.get("export_present") is not True:
                raise ValueError("Missing verified AS2 role mapping: " + str(key))
            path = role.get("expected_script_path")
            script = script_by_path.get(path)
            if not script or not script.get("role_candidate"):
                raise ValueError("Missing hashed AS2 role script summary: " + str(key))
            if not script.get("sha256") or not isinstance(script.get("size_bytes"), int):
                raise ValueError("Incomplete AS2 role script provenance: " + path)

            scopes = [_scope_evidence(s, path) for s in script.get("function_scopes", [])]
            sprite = timeline_by_id.get(sprite_id)
            timeline_ref = None
            if sprite is not None:
                timeline_ref = {
                    "timeline": sprite["timeline"],
                    "sprite_character_id": sprite_id,
                    "declared_frames": sprite["declared_frames"],
                    "observed_show_frames": sprite["observed_show_frames"],
                    "frame_label_count": len(sprite.get("frame_labels", [])),
                    "script_event_count": len(sprite.get("script_events", [])),
                    "display_event_count": len(sprite.get("display_events", [])),
                    "sound_event_count": len(sprite.get("sound_events", [])),
                }
            result.append({
                "character_candidate": name,
                "variant": variant,
                "export_assets_character_id": sprite_id,
                "verified_as2_script_path": path,
                "verified_as2_script_sha256": script["sha256"],
                "verified_as2_script_size_bytes": script["size_bytes"],
                "function_scope_candidate_count": len(scopes),
                "function_scope_candidates": scopes,
                "sprite_timeline": timeline_ref,
                "link_basis": "ExportAssets role class ID + verified FFDec class script path",
            })

    if not result:
        raise ValueError("No role candidates to cross-reference")
    if set(role_by_key) != seen:
        raise ValueError("AS2 role mapping and ExportAssets role candidates differ")
    result.sort(key=lambda r: (r["character_candidate"], r["variant"]))
    marker_totals = Counter()
    for item in result:
        for scope in item["function_scope_candidates"]:
            marker_totals.update(scope["marker_counts"])
    return {
        "source_sha256": hashes[0],
        "role_variant_count": len(result),
        "role_candidate_names": sorted({item["character_candidate"] for item in result}),
        "linked_sprite_timeline_count": sum(item["sprite_timeline"] is not None for item in result),
        "unlinked_sprite_timeline_count": sum(item["sprite_timeline"] is None for item in result),
        "function_scope_candidate_count": sum(item["function_scope_candidate_count"] for item in result),
        "function_marker_counts": dict(sorted(marker_totals.items())),
        "roles": result,
        "limitations": [
            "ExportAssets links a class symbol ID; it does not prove that a candidate is selectable.",
            "A matching DefineSprite timeline does not prove an AS2 function drives that timeline.",
            "Function identifiers, line ranges and markers are lexical evidence, not a call graph.",
            "No original script bodies, original assets, damage values, hitboxes or action frames are included.",
            "Absent sprite timeline references are reported explicitly rather than guessed.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-index", type=Path, required=True)
    parser.add_argument("--timeline-index", type=Path, required=True)
    parser.add_argument("--semantic-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_crosswalk(
        json.loads(args.asset_index.read_text(encoding="utf-8")),
        json.loads(args.timeline_index.read_text(encoding="utf-8")),
        json.loads(args.semantic_index.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "role_variants": result["role_variant_count"],
        "linked_sprite_timelines": result["linked_sprite_timeline_count"],
        "unlinked_sprite_timelines": result["unlinked_sprite_timeline_count"],
        "function_scope_candidates": result["function_scope_candidate_count"],
        "function_marker_counts": result["function_marker_counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
