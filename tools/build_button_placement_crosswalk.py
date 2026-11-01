#!/usr/bin/env python3
"""Join verified DefineButton2 actions to static PlaceObject references (metadata only).

A static placement is a tag-level reference, not proof of runtime visibility,
input handling, activation, or a reachable UI state.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def _number(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def build_button_placement_crosswalk(manifest, buttons, timeline):
    source = manifest.get("source", {}).get("sha256")
    if not isinstance(source, str) or len(source) != 64 or any(c not in "0123456789abcdef" for c in source):
        raise ValueError("Invalid source SHA-256")
    if buttons.get("source_sha256") != source or timeline.get("source_sha256") != source:
        raise ValueError("Button placement source provenance mismatch")
    definitions = [t for t in manifest.get("tags", []) if t.get("tag_code") == 34]
    if len(definitions) != manifest.get("tag_counts_by_code", {}).get("34"):
        raise ValueError("DefineButton2 manifest count mismatch")
    definition_by_id = {}
    for tag in definitions:
        cid = _number(tag.get("character_id"), "button definition ID")
        if cid in definition_by_id:
            raise ValueError("Duplicate DefineButton2 character ID")
        definition_by_id[cid] = tag
    rows = buttons.get("buttons")
    if not isinstance(rows, list) or len(rows) != len(definitions) or buttons.get("define_button2_count") != len(rows):
        raise ValueError("Button evidence coverage mismatch")
    button_by_id = {}
    for row in rows:
        cid = _number(row.get("character_id"), "button ID")
        tag = definition_by_id.get(cid)
        if tag is None or cid in button_by_id:
            raise ValueError("Unknown or duplicate button evidence ID")
        if (row.get("tag_offset_uncompressed") != tag.get("offset_uncompressed")
                or row.get("timeline") != tag.get("timeline")
                or row.get("frame_zero_based") != tag.get("frame")):
            raise ValueError("Button definition provenance mismatch")
        count = _number(row.get("embedded_action_record_count"), "action record count")
        if count != len(row.get("embedded_action_records", [])):
            raise ValueError("Button action record mismatch")
        button_by_id[cid] = row
    if set(button_by_id) != set(definition_by_id):
        raise ValueError("Button definition IDs not fully covered")
    if sum(x["embedded_action_record_count"] for x in rows) != buttons.get("embedded_action_record_count"):
        raise ValueError("Embedded action record total mismatch")
    timelines = timeline.get("timelines")
    if not isinstance(timelines, list) or len(timelines) != timeline.get("timeline_count"):
        raise ValueError("Timeline inventory mismatch")
    tag_by_offset = {t["offset_uncompressed"]: t for t in manifest["tags"]}
    if len(tag_by_offset) != len(manifest["tags"]):
        raise ValueError("Duplicate SWF tag offset")
    placement_by_id = defaultdict(list)
    seen_timelines = set()
    for line in timelines:
        name = line.get("timeline")
        if not isinstance(name, str) or name in seen_timelines:
            raise ValueError("Duplicate or invalid timeline")
        seen_timelines.add(name)
        for event in line.get("display_events", []):
            if event.get("kind") != "place" or event.get("character_id") not in button_by_id:
                continue
            cid = event["character_id"]
            offset = _number(event.get("offset_uncompressed"), "placement offset")
            frame = _number(event.get("frame"), "placement frame")
            depth = _number(event.get("depth"), "placement depth")
            code = event.get("tag_code")
            tag = tag_by_offset.get(offset)
            if (code not in (4, 26, 70) or tag is None or tag.get("tag_code") != code
                    or tag.get("character_id_reference") != cid or tag.get("depth") != depth
                    or tag.get("frame") != frame or tag.get("timeline") != name):
                raise ValueError("Button placement tag provenance mismatch")
            placement_by_id[cid].append({
                "timeline": name, "frame_zero_based": frame, "depth": depth,
                "place_tag_code": code, "tag_offset_uncompressed": offset,
            })
    result_rows = []
    for cid in sorted(button_by_id):
        row = button_by_id[cid]
        placements = sorted(placement_by_id[cid], key=lambda e: (e["timeline"], e["frame_zero_based"], e["tag_offset_uncompressed"]))
        result_rows.append({
            "button_character_id": cid,
            "definition_tag_offset_uncompressed": row["tag_offset_uncompressed"],
            "embedded_action_record_count": row["embedded_action_record_count"],
            "static_placement_count": len(placements),
            "static_placements": placements,
        })
    all_placements = [p for row in result_rows for p in row["static_placements"]]
    return {
        "source_sha256": source,
        "button_definition_count": len(result_rows),
        "buttons_with_actions": sum(r["embedded_action_record_count"] > 0 for r in result_rows),
        "buttons_with_static_placement": sum(r["static_placement_count"] > 0 for r in result_rows),
        "action_bearing_buttons_with_static_placement": sum(r["embedded_action_record_count"] > 0 and r["static_placement_count"] > 0 for r in result_rows),
        "buttons_without_static_placement": sum(r["static_placement_count"] == 0 for r in result_rows),
        "static_placement_count": len(all_placements),
        "action_bearing_static_placement_count": sum(r["static_placement_count"] for r in result_rows if r["embedded_action_record_count"] > 0),
        "main_timeline_placement_count": sum(p["timeline"] == "main" for p in all_placements),
        "nested_timeline_placement_count": sum(p["timeline"] != "main" for p in all_placements),
        "buttons": result_rows,
        "limitations": [
            "Static PlaceObject references do not establish a live MovieClip, button activation, or UI reachability.",
            "Dynamic ActionScript attachment and conditional execution are not resolved.",
            "Action containers are not equivalent to commands, playable moves, or verified input mappings.",
            "Only character IDs, timeline IDs, frames, depths, offsets and counts are emitted; no original assets or scripts.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--buttons", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = [json.loads(p.read_text(encoding="utf-8")) for p in (args.manifest, args.buttons, args.timeline)]
    result = build_button_placement_crosswalk(*inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("buttons", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
