#!/usr/bin/env python3
"""Classify SWF timeline tags after the final ShowFrame (metadata only)."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def _int(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {name}")
    return value


def build_frame_tail_evidence(manifest: dict, audit: dict) -> dict:
    sha = manifest["source"]["sha256"]
    if (not isinstance(sha, str) or len(sha) != 64
            or any(c not in "0123456789abcdef" for c in sha)
            or sha != audit["source_sha256"]):
        raise ValueError("Invalid or mismatched source SHA-256")
    by_timeline = defaultdict(list)
    for tag in manifest["tags"]:
        name = tag["timeline"]
        if not isinstance(name, str) or not (name == "main" or name.startswith("sprite:")):
            raise ValueError("Invalid timeline")
        by_timeline[name].append(tag)
    mismatch_rows = audit["mismatches"]
    if _int(audit["mismatch_count"], "mismatch count") != len(mismatch_rows):
        raise ValueError("Audit mismatch count disagrees with rows")
    if _int(audit["timeline_count"], "timeline count") != len(by_timeline):
        raise ValueError("Audit timeline count mismatch")
    declared = {"main": _int(manifest["stage"]["frame_count"], "main declared frames")}
    for tag in manifest["tags"]:
        if tag["tag_code"] == 39:
            key = f"sprite:{_int(tag['character_id'], 'sprite ID')}"
            if key in declared:
                raise ValueError("Duplicate sprite declaration")
            declared[key] = _int(tag["sprite_frame_count"], "sprite declared frames")
    if set(declared) != set(by_timeline):
        raise ValueError("Timeline declarations mismatch")
    indexed = {}
    for row in mismatch_rows:
        name = row["timeline"]
        if name in indexed or name not in by_timeline:
            raise ValueError("Duplicate or unknown mismatch timeline")
        indexed[name] = row
    results = []
    classes = Counter()
    trailing_codes = Counter()
    show_total = 0
    for name, tags in by_timeline.items():
        prev_offset = -1
        show_count = 0
        end_count = 0
        last_show_index = -1
        for i, tag in enumerate(tags):
            offset = _int(tag["offset_uncompressed"], "tag offset")
            code = _int(tag["tag_code"], "tag code")
            frame = _int(tag["frame"], "tag frame")
            if offset <= prev_offset:
                raise ValueError("Non-increasing timeline tag offsets")
            if frame != show_count:
                raise ValueError("Unexpected tag frame index")
            prev_offset = offset
            if code == 1:
                last_show_index = i
                show_count += 1
            elif code == 0:
                end_count += 1
                if i != len(tags) - 1:
                    raise ValueError("End tag is not last")
        if end_count != 1:
            raise ValueError("Missing or duplicate End tag")
        show_total += show_count
        delta = show_count - declared[name]
        if (delta != 0) != (name in indexed):
            raise ValueError("Mismatch membership disagrees with original tags")
        if not delta:
            continue
        row = indexed[name]
        end = tags[-1]
        last_show = tags[last_show_index] if last_show_index >= 0 else None
        if (row["declared_frames"] != declared[name]
                or row["observed_show_frames"] != show_count
                or row["delta_observed_minus_declared"] != delta
                or row["end_tag_offset_uncompressed"] != end["offset_uncompressed"]
                or row["last_show_frame_offset_uncompressed"] !=
                (last_show["offset_uncompressed"] if last_show else None)):
            raise ValueError("Frame audit row disagrees with original tags")
        tail = tags[last_show_index + 1:-1]
        counts = Counter(str(t["tag_code"]) for t in tail)
        for code, count in counts.items():
            trailing_codes[code] += count
        kind = ("no_show_frame" if last_show is None else
                "pending_tags_after_last_show" if tail else "end_directly_after_show")
        classes[kind] += 1
        results.append({
            "timeline": name, "declared_frames": declared[name],
            "observed_show_frames": show_count,
            "delta_observed_minus_declared": delta,
            "tail_class": kind,
            "tags_between_last_show_and_end": len(tail),
            "tail_tag_counts_by_code": dict(sorted(counts.items(), key=lambda p: int(p[0]))),
            "first_tail_tag_offset_uncompressed": tail[0]["offset_uncompressed"] if tail else None,
            "last_tail_tag_offset_uncompressed": tail[-1]["offset_uncompressed"] if tail else None,
            "last_show_frame_offset_uncompressed": last_show["offset_uncompressed"] if last_show else None,
            "end_tag_offset_uncompressed": end["offset_uncompressed"],
        })
    if (len(results) != len(indexed)
            or show_total != audit["show_frame_count"]
            or sum(classes.values()) != len(results)):
        raise ValueError("Aggregate frame-tail accounting mismatch")
    results.sort(key=lambda r: (r["timeline"] != "main", r["timeline"]))
    return {
        "source_sha256": sha, "timeline_count": len(by_timeline),
        "show_frame_count": show_total, "mismatch_count": len(results),
        "tail_class_counts": dict(sorted(classes.items())),
        "tail_tag_counts_by_code": dict(sorted(trailing_codes.items(), key=lambda p: int(p[0]))),
        "mismatches": results,
        "limitations": [
            "Trailing tags are static positions, not proof of a missing playable frame.",
            "No frame is synthesized; ActionScript and runtime rendering are not evaluated.",
            "No original SWF, ActionScript, artwork, or audio payload is included.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    m = json.loads(args.manifest.read_text(encoding="utf-8"))
    a = json.loads(args.audit.read_text(encoding="utf-8"))
    result = build_frame_tail_evidence(m, a)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("timeline_count", "mismatch_count", "tail_class_counts", "tail_tag_counts_by_code")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
