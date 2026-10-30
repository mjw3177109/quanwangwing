#!/usr/bin/env python3
"""Audit declared versus observed SWF timeline frames using metadata only."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def _nonnegative_int(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def build_frame_count_audit(manifest: dict, depth: dict) -> dict:
    source = manifest["source"]["sha256"]
    if source != depth["source_sha256"]:
        raise ValueError("Source SHA-256 mismatch")
    if not isinstance(source, str) or len(source) != 64 or any(c not in "0123456789abcdef" for c in source):
        raise ValueError("Invalid source SHA-256")
    declarations = {"main": _nonnegative_int(manifest["stage"]["frame_count"], "main frames")}
    tags_by_timeline = defaultdict(list)
    for tag in manifest["tags"]:
        timeline = tag["timeline"]
        tags_by_timeline[timeline].append(tag)
        if tag["tag_code"] == 39:
            name = f"sprite:{_nonnegative_int(tag['character_id'], 'sprite ID')}"
            if name in declarations:
                raise ValueError("Duplicate sprite declaration")
            declarations[name] = _nonnegative_int(tag["sprite_frame_count"], "sprite frames")
    reports = depth["timelines"]
    if depth["timeline_count"] != len(reports) or len({r["timeline"] for r in reports}) != len(reports):
        raise ValueError("Duplicate or inconsistent depth timelines")
    if set(declarations) != set(tags_by_timeline) or set(declarations) != {r["timeline"] for r in reports}:
        raise ValueError("Timeline set mismatch")
    mismatches = []
    histogram = Counter()
    direction = Counter()
    observed_total = 0
    for report in reports:
        name = report["timeline"]
        declared = declarations[name]
        observed = _nonnegative_int(report["observed_show_frames"], "observed frames")
        frames = report["frames"]
        original = tags_by_timeline[name]
        show = [tag for tag in original if tag["tag_code"] == 1]
        if (report["declared_frames"] != declared or observed != len(frames) or observed != len(show)
                or report["frame_count_mismatch"] != (declared != observed)):
            raise ValueError("Frame count evidence disagrees with original tags")
        if any(f["frame_zero_based"] != i or f["show_frame_offset_uncompressed"] != show[i]["offset_uncompressed"]
               for i, f in enumerate(frames)):
            raise ValueError("ShowFrame offset or index mismatch")
        observed_total += observed
        delta = observed - declared
        if delta:
            kind = "surplus" if delta > 0 else "shortfall"
            direction[kind] += 1
            histogram[str(delta)] += 1
            end_tags = [t for t in original if t["tag_code"] == 0]
            if len(end_tags) != 1:
                raise ValueError("Timeline End tag missing or duplicated")
            mismatches.append({
                "timeline": name,
                "declared_frames": declared,
                "observed_show_frames": observed,
                "delta_observed_minus_declared": delta,
                "last_show_frame_offset_uncompressed": show[-1]["offset_uncompressed"] if show else None,
                "end_tag_offset_uncompressed": end_tags[0]["offset_uncompressed"],
                "script_tag_count": sum(t["tag_code"] in (12, 59, 72, 82) for t in original),
                "display_tag_count": sum(t["tag_code"] in (4, 5, 26, 28, 70) for t in original),
            })
    if (observed_total != depth["show_frame_count"] or
            len(mismatches) != depth["frame_count_mismatch_timelines"]):
        raise ValueError("Aggregate frame accounting mismatch")
    mismatches.sort(key=lambda r: (r["timeline"] != "main", -abs(r["delta_observed_minus_declared"]), r["timeline"]))
    return {
        "source_sha256": source,
        "timeline_count": len(reports),
        "show_frame_count": observed_total,
        "mismatch_count": len(mismatches),
        "mismatch_direction_counts": dict(sorted(direction.items())),
        "delta_histogram": dict(sorted(histogram.items(), key=lambda x: int(x[0]))),
        "mismatches": mismatches,
        "limitations": [
            "Declared and observed frame differences are structural facts, not proof of malformed SWF.",
            "A tag position is not a rendered animation frame, runtime action, or hitbox.",
            "No original SWF, ActionScript, audio or image payload is included.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--depth", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    m = json.loads(args.manifest.read_text(encoding="utf-8"))
    d = json.loads(args.depth.read_text(encoding="utf-8"))
    audit = build_frame_count_audit(m, d)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("timeline_count", "show_frame_count", "mismatch_count", "mismatch_direction_counts", "delta_histogram")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
