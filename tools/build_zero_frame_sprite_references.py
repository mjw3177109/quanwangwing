#!/usr/bin/env python3
"""Cross-reference zero-ShowFrame sprites with static SWF tags (metadata only)."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def _integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def build_zero_frame_sprite_references(manifest: dict, tail: dict) -> dict:
    sha = manifest["source"]["sha256"]
    if (not isinstance(sha, str) or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
            or tail["source_sha256"] != sha):
        raise ValueError("SWF source SHA-256 mismatch")

    declarations = {}
    timeline_tags = defaultdict(list)
    for tag in manifest["tags"]:
        name = tag["timeline"]
        if not isinstance(name, str) or not (name == "main" or name.startswith("sprite:")):
            raise ValueError("Invalid timeline name")
        timeline_tags[name].append(tag)
        if tag["tag_code"] == 39:
            sid = _integer(tag["character_id"], "sprite ID")
            key = f"sprite:{sid}"
            if key in declarations:
                raise ValueError("Duplicate sprite declaration")
            declarations[key] = _integer(tag["sprite_frame_count"], "declared frames")
    if set(timeline_tags) != set(declarations) | {"main"}:
        raise ValueError("Sprite timeline declarations mismatch")

    observed = {name: sum(t["tag_code"] == 1 for t in tags)
                for name, tags in timeline_tags.items()}
    expected_mismatches = {
        name for name, count in observed.items()
        if count != (manifest["stage"]["frame_count"] if name == "main" else declarations[name])
    }
    rows = tail["mismatches"]
    if (_integer(tail["mismatch_count"], "mismatch count") != len(rows)
            or len({r["timeline"] for r in rows}) != len(rows)
            or {r["timeline"] for r in rows} != expected_mismatches):
        raise ValueError("Frame-tail mismatch membership disagrees with original tags")

    zero_ids = {}
    for row in rows:
        name = row["timeline"]
        declared = manifest["stage"]["frame_count"] if name == "main" else declarations[name]
        if (row["declared_frames"] != declared
                or row["observed_show_frames"] != observed[name]
                or row["delta_observed_minus_declared"] != observed[name] - declared):
            raise ValueError("Frame-tail row disagrees with original tags")
        if row["tail_class"] != ("no_show_frame" if observed[name] == 0
                                 else row["tail_class"]):
            raise ValueError("Zero-ShowFrame classification mismatch")
        if name != "main" and observed[name] == 0:
            if row["tail_class"] != "no_show_frame":
                raise ValueError("Zero-ShowFrame classification mismatch")
            zero_ids[int(name.split(":", 1)[1])] = name
    if sum(tail["tail_class_counts"].values()) != len(rows):
        raise ValueError("Frame-tail classification accounting mismatch")

    incoming = defaultdict(list)
    for tag in manifest["tags"]:
        code = tag["tag_code"]
        if code in (4, 26, 70):
            sid = tag.get("character_id_reference")
            kind = "place"
        elif code == 59:
            sid = tag.get("init_target_sprite_id")
            kind = "init_action"
        else:
            continue
        if sid is None:
            continue
        _integer(sid, "referenced character ID")
        if sid in zero_ids:
            incoming[sid].append({
                "kind": kind, "tag_code": code,
                "timeline": tag["timeline"], "frame_zero_based": _integer(tag["frame"], "frame"),
                "offset_uncompressed": _integer(tag["offset_uncompressed"], "offset"),
            })

    exported = Counter()
    classes = Counter()
    for key, counter in (("export_assets", exported), ("symbol_class", classes)):
        for item in manifest[key]:
            sid = _integer(item["character_id"], "export character ID")
            if sid in zero_ids:
                counter[sid] += 1

    reports = []
    for sid in sorted(zero_ids):
        name = zero_ids[sid]
        tags = timeline_tags[name]
        internal = Counter(str(t["tag_code"]) for t in tags if t["tag_code"] != 0)
        refs = sorted(incoming[sid], key=lambda e: (e["offset_uncompressed"], e["tag_code"]))
        reports.append({
            "sprite_character_id": sid, "timeline": name,
            "declared_frames": declarations[name], "observed_show_frames": 0,
            "definition_offset_uncompressed": next(
                t["offset_uncompressed"] for t in manifest["tags"]
                if t["tag_code"] == 39 and t["character_id"] == sid),
            "internal_tag_counts_by_code": dict(sorted(internal.items(), key=lambda p: int(p[0]))),
            "static_place_reference_count": sum(e["kind"] == "place" for e in refs),
            "static_init_action_reference_count": sum(e["kind"] == "init_action" for e in refs),
            "export_asset_name_count": exported[sid],
            "symbol_class_name_count": classes[sid],
            "static_inbound_references": refs,
        })
    return {
        "source_sha256": sha,
        "zero_show_frame_sprite_count": len(reports),
        "sprites_with_static_place_reference": sum(r["static_place_reference_count"] > 0 for r in reports),
        "sprites_with_static_init_reference": sum(r["static_init_action_reference_count"] > 0 for r in reports),
        "sprites_with_export_name": sum(r["export_asset_name_count"] > 0 for r in reports),
        "sprites_with_symbol_class_name": sum(r["symbol_class_name_count"] > 0 for r in reports),
        "static_place_reference_count": sum(r["static_place_reference_count"] for r in reports),
        "static_init_action_reference_count": sum(r["static_init_action_reference_count"] for r in reports),
        "sprites": reports,
        "limitations": [
            "Static placement and linkage do not establish runtime reachability or visibility.",
            "ActionScript attachMovie and external loading are not resolved.",
            "No synthetic frame, original asset bytes, script bodies or export-name strings are emitted.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--tail", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = build_zero_frame_sprite_references(
        json.loads(a.manifest.read_text(encoding="utf-8")),
        json.loads(a.tail.read_text(encoding="utf-8")))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k.endswith("_count") and isinstance(v, int)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
