#!/usr/bin/env python3
"""Cross-check zero-ShowFrame SWF class exports with verified FFDec AS2 paths.

Only metadata is emitted; a path match is NOT proof of runtime class binding.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*\Z")


def _valid_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _uint(value, name):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid " + name)
    return value


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate_path(name):
    if not isinstance(name, str):
        raise ValueError("Invalid ExportAssets name")
    parts = name.split(".")
    if len(parts) < 2 or parts[0] != "__Packages" or not all(IDENT.fullmatch(p) for p in parts):
        return None
    return "scripts/" + "/".join(parts) + ".as"


def build_zero_frame_as2_class_links(manifest: dict, asset: dict, export: dict) -> dict:
    sha = manifest["source"]["sha256"]
    if not _valid_sha(sha) or asset.get("source_sha256") != sha or export.get("source_sha256") != sha:
        raise ValueError("SWF source SHA-256 mismatch")
    if export.get("unexpected_empty_count", 0) != 0:
        raise ValueError("Unexplained empty FFDec exports")
    files = export["files"]
    if _uint(export["script_count"], "script count") != len(files):
        raise ValueError("FFDec script count mismatch")
    paths = {}
    for record in files:
        path = record["path"]
        if (not isinstance(path, str) or not path.startswith("scripts/")
                or not path.endswith(".as") or ".." in Path(path).parts
                or path in paths or not _valid_sha(record["sha256"])):
            raise ValueError("Invalid or duplicate verified script path/hash")
        _uint(record["size_bytes"], "script byte length")
        paths[path] = record

    tags = manifest["tags"]
    sprite_defs = {}
    sprite_show = Counter()
    init_targets = defaultdict(list)
    init_offsets = set()
    for tag in tags:
        code = _uint(tag["tag_code"], "tag code")
        timeline = tag["timeline"]
        if not isinstance(timeline, str):
            raise ValueError("Invalid timeline")
        if code == 39:
            sid = _uint(tag["character_id"], "sprite ID")
            if sid in sprite_defs:
                raise ValueError("Duplicate sprite ID")
            sprite_defs[sid] = tag
        elif code == 1:
            sprite_show[timeline] += 1
        elif code == 59:
            sid = _uint(tag["init_target_sprite_id"], "init target ID")
            key = (timeline, _uint(tag["offset_uncompressed"], "init tag offset"))
            if key in init_offsets:
                raise ValueError("Duplicate DoInitAction tag offset")
            init_offsets.add(key)
            init_targets[sid].append({
                "timeline": timeline,
                "frame_zero_based": _uint(tag["frame"], "init frame"),
                "offset_uncompressed": key[1],
                "tag_length_bytes": _uint(tag["length"], "init tag length"),
            })

    asset_defs = {}
    for item in asset["assets"]:
        sid = _uint(item["character_id"], "asset character ID")
        if sid in asset_defs:
            raise ValueError("Duplicate asset character ID")
        asset_defs[sid] = item
    names = defaultdict(list)
    if _uint(asset["exported_symbol_count"], "export count") != len(asset["export_assets"]):
        raise ValueError("Asset export count mismatch")
    if asset["export_assets"] != manifest["export_assets"]:
        raise ValueError("Asset and SWF ExportAssets disagree")
    for item in manifest["export_assets"]:
        names[_uint(item["character_id"], "export character ID")].append(item["name"])

    rows = []
    classes = Counter()
    zero_ids = []
    for sid, definition in sorted(sprite_defs.items()):
        if sprite_show[f"sprite:{sid}"] != 0:
            continue
        zero_ids.append(sid)
        asset_def = asset_defs.get(sid)
        if (asset_def is None or asset_def["category"] != "sprite"
                or asset_def["tag_code"] != 39
                or asset_def["offset_uncompressed"] != definition["offset_uncompressed"]):
            raise ValueError("Zero-frame sprite definition disagrees with asset index")
        for name in names[sid]:
            candidate = _candidate_path(name)
            record = paths.get(candidate) if candidate is not None else None
            classification = ("not_class_path" if candidate is None else
                              "verified_path_match" if record is not None else "unmatched_class_path")
            classes[classification] += 1
            rows.append({
                "sprite_character_id": sid,
                "sprite_definition_offset_uncompressed": _uint(definition["offset_uncompressed"], "offset"),
                "do_init_action_target_count": len(init_targets[sid]),
                "init_script_tags": sorted(init_targets[sid],
                                           key=lambda t: (t["timeline"], t["offset_uncompressed"])),
                "export_name_sha256": _digest(name),
                "classification": classification,
                "candidate_script_path_sha256": _digest(candidate) if candidate else None,
                "verified_script_sha256": record["sha256"] if record else None,
                "verified_script_size_bytes": record["size_bytes"] if record else None,
            })
    return {
        "source_sha256": sha,
        "verified_as2_script_count": len(paths),
        "zero_show_frame_sprite_count": len(zero_ids),
        "zero_sprite_export_count": len(rows),
        "zero_sprites_with_init_target": sum(bool(init_targets[sid]) for sid in zero_ids),
        "zero_sprite_init_tag_count": sum(len(init_targets[sid]) for sid in zero_ids),
        "zero_sprites_with_verified_class_and_init_tag": len({
            row["sprite_character_id"] for row in rows
            if row["classification"] == "verified_path_match"
            and init_targets[row["sprite_character_id"]]
        }),
        "zero_sprites_with_class_path_match": len({r["sprite_character_id"] for r in rows
                                                  if r["classification"] == "verified_path_match"}),
        "class_path_classifications": dict(sorted(classes.items())),
        "entries": rows,
        "limitations": [
            "Class paths are derived only by __Packages dotted-name to FFDec script-path convention.",
            "An existing, hash-verified AS2 export path is lexical evidence, not a runtime binding.",
            "DoInitAction frame/offset/length are parsed SWF tag metadata, not proof of execution.",
            "Zero ShowFrame does not prove that a sprite is an invisible class container.",
            "No source bodies, raw export names, script paths, images or audio are emitted.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--asset-index", type=Path, required=True)
    p.add_argument("--export-index", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_zero_frame_as2_class_links(read(a.manifest), read(a.asset_index), read(a.export_index))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("entries", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
