#!/usr/bin/env python3
"""Evidence-only per-frame SWF reference map; no original assets or script bodies."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def build_timeline_index(manifest: dict) -> dict:
    tags = manifest["tags"]
    declared = {
        f"sprite:{t['character_id']}": t["sprite_frame_count"]
        for t in tags if t["tag_code"] == 39
    }
    names = defaultdict(list)
    for symbol in manifest["export_assets"] + manifest["symbol_class"]:
        names[symbol["character_id"]].append(symbol["name"])
    defined = {c["character_id"] for c in manifest["characters"]}
    timelines = {}
    referenced = set()
    unknown_next = Counter()

    for i, tag in enumerate(tags):
        name = tag["timeline"]
        if name not in timelines:
            sprite_id = int(name.split(":", 1)[1]) if name.startswith("sprite:") else None
            timelines[name] = {
                "timeline": name, "sprite_character_id": sprite_id,
                "export_names": names.get(sprite_id, []) if sprite_id is not None else [],
                "declared_frames": declared.get(name, manifest["stage"]["frame_count"]),
                "observed_show_frames": 0, "tag_counts": Counter(),
                "frame_labels": [], "script_events": [], "display_events": [],
                "sound_events": [], "unknown_tag_events": [],
            }
        timeline = timelines[name]
        code = tag["tag_code"]
        timeline["tag_counts"][str(code)] += 1
        event = {
            "frame": tag["frame"],
            "offset_uncompressed": tag["offset_uncompressed"],
        }
        if code == 1:
            timeline["observed_show_frames"] += 1
        elif code == 43:
            timeline["frame_labels"].append({**event, "label": tag.get("frame_label")})
        elif code in (4, 26, 70):
            item = {**event, "kind": "place", "tag_code": code, "depth": tag.get("depth")}
            if "character_id_reference" in tag:
                char_id = tag["character_id_reference"]
                item["character_id"] = char_id
                item["export_names"] = names.get(char_id, [])
                referenced.add(char_id)
            if "move" in tag:
                item["move"] = tag["move"]
            timeline["display_events"].append(item)
        elif code in (5, 28):
            item = {**event, "kind": "remove", "tag_code": code, "depth": tag.get("depth")}
            if "character_id_reference" in tag:
                item["character_id"] = tag["character_id_reference"]
            timeline["display_events"].append(item)
        elif code == 15:
            sound_id = tag.get("sound_id_reference")
            timeline["sound_events"].append({
                **event, "sound_id": sound_id,
                "export_names": names.get(sound_id, []),
            })
            if sound_id is not None:
                referenced.add(sound_id)
        elif code in (12, 59, 72, 82):
            item = {**event, "tag_code": code, "length": tag["length"]}
            if "init_target_sprite_id" in tag:
                sprite_id = tag["init_target_sprite_id"]
                item["init_target_sprite_id"] = sprite_id
                item["target_export_names"] = names.get(sprite_id, [])
                referenced.add(sprite_id)
            timeline["script_events"].append(item)
        elif code in (253, 255):
            next_tag = tags[i + 1] if i + 1 < len(tags) else None
            next_code = next_tag["tag_code"] if next_tag and next_tag["timeline"] == name else None
            timeline["unknown_tag_events"].append({
                **event, "tag_code": code, "length": tag["length"],
                "next_tag_code_same_timeline": next_code,
            })
            if code == 253:
                unknown_next[str(next_code)] += 1

    ordered = sorted(timelines, key=lambda n: -1 if n == "main" else int(n.split(":", 1)[1]))
    return {
        "source_sha256": manifest["source"]["sha256"],
        "stage": manifest["stage"],
        "timeline_count": len(timelines),
        "script_event_count": sum(len(t["script_events"]) for t in timelines.values()),
        "display_event_count": sum(len(t["display_events"]) for t in timelines.values()),
        "sound_event_count": sum(len(t["sound_events"]) for t in timelines.values()),
        "frame_label_count": sum(len(t["frame_labels"]) for t in timelines.values()),
        "unknown_tag_253_next_code_counts": dict(sorted(unknown_next.items(), key=lambda x: int(x[0]))),
        "references_without_local_definition": sorted(referenced - defined),
        "timelines": [
            {**timelines[name],
             "tag_counts": dict(sorted(timelines[name]["tag_counts"].items(), key=lambda x: int(x[0])))}
            for name in ordered
        ],
        "limitations": [
            "This index is reference metadata, not reconstructed ActionScript or gameplay.",
            "Unknown tags 253/255 are recorded by offset and adjacency only; their meaning is unknown.",
            "No original asset bytes, script bodies, hitboxes, move timings or damage values are included.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("build/swf-analysis/swf-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("build/swf-analysis/timeline-index.json"))
    args = parser.parse_args()
    result = build_timeline_index(json.loads(args.manifest.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "timeline_count": result["timeline_count"],
        "script_events": result["script_event_count"],
        "display_events": result["display_event_count"],
        "sound_events": result["sound_event_count"],
        "frame_labels": result["frame_label_count"],
        "unknown_253_next": result["unknown_tag_253_next_code_counts"],
        "references_without_local_definition": len(result["references_without_local_definition"]),
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
