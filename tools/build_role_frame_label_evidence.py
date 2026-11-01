#!/usr/bin/env python3
"""Compare hash-verified AS2 goto string literals with original SWF FrameLabel tags.

Evidence only: lexical label equality is NOT a verified MovieClip runtime binding.
Never emit literal labels, original source, or original asset bytes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from build_as2_semantic_index import mask_comments_strings
from build_role_timeline_call_evidence import CALL, scan_calls

SHA = re.compile(r"[0-9a-f]{64}\Z")
PLAIN_LABEL = re.compile(r"\s*(['\"])([^'\"\\\r\n]*)\1\s*\)")
CATEGORIES = ("own_unique_candidate", "own_ambiguous_candidate",
              "other_only_candidate", "not_found", "escaped_or_unparsed")
PLACEMENT_CATEGORIES = ("own_timeline", "direct_child_candidate",
                        "nested_descendant_candidate", "other_unreachable_static",
                        "no_matching_label", "escaped_or_unparsed")


def _literal_arguments(raw: bytes) -> list[str | None]:
    source = raw.decode("utf-8", errors="replace")
    masked = mask_comments_strings(source)
    found = []
    for match in CALL.finditer(masked):
        if re.search(r"\bfunction\s+$", masked[max(0, match.start() - 64):match.start()]):
            continue
        token = PLAIN_LABEL.match(source, match.end())
        found.append(token.group(2) if token else None)
    return found


def build_evidence(scripts_root: Path, export: dict, crosswalk: dict,
                   calls: dict, timeline: dict) -> dict:
    sha = crosswalk.get("source_sha256")
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or any(
        x.get("source_sha256") != sha for x in (export, calls, timeline)
    ):
        raise ValueError("SWF source SHA-256 mismatch")
    files = export.get("files")
    if (not isinstance(files, list) or len(files) != export.get("script_count")
            or export.get("unexpected_empty_count", 0)):
        raise ValueError("Incomplete script export index")
    by_path = {}
    for f in files:
        p = f.get("path")
        if (not isinstance(p, str) or not p.startswith("scripts/") or not p.endswith(".as")
                or ".." in Path(p).parts or p in by_path):
            raise ValueError("Invalid or duplicate script export path")
        by_path[p] = f
    timelines = timeline.get("timelines")
    if not isinstance(timelines, list) or len(timelines) != timeline.get("timeline_count"):
        raise ValueError("Timeline coverage mismatch")
    labels = defaultdict(list)
    placed_sprites = defaultdict(set)
    seen_timeline = set()
    for item in timelines:
        key = item.get("timeline")
        if not isinstance(key, str) or key in seen_timeline:
            raise ValueError("Invalid or duplicate timeline")
        seen_timeline.add(key)
        for frame_label in item.get("frame_labels", []):
            label = frame_label.get("label")
            if not isinstance(label, str):
                raise ValueError("Invalid SWF FrameLabel")
            labels[label].append(key)
        for event in item.get("display_events", []):
            if event.get("kind") != "place" or "character_id" not in event:
                continue
            child_id = event["character_id"]
            if type(child_id) is not int or child_id <= 0:
                raise ValueError("Invalid static PlaceObject character ID")
            placed_sprites[key].add(f"sprite:{child_id}")
    # Only actual DefineSprite timelines are graph vertices. A PlaceObject
    # may reference a shape, button or other non-Sprite character instead.
    adjacency = {key: {child for child in children if child in seen_timeline}
                 for key, children in placed_sprites.items()}
    source_roles, call_roles = crosswalk.get("roles"), calls.get("roles")
    if (not isinstance(source_roles, list) or not isinstance(call_roles, list)
            or len(source_roles) != crosswalk.get("role_variant_count")
            or len(call_roles) != calls.get("role_variant_count")
            or len(source_roles) != len(call_roles)):
        raise ValueError("Role coverage mismatch")
    call_by_key = {}
    for role in call_roles:
        key = (role.get("character_candidate"), role.get("variant"))
        if key in call_by_key:
            raise ValueError("Duplicate call evidence role")
        call_by_key[key] = role
    seen_roles = set()
    counts = Counter({c: 0 for c in CATEGORIES})
    placement_counts = Counter({c: 0 for c in PLACEMENT_CATEGORIES})
    results = []
    checked_calls = 0
    for role in source_roles:
        key = (role.get("character_candidate"), role.get("variant"))
        if (key in seen_roles or key not in call_by_key or not all(
                isinstance(k, str) and k for k in key)):
            raise ValueError("Duplicate or missing role")
        seen_roles.add(key)
        other = call_by_key[key]
        path = role.get("verified_as2_script_path")
        record = by_path.get(path)
        if record is None or other.get("verified_as2_script_path") != path:
            raise ValueError("Missing verified role script path")
        raw = (scripts_root / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if (digest != role.get("verified_as2_script_sha256")
                or digest != other.get("verified_as2_script_sha256")
                or digest != record.get("sha256")
                or len(raw) != record.get("size_bytes")
                or len(raw) != role.get("verified_as2_script_size_bytes")):
            raise ValueError("Role script hash/length mismatch")
        parsed = scan_calls(raw)
        indexed = other.get("calls")
        if (not isinstance(indexed, list) or len(parsed) != len(indexed)
                or len(indexed) != other.get("call_candidate_count")):
            raise ValueError("Role callsite coverage mismatch")
        literal_args = _literal_arguments(raw)
        if len(literal_args) != len(parsed):
            raise ValueError("Callsite scan alignment mismatch")
        sprite_id = role.get("export_assets_character_id")
        if type(sprite_id) is not int or sprite_id <= 0:
            raise ValueError("Invalid role ExportAssets character ID")
        own = f"sprite:{sprite_id}"
        sprite = role.get("sprite_timeline")
        if sprite is not None and sprite.get("sprite_character_id") != sprite_id:
            raise ValueError("Role Sprite ID mismatch")
        # Union-of-ever-placed static graph, NOT a runtime display list.
        # A bounded BFS prevents infinite traversal through Sprite cycles.
        distances = {own: 0}
        queue = [own]
        for node in queue:
            for child in sorted(adjacency.get(node, ())):
                if child not in distances:
                    distances[child] = distances[node] + 1
                    queue.append(child)
        rows = []
        for parsed_call, indexed_call, literal in zip(parsed, indexed, literal_args):
            for field in ("line", "method", "receiver_kind", "argument_kind"):
                if parsed_call[field] != indexed_call.get(field):
                    raise ValueError("Callsite provenance mismatch: " + field)
            checked_calls += 1
            if parsed_call["argument_kind"] != "string_literal":
                continue
            occurrences = labels.get(literal, []) if literal is not None else []
            own_count = occurrences.count(own)
            other_count = len(occurrences) - own_count
            if literal is None:
                category = "escaped_or_unparsed"
            elif own_count == 1:
                category = "own_unique_candidate"
            elif own_count > 1:
                category = "own_ambiguous_candidate"
            elif other_count:
                category = "other_only_candidate"
            else:
                category = "not_found"
            counts[category] += 1
            matching_timelines = set(occurrences)
            reachable_hops = [distances[t] for t in matching_timelines if t in distances]
            minimum_hops = min(reachable_hops) if reachable_hops else None
            if literal is None:
                placement_relation = "escaped_or_unparsed"
            elif not matching_timelines:
                placement_relation = "no_matching_label"
            elif minimum_hops == 0:
                placement_relation = "own_timeline"
            elif minimum_hops == 1:
                placement_relation = "direct_child_candidate"
            elif minimum_hops is not None:
                placement_relation = "nested_descendant_candidate"
            else:
                placement_relation = "other_unreachable_static"
            placement_counts[placement_relation] += 1
            rows.append({"line": parsed_call["line"], "method": parsed_call["method"],
                         "receiver_kind": parsed_call["receiver_kind"],
                         "match_category": category,
                         "static_placement_relation": placement_relation,
                         "matching_timeline_count": len(matching_timelines),
                         "statically_reachable_timeline_count": len(reachable_hops),
                         "minimum_static_placement_hops": minimum_hops,
                         "own_timeline_label_occurrences": own_count,
                         "other_timeline_label_occurrences": other_count,
                         "runtime_binding_verified": False})
        results.append({"character_candidate": key[0], "variant": key[1],
                        "export_assets_character_id": sprite_id,
                        "verified_as2_script_sha256": digest,
                        "string_call_count": len(rows), "calls": rows})
    if (seen_roles != set(call_by_key) or checked_calls != calls.get("call_candidate_count")
            or sum(counts.values()) != calls.get("argument_kind_counts", {}).get("string_literal")
            or sum(placement_counts.values()) != sum(counts.values())):
        raise ValueError("FrameLabel evidence accounting mismatch")
    return {"source_sha256": sha, "role_variant_count": len(results),
            "call_candidate_count": checked_calls,
            "string_literal_call_count": sum(counts.values()),
            "frame_label_match_categories": dict(counts),
            "static_placement_relation_counts": dict(placement_counts),
            "roles": sorted(results, key=lambda x: (x["character_candidate"], x["variant"])),
            "limitations": [
                "FrameLabel equality is lexical only; runtime receiver and target timeline are unverified.",
                "String escapes and complex expressions are deliberately not resolved.",
                "Static PlaceObject reachability is a union of possible placements; dynamic attachMovie, time, depth and runtime receiver bindings are not modeled.",
                "A missing static path does NOT establish that a label or MovieClip is unreachable at runtime.",
                "No original label text, script source, media or inferred action frames are emitted.",
            ]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scripts", type=Path, required=True)
    p.add_argument("--export-index", type=Path, required=True)
    p.add_argument("--role-crosswalk", type=Path, required=True)
    p.add_argument("--call-evidence", type=Path, required=True)
    p.add_argument("--timeline-index", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = build_evidence(a.scripts, *[
        json.loads(path.read_text(encoding="utf-8")) for path in (
            a.export_index, a.role_crosswalk, a.call_evidence, a.timeline_index)])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"string_literal_call_count": result["string_literal_call_count"],
                      "frame_label_match_categories": result["frame_label_match_categories"],
                      "static_placement_relation_counts": result["static_placement_relation_counts"]}))


if __name__ == "__main__":
    main()
