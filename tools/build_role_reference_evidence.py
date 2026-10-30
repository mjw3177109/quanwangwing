#!/usr/bin/env python3
"""Trace role ExportAssets IDs to direct SWF placement and DoInitAction tags.

Metadata only: no script bodies, assets, gameplay claims or runtime inference.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def _nonnegative(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid " + label)
    return value


def build_role_reference_evidence(crosswalk: dict, timeline: dict) -> dict:
    sha = crosswalk.get("source_sha256")
    if not sha or sha != timeline.get("source_sha256"):
        raise ValueError("SWF source SHA-256 mismatch")
    roles = crosswalk.get("roles")
    if not isinstance(roles, list) or not roles or len(roles) != crosswalk.get("role_variant_count"):
        raise ValueError("Role crosswalk count mismatch")
    by_id = {}
    for role in roles:
        cid = _nonnegative(role.get("export_assets_character_id"), "role character ID")
        if cid == 0 or cid in by_id:
            raise ValueError("Duplicate or zero role character ID")
        sprite = role.get("sprite_timeline")
        if sprite is not None and sprite.get("sprite_character_id") != cid:
            raise ValueError("Role Sprite character ID mismatch")
        if not role.get("verified_as2_script_path") or not role.get("verified_as2_script_sha256"):
            raise ValueError("Missing verified AS2 script provenance")
        by_id[cid] = role
    references = {cid: {"placements": [], "init_targets": []} for cid in by_id}
    seen = set()
    for parent in timeline.get("timelines", []):
        name = parent.get("timeline")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Duplicate or invalid parent timeline")
        seen.add(name)
        for event in parent.get("display_events", []):
            cid = event.get("character_id")
            if event.get("kind") != "place" or cid not in by_id:
                continue
            if event.get("tag_code") not in (4, 26, 70):
                raise ValueError("Invalid role placement tag code")
            record = {
                "parent_timeline": name,
                "frame": _nonnegative(event.get("frame"), "event frame"),
                "offset_uncompressed": _nonnegative(event.get("offset_uncompressed"), "tag offset"),
                "tag_code": event["tag_code"],
                "depth": _nonnegative(event.get("depth"), "display depth"),
                "move": event.get("move") if type(event.get("move")) is bool else None,
            }
            references[cid]["placements"].append(record)
        for event in parent.get("script_events", []):
            cid = event.get("init_target_sprite_id")
            if event.get("tag_code") != 59 or cid not in by_id:
                continue
            references[cid]["init_targets"].append({
                "parent_timeline": name,
                "frame": _nonnegative(event.get("frame"), "event frame"),
                "offset_uncompressed": _nonnegative(event.get("offset_uncompressed"), "tag offset"),
                "tag_code": 59,
            })
    records = []
    for cid, role in sorted(by_id.items(), key=lambda pair: (pair[1]["character_candidate"], pair[1]["variant"])):
        sortkey = lambda e: (e["parent_timeline"], e["frame"], e["offset_uncompressed"])
        places = sorted(references[cid]["placements"], key=sortkey)
        inits = sorted(references[cid]["init_targets"], key=sortkey)
        records.append({
            "character_candidate": role["character_candidate"],
            "variant": role["variant"],
            "export_assets_character_id": cid,
            "verified_as2_script_path": role["verified_as2_script_path"],
            "verified_as2_script_sha256": role["verified_as2_script_sha256"],
            "direct_placement_count": len(places),
            "direct_parent_timeline_count": len({x["parent_timeline"] for x in places}),
            "do_init_action_target_count": len(inits),
            "direct_placements": places,
            "do_init_action_targets": inits,
        })
    return {
        "source_sha256": sha,
        "role_variant_count": len(records),
        "direct_placement_count": sum(r["direct_placement_count"] for r in records),
        "do_init_action_target_count": sum(r["do_init_action_target_count"] for r in records),
        "roles_with_direct_placements": sum(bool(r["direct_placements"]) for r in records),
        "roles_with_do_init_action_targets": sum(bool(r["do_init_action_targets"]) for r in records),
        "roles": records,
        "limitations": [
            "Only direct PlaceObject references with explicit role character IDs are counted.",
            "DoInitAction targets are initialization references, not gameplay calls.",
            "Zero direct references do not imply an unplayable or unused character.",
            "No action frames, damage, hitboxes or runtime call graph are inferred.",
            "No original ActionScript bodies or asset bytes are included.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--crosswalk", type=Path, required=True)
    p.add_argument("--timeline-index", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    data = build_role_reference_evidence(
        json.loads(a.crosswalk.read_text(encoding="utf-8")),
        json.loads(a.timeline_index.read_text(encoding="utf-8")),
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "role_variants": data["role_variant_count"],
        "direct_placements": data["direct_placement_count"],
        "do_init_action_targets": data["do_init_action_target_count"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
