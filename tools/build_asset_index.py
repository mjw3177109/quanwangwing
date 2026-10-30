#!/usr/bin/env python3
"""Create a compact, traceable asset/class index from the SWF tag manifest.

No original bitmaps, sounds, ActionScript source, or other copyrighted payloads
are copied into this index. Names are raw ExportAssets evidence, not a claim
that any candidate character is selectable in-game.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, Counter
import json
from pathlib import Path
import re

CATEGORY_BY_TAG = {
    2: "shape", 22: "shape", 32: "shape", 83: "shape",
    46: "morphshape", 84: "morphshape",
    6: "image", 20: "image", 21: "image", 35: "image",
    36: "image", 90: "image",
    39: "sprite",
    14: "sound",
    7: "button", 34: "button",
    10: "font", 48: "font", 75: "font", 91: "font",
    11: "text", 33: "text", 37: "text",
    60: "video", 87: "binary",
}
ROLE_CLASS = re.compile(r"^__Packages\.(Type2_)?([A-Za-z0-9]+)_role$")


def build_index(manifest: dict) -> dict:
    source = manifest["source"]
    stage = manifest["stage"]
    exports = manifest["export_assets"]
    definitions = manifest["characters"]
    names_by_id = defaultdict(list)
    for e in exports:
        names_by_id[e["character_id"]].append(e["name"])

    assets = []
    categories = Counter()
    for definition in definitions:
        code = definition["tag_code"]
        category = CATEGORY_BY_TAG.get(code, "other_definition")
        categories[category] += 1
        assets.append({
            "character_id": definition["character_id"],
            "category": category,
            "tag_code": code,
            "tag_name": definition["tag_name"],
            "timeline": definition["timeline"],
            "offset_uncompressed": definition["offset_uncompressed"],
            "export_names": names_by_id.get(definition["character_id"], []),
        })

    candidates = {}
    for e in exports:
        match = ROLE_CLASS.fullmatch(e["name"])
        if not match:
            continue
        variant, name = match.groups()
        entry = candidates.setdefault(name, {
            "class_name": name, "base_role_character_id": None,
            "type2_role_character_id": None, "evidence": [],
        })
        field = "type2_role_character_id" if variant else "base_role_character_id"
        entry[field] = e["character_id"]
        entry["evidence"].append(e["name"])

    return {
        "source_sha256": source["sha256"],
        "source_filename": source["filename"],
        "stage": stage,
        "asset_definition_count": len(assets),
        "asset_categories": dict(sorted(categories.items())),
        "exported_symbol_count": len(exports),
        "export_assets": exports,
        "assets": assets,
        "script_tags": manifest["scripts"],
        "character_class_candidates": sorted(
            candidates.values(),
            key=lambda x: (
                x["base_role_character_id"] if x["base_role_character_id"] is not None
                else 1 << 30,
                x["class_name"],
            ),
        ),
        "limitations": [
            "A class name is not proof of a selectable character or a finished animation.",
            "ActionScript semantics, collision boxes and moves are not yet reconstructed.",
            "Unknown/custom SWF tag payloads are not decoded here.",
            "This index contains references and metadata only, no original asset bytes.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path,
                        default=Path("build/swf-analysis/swf-manifest.json"))
    parser.add_argument("--output", type=Path,
                        default=Path("build/swf-analysis/asset-index.json"))
    args = parser.parse_args()
    index = build_index(json.loads(args.manifest.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "asset_definitions": index["asset_definition_count"],
        "categories": index["asset_categories"],
        "exported_names": index["exported_symbol_count"],
        "character_class_candidates": [
            x["class_name"] for x in index["character_class_candidates"]
        ],
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
