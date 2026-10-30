#!/usr/bin/env python3
"""Join byte-verified SWF StartSound and script container locations.

Same-frame proximity is co-location only, not proof of script-triggered audio.
No ActionScript, SOUNDINFO, audio or SWF payload bytes are emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

SCRIPT_TAGS = {12, 59, 72, 82}


def _script_key(entry):
    return (entry["timeline"], entry["frame_zero_based"],
            entry["offset_uncompressed"], entry["tag_code"])


def _sound_key(entry):
    return (entry["timeline"], entry["frame_zero_based"],
            entry["offset_uncompressed"], entry["sound_id"])


def build_sound_script_crosswalk(manifest: dict, sound: dict, script: dict) -> dict:
    sha = manifest["source"]["sha256"]
    if not sha or sound["source_sha256"] != sha or script["source_sha256"] != sha:
        raise ValueError("SWF source SHA-256 mismatch across evidence")

    expected_scripts = [
        (t["timeline"], t["frame"], t["offset_uncompressed"], t["tag_code"])
        for t in manifest["tags"] if t["tag_code"] in SCRIPT_TAGS
    ]
    actual_scripts = [_script_key(e) for e in script["entries"]]
    if actual_scripts != expected_scripts or script["script_container_count"] != len(expected_scripts):
        raise ValueError("Script entry report disagrees with original tag inventory")
    expected_sounds = [
        (t["timeline"], t["frame"], t["offset_uncompressed"], t["sound_id_reference"])
        for t in manifest["tags"] if t["tag_code"] == 15
    ]
    actual_sounds = [_sound_key(e) for e in sound["start_events"]]
    if actual_sounds != expected_sounds or sound["start_sound_count"] != len(expected_sounds):
        raise ValueError("StartSound report disagrees with original tag inventory")

    by_frame = defaultdict(list)
    for e in script["entries"]:
        by_frame[(e["timeline"], e["frame_zero_based"])].append(e)
    counts_by_sound = Counter()
    counts_by_timeline = Counter()
    events = []
    matched = 0
    pairs = 0
    for e in sound["start_events"]:
        scripts = by_frame.get((e["timeline"], e["frame_zero_based"]), [])
        counts_by_sound[str(e["sound_id"])] += 1
        counts_by_timeline[e["timeline"]] += 1
        if scripts:
            matched += 1
        pairs += len(scripts)
        events.append({
            "timeline": e["timeline"],
            "frame_zero_based": e["frame_zero_based"],
            "sound_id": e["sound_id"],
            "start_sound_offset_uncompressed": e["offset_uncompressed"],
            "same_frame_script_container_count": len(scripts),
            "same_frame_script_containers": [
                {"tag_code": s["tag_code"],
                 "offset_uncompressed": s["offset_uncompressed"],
                 "relative_tag_order": "before" if s["offset_uncompressed"] < e["offset_uncompressed"] else "after"}
                for s in scripts
            ],
        })
    return {
        "source_sha256": sha,
        "script_container_count": len(expected_scripts),
        "start_sound_count": len(events),
        "sound_events_with_same_frame_scripts": matched,
        "sound_events_without_same_frame_scripts": len(events) - matched,
        "same_frame_sound_script_pairs": pairs,
        "start_sound_counts_by_id": dict(sorted(counts_by_sound.items(), key=lambda x: int(x[0]))),
        "start_sound_counts_by_timeline": dict(sorted(counts_by_timeline.items())),
        "events": events,
        "limitations": [
            "Same timeline/frame is structural co-location, not evidence that a script triggers a sound.",
            "Tag order is byte order in the decompressed SWF, not runtime execution order.",
            "Script containers are not functions; AS1/AS2 semantics and external scripts are unresolved.",
            "DoInitAction can initialize symbols and is not a confirmed per-frame sound trigger.",
            "No original script, SOUNDINFO envelope, audio, artwork or combat data is included.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sound", type=Path, required=True)
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_sound_script_crosswalk(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.sound.read_text(encoding="utf-8")),
        json.loads(args.scripts.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "script_container_count", "start_sound_count", "sound_events_with_same_frame_scripts",
        "sound_events_without_same_frame_scripts", "same_frame_sound_script_pairs")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
