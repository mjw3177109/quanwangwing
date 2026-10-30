#!/usr/bin/env python3
"""Trace static SWF display-depth IDs at ShowFrame boundaries; metadata only."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

DISPLAY_CODES = {4, 5, 26, 28, 70}

def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid {label}")
    return value

def build_display_depth_evidence(manifest: dict) -> dict:
    sha = manifest["source"]["sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Invalid SWF source SHA-256")
    tags = manifest["tags"]
    declarations = {}
    for t in tags:
        if t["tag_code"] == 39:
            sid = _integer(t["character_id"], "sprite character ID")
            frames = _integer(t["sprite_frame_count"], "sprite declared frames")
            name = f"sprite:{sid}"
            if name in declarations:
                raise ValueError("Duplicate sprite declaration")
            declarations[name] = frames
    timelines = defaultdict(list)
    for t in tags:
        name = t["timeline"]
        if not isinstance(name, str) or (name != "main" and not name.startswith("sprite:")):
            raise ValueError("Invalid timeline name")
        timelines[name].append(t)
    expected = {"main": _integer(manifest["stage"]["frame_count"], "main declared frames"), **declarations}
    if set(timelines) != set(expected):
        raise ValueError("Timeline set disagrees with sprite declarations")
    reports = []
    totals = Counter()
    for name in sorted(timelines, key=lambda x: (-1 if x == "main" else int(x.split(":", 1)[1]))):
        active = {}
        snapshots = []
        anomalies = []
        event_count = 0
        previous_offset = -1
        for tag in timelines[name]:
            code = _integer(tag["tag_code"], "tag code")
            frame = _integer(tag["frame"], "frame")
            offset = _integer(tag["offset_uncompressed"], "tag offset")
            if offset <= previous_offset:
                raise ValueError("Non-increasing tag offsets in timeline")
            previous_offset = offset
            if code == 1:
                if frame != len(snapshots):
                    raise ValueError("Non-sequential ShowFrame index")
                snapshots.append({
                    "frame_zero_based": frame,
                    "show_frame_offset_uncompressed": offset,
                    "active_depths": [{"depth": depth, "character_id": active[depth]}
                                      for depth in sorted(active)],
                })
                continue
            if code not in DISPLAY_CODES:
                continue
            event_count += 1
            totals["display_events"] += 1
            depth = _integer(tag.get("depth"), "display depth")
            character = tag.get("character_id_reference")
            if character is not None:
                _integer(character, "display character ID")
            issue = None
            if code in (4, 26, 70):
                move = bool(tag.get("move", False)) if code == 4 else tag.get("move")
                if code != 4 and type(move) is not bool:
                    raise ValueError("Missing or invalid PlaceObject move flag")
                if character is not None:
                    if depth in active and not move:
                        issue = "placement_over_existing_depth"
                    active[depth] = character
                elif move:
                    if depth not in active:
                        issue = "modify_missing_depth"
                        active[depth] = None
                else:
                    issue = "placement_without_character_or_move"
            else:
                if depth not in active:
                    issue = "remove_missing_depth"
                elif code == 5 and active[depth] is not None and active[depth] != character:
                    issue = "remove_character_mismatch"
                active.pop(depth, None)
            if issue:
                anomalies.append({"frame_zero_based": frame, "offset_uncompressed": offset,
                                  "tag_code": code, "depth": depth, "kind": issue})
                totals[issue] += 1
        totals["show_frames"] += len(snapshots)
        reports.append({
            "timeline": name, "declared_frames": expected[name],
            "observed_show_frames": len(snapshots), "display_event_count": event_count,
            "frame_count_mismatch": expected[name] != len(snapshots),
            "anomalies": anomalies, "frames": snapshots,
        })
    return {
        "source_sha256": sha, "timeline_count": len(reports),
        "show_frame_count": totals["show_frames"],
        "display_event_count": totals["display_events"],
        "frame_count_mismatch_timelines": sum(t["frame_count_mismatch"] for t in reports),
        "anomaly_counts": {k: totals[k] for k in sorted(totals)
                           if k not in ("show_frames", "display_events")},
        "timelines": reports,
        "limitations": [
            "Only static display-depth character references are traced; this is not a rendered frame.",
            "PlaceObject2/3 move-only tags preserve the prior character ID, not its transforms.",
            "Unknown modifications use null, never a fabricated character ID.",
            "Sprite nesting, ActionScript placements, masks, transforms and gameplay are not resolved.",
            "No original artwork, audio, script or SWF payload bytes are emitted.",
        ],
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", type=Path, default=Path(__file__).resolve().parents[1] / "拳皇wing1.4.swf")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if hashlib.sha256(args.swf.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        raise SystemExit("Display depth evidence SWF SHA-256 mismatch")
    from build_script_entry_evidence import _check_tag
    from swf_inventory import load_swf
    data, _ = load_swf(args.swf)
    for tag in manifest["tags"]:
        if tag["tag_code"] in DISPLAY_CODES | {1, 39}:
            _check_tag(data, tag)
    report = build_display_depth_evidence(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "timeline_count", "show_frame_count", "display_event_count",
        "frame_count_mismatch_timelines", "anomaly_counts")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
