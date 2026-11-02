#!/usr/bin/env python3
"""Join byte-verified SWF ButtonCondAction records to FFDec export metadata.

This checks export file identity and coverage, NOT decompilation equivalence,
Flash runtime behavior, button activation, or game input semantics.
No original script or SWF bytes are emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

# Observed SWF condition flag -> observed FFDec 18.0.0 export event label.
# Intentionally NOT a general-purpose decoder: unknown/mixed flags fail closed.
# Key code 18 in this source is rendered as "Tab" by this FFDec version.
OBSERVED_EVENT_LABELS = {
    0x0001: "rollOver",
    0x0002: "rollOut",
    0x0004: "press",
    0x0008: "release",
    0x2400: "keyPress Tab",
}
BUTTON_EXPORT = re.compile(r"scripts/DefineButton2_(\d+)/BUTTONCONDACTION on\(([^/]+)\)\.as\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def build_button_ffdec_export_crosswalk(buttons: dict, exports: dict) -> dict:
    """Fail closed on source mismatch, missing, extra or ambiguous button scripts."""
    source = buttons.get("source_sha256")
    if type(source) is not str or not SHA256.fullmatch(source) or exports.get("source_sha256") != source:
        raise ValueError("Button/FFDec source SHA-256 mismatch")
    source_buttons = buttons.get("buttons")
    files = exports.get("files")
    if type(source_buttons) is not list or type(files) is not list:
        raise ValueError("Invalid source button or FFDec export rows")
    if _count(buttons.get("define_button2_count"), "button definition count") != len(source_buttons):
        raise ValueError("Button definition coverage mismatch")
    if _count(exports.get("script_count"), "FFDec script count") != len(files):
        raise ValueError("FFDec export index coverage mismatch")
    if _count(exports.get("total_bytes"), "FFDec byte total") != sum(
            _count(f.get("size_bytes"), "export file size") for f in files):
        raise ValueError("FFDec export byte accounting mismatch")

    button_files = {}
    all_paths = set()
    for item in files:
        path = item.get("path")
        if type(path) is not str or path in all_paths:
            raise ValueError("Duplicate or invalid FFDec export path")
        all_paths.add(path)
        if not path.startswith("scripts/DefineButton2_"):
            continue
        match = BUTTON_EXPORT.fullmatch(path)
        if not match or not SHA256.fullmatch(str(item.get("sha256"))):
            raise ValueError("Malformed or unverified FFDec button export metadata")
        _count(item.get("size_bytes"), "FFDec button script bytes")
        button_files[path] = item

    seen_buttons = set()
    used_paths = set()
    rows = []
    flags_histogram = Counter()
    for button in source_buttons:
        cid = _count(button.get("character_id"), "button character ID")
        if cid in seen_buttons:
            raise ValueError("Duplicate source button character ID")
        seen_buttons.add(cid)
        records = button.get("embedded_action_records")
        if type(records) is not list or _count(
                button.get("embedded_action_record_count"), "source action count") != len(records):
            raise ValueError("Source button action coverage mismatch")
        for record in records:
            flags = record.get("condition_flags")
            if type(flags) is not int or flags not in OBSERVED_EVENT_LABELS:
                raise ValueError("Unmapped source ButtonCondAction flags; FFDec review required")
            offset = _count(record.get("offset_uncompressed"), "source action offset")
            source_length = _count(record.get("action_bytes_including_terminator"),
                                   "source action byte length")
            if source_length == 0:
                raise ValueError("Empty source action container")
            event = OBSERVED_EVENT_LABELS[flags]
            path = f"scripts/DefineButton2_{cid}/BUTTONCONDACTION on({event}).as"
            if path not in button_files or path in used_paths:
                raise ValueError("Missing or ambiguous FFDec button event export")
            exported = button_files[path]
            used_paths.add(path)
            flags_histogram[f"0x{flags:04X}"] += 1
            rows.append({
                "button_character_id": cid,
                "action_offset_uncompressed": offset,
                "condition_flags": flags,
                "source_action_byte_length": source_length,
                "ffdec_event_label": event,
                "ffdec_export_path": path,
                "ffdec_export_size_bytes": exported["size_bytes"],
                "ffdec_export_sha256": exported["sha256"],
                "decompiled_semantics_verified": False,
                "runtime_behavior_verified": False,
            })
    if _count(buttons.get("embedded_action_record_count"), "source action total") != len(rows):
        raise ValueError("Source embedded action total mismatch")
    if _count(buttons.get("buttons_with_actions"), "buttons with actions") != sum(
            bool(b["embedded_action_records"]) for b in source_buttons):
        raise ValueError("Source action-bearing button count mismatch")
    if used_paths != set(button_files):
        raise ValueError("Extra or unmatched FFDec button export paths")
    return {
        "source_sha256": source,
        "source_button_definition_count": len(source_buttons),
        "source_action_record_count": len(rows),
        "ffdec_button_export_count": len(button_files),
        "matched_export_count": len(used_paths),
        "buttons_with_matched_exports": len({r["button_character_id"] for r in rows}),
        "condition_flag_counts": dict(sorted(flags_histogram.items())),
        "decompiled_semantics_verified": False,
        "runtime_behavior_verified": False,
        "records": sorted(rows, key=lambda r: (r["button_character_id"], r["action_offset_uncompressed"])),
        "limitations": [
            "SWF event flags are matched to observed FFDec 18.0.0 export filenames only.",
            "This verifies file existence and hash-index provenance, not source/decompilation equivalence.",
            "Unknown or combined event flags require manual mapping and fail closed.",
            "Button export paths are not proof of Flash VM execution, UI activation or combat inputs.",
            "Original SWF bytes and decompiled ActionScript remain off-artifact.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--buttons", type=Path, required=True)
    parser.add_argument("--export-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_button_ffdec_export_crosswalk(
        json.loads(args.buttons.read_text(encoding="utf-8")),
        json.loads(args.export_index.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
