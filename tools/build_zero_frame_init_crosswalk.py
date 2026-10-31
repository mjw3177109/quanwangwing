#!/usr/bin/env python3
"""Join zero-ShowFrame sprite static init references to byte-verified script entries.

Metadata only: initialization is not proof of visible rendering or runtime execution.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

SCRIPT_TAGS = {12, 59, 72, 82}


def _number(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def build_zero_frame_init_crosswalk(manifest: dict, zero: dict, scripts: dict) -> dict:
    sha = manifest["source"]["sha256"]
    if (not isinstance(sha, str) or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
            or zero["source_sha256"] != sha or scripts["source_sha256"] != sha):
        raise ValueError("SWF source SHA-256 mismatch")

    original_scripts = {}
    definitions = {}
    internal = defaultdict(Counter)
    for tag in manifest["tags"]:
        code = tag["tag_code"]
        key = (tag["timeline"], _number(tag["offset_uncompressed"], "tag offset"))
        if code in SCRIPT_TAGS:
            if key in original_scripts:
                raise ValueError("Duplicate original script offset")
            original_scripts[key] = tag
        if code == 39:
            sid = _number(tag["character_id"], "sprite ID")
            if sid in definitions:
                raise ValueError("Duplicate sprite definition")
            definitions[sid] = tag
        if tag["timeline"].startswith("sprite:") and code != 0:
            internal[tag["timeline"]][str(code)] += 1

    entries = scripts["entries"]
    if (_number(scripts["script_container_count"], "script count") != len(entries)
            or len(entries) != len(original_scripts)):
        raise ValueError("Script container accounting mismatch")
    entry_index = {}
    entry_counts = Counter()
    for entry in entries:
        key = (entry["timeline"], _number(entry["offset_uncompressed"], "script offset"))
        if key in entry_index:
            raise ValueError("Duplicate script entry offset")
        tag = original_scripts.get(key)
        if tag is None or any((entry["tag_code"] != tag["tag_code"],
                               entry["length"] != tag["length"],
                               entry["frame_zero_based"] != tag["frame"],
                               entry["frame_one_based"] != tag["frame"] + 1)):
            raise ValueError("Script entry disagrees with original SWF tag")
        if tag["tag_code"] == 59 and entry.get("init_target_sprite_id") != tag.get("init_target_sprite_id"):
            raise ValueError("DoInitAction target disagrees with original SWF tag")
        _number(entry["length"], "script length")
        entry_index[key] = entry
        entry_counts[str(tag["tag_code"])] += 1
    if entry_counts != Counter(scripts["script_container_counts_by_tag"]):
        raise ValueError("Script tag counts disagree with entry evidence")

    rows = zero["sprites"]
    if _number(zero["zero_show_frame_sprite_count"], "zero-frame sprite count") != len(rows):
        raise ValueError("Zero-frame sprite accounting mismatch")
    seen_ids = set()
    joined = []
    for sprite in rows:
        sid = _number(sprite["sprite_character_id"], "sprite ID")
        if sid in seen_ids:
            raise ValueError("Duplicate zero-frame sprite")
        seen_ids.add(sid)
        definition = definitions.get(sid)
        timeline = f"sprite:{sid}"
        if (definition is None or sprite["timeline"] != timeline
                or sprite["definition_offset_uncompressed"] != definition["offset_uncompressed"]
                or sprite["declared_frames"] != definition["sprite_frame_count"]
                or sprite["observed_show_frames"] != 0
                or Counter(sprite["internal_tag_counts_by_code"]) != internal[timeline]):
            raise ValueError("Zero-frame sprite disagrees with original SWF tags")
        refs = sprite["static_inbound_references"]
        if (sprite["static_init_action_reference_count"] != sum(r["kind"] == "init_action" for r in refs)
                or sprite["static_place_reference_count"] != sum(r["kind"] == "place" for r in refs)):
            raise ValueError("Static inbound reference accounting mismatch")
        for ref in refs:
            if ref["kind"] != "init_action":
                continue
            key = (ref["timeline"], _number(ref["offset_uncompressed"], "init offset"))
            tag = original_scripts.get(key)
            entry = entry_index.get(key)
            if (tag is None or entry is None or tag["tag_code"] != 59
                    or tag.get("init_target_sprite_id") != sid
                    or ref["tag_code"] != 59
                    or ref["frame_zero_based"] != tag["frame"]):
                raise ValueError("DoInitAction reference does not match script and SWF tag")
            joined.append({
                "sprite_character_id": sid,
                "sprite_definition_offset_uncompressed": definition["offset_uncompressed"],
                "sprite_internal_tag_count": sum(internal[timeline].values()),
                "sprite_export_name_count": _number(sprite["export_asset_name_count"], "export count"),
                "init_timeline": ref["timeline"],
                "init_frame_zero_based": tag["frame"],
                "init_script_offset_uncompressed": tag["offset_uncompressed"],
                "init_script_length_bytes": entry["length"],
            })

    if len(joined) != zero["static_init_action_reference_count"]:
        raise ValueError("Crosswalk init reference accounting mismatch")
    joined.sort(key=lambda r: (r["sprite_character_id"], r["init_script_offset_uncompressed"]))
    return {
        "source_sha256": sha,
        "zero_show_frame_sprite_count": len(rows),
        "matched_init_script_count": len(joined),
        "sprites_with_no_internal_tags": sum(not internal[f"sprite:{r['sprite_character_id']}"] for r in rows),
        "sprites_with_export_name": sum(r["export_asset_name_count"] > 0 for r in rows),
        "init_scripts_on_main_frame_zero": sum(r["init_timeline"] == "main" and r["init_frame_zero_based"] == 0 for r in joined),
        "init_script_container_bytes_total": sum(r["init_script_length_bytes"] for r in joined),
        "init_script_length_min_bytes": min((r["init_script_length_bytes"] for r in joined), default=None),
        "init_script_length_max_bytes": max((r["init_script_length_bytes"] for r in joined), default=None),
        "entries": joined,
        "limitations": [
            "DoInitAction static linkage does not establish runtime execution or visible sprite placement.",
            "Script length measures SWF tag body bytes, not functions or executable instruction count.",
            "No original script body, export-name string, artwork or audio is included.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--zero", type=Path, required=True)
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_zero_frame_init_crosswalk(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.zero.read_text(encoding="utf-8")),
        json.loads(args.scripts.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "entries" and k != "limitations"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
