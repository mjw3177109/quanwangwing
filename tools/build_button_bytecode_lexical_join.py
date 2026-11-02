#!/usr/bin/env python3
"""Join source SWF ActionRecord function declarations with FFDec lexical candidates.

Metadata-only discrepancy locator; neither semantic equivalence nor VM execution.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from button_action_structure import ActionStructureError, partition_top_level_actions

CLASSES = (
    "neither_detected", "bytecode_only_candidate", "lexical_only_candidate",
    "both_present_unverified", "source_partition_rejected",
)


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid " + label)
    return value


def _index(rows, label):
    result = {}
    for row in rows:
        if type(row) is not dict:
            raise ValueError("Invalid " + label + " row")
        key = (_count(row.get("button_character_id"), "button ID"),
               _count(row.get("action_offset_uncompressed"), "action offset"))
        if key in result:
            raise ValueError("Duplicate " + label + " source key")
        result[key] = row
    return result


def join_button_bytecode_lexical(buttons: dict, lexical: dict, crosswalk: dict,
                                 decompressed: bytes, source_sha256: str) -> dict:
    if (type(source_sha256) is not str or len(source_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in source_sha256)):
        raise ValueError("Invalid source SHA-256")
    if any(d.get("source_sha256") != source_sha256 for d in (buttons, lexical, crosswalk)):
        raise ValueError("SWF source SHA-256 mismatch")
    if any(d.get("decompiled_semantics_verified") is not False or
           d.get("runtime_behavior_verified") is not False for d in (lexical, crosswalk)):
        raise ValueError("Unsupported semantics/runtime claim")
    if type(buttons.get("buttons")) is not list:
        raise ValueError("Invalid button evidence")
    source_rows = {}
    for button in buttons["buttons"]:
        cid = _count(button.get("character_id"), "button character ID")
        events = button.get("embedded_action_records")
        if (type(events) is not list or
                len(events) != _count(button.get("embedded_action_record_count"), "button record count")):
            raise ValueError("Invalid embedded button records")
        for event in events:
            key = (cid, _count(event.get("offset_uncompressed"), "action offset"))
            if key in source_rows:
                raise ValueError("Duplicate original button action source key")
            source_rows[key] = event
    if len(source_rows) != _count(buttons.get("embedded_action_record_count"), "source count"):
        raise ValueError("Original button record count mismatch")
    lex_rows, cross_rows = lexical.get("records"), crosswalk.get("records")
    if type(lex_rows) is not list or type(cross_rows) is not list:
        raise ValueError("Missing lexical or crosswalk rows")
    if (len(lex_rows) != _count(lexical.get("audited_button_action_count"), "lexical count") or
            len(cross_rows) != _count(crosswalk.get("matched_export_count"), "crosswalk count") or
            len(cross_rows) != _count(crosswalk.get("source_action_record_count"), "crosswalk source count")):
        raise ValueError("Reported record coverage mismatch")
    lex_index, cross_index = _index(lex_rows, "lexical"), _index(cross_rows, "crosswalk")
    if set(source_rows) != set(lex_index) or set(source_rows) != set(cross_index):
        raise ValueError("Missing or extra source-keyed button record")
    totals = Counter({cls: 0 for cls in CLASSES})
    raw_total = lexical_total = rejected = body_byte_total = 0
    rows = []
    for key in sorted(source_rows):
        event, lex, cross = source_rows[key], lex_index[key], cross_index[key]
        if (event.get("condition_flags") != cross.get("condition_flags") or
                event.get("action_bytes_including_terminator") != cross.get("source_action_byte_length") or
                lex.get("ffdec_export_path") != cross.get("ffdec_export_path") or
                lex.get("ffdec_export_sha256") != cross.get("ffdec_export_sha256") or
                any(row.get("decompiled_semantics_verified") is not False or
                    row.get("runtime_behavior_verified") is not False for row in (lex, cross))):
            raise ValueError("Button source/export provenance or verification mismatch")
        candidates = _count(lex.get("lexical_function_candidate_count"), "lexical candidates")
        matched = _count(lex.get("lexical_matched_function_scope_count"), "matched lexical scopes")
        unmatched = _count(lex.get("lexical_unmatched_function_candidate_count"), "unmatched lexical scopes")
        if candidates != matched + unmatched:
            raise ValueError("Lexical candidate accounting mismatch")
        offset = key[1]
        length = _count(event.get("action_bytes_including_terminator"), "action length")
        if length == 0 or offset + 4 + length > len(decompressed):
            raise ValueError("Button action payload outside decompressed SWF")
        # CondActionSize and CondFlags are two little-endian words immediately
        # before the ActionRecord bytes. Re-read the original bytes rather than
        # trusting two mutually consistent, potentially forged metadata reports.
        raw_size = int.from_bytes(decompressed[offset:offset + 2], "little")
        raw_flags = int.from_bytes(decompressed[offset + 2:offset + 4], "little")
        if raw_flags != event.get("condition_flags"):
            raise ValueError("ButtonCondAction raw header condition flags mismatch")
        final_by_zero = event.get("is_last_by_zero_size")
        if type(final_by_zero) is not bool or final_by_zero != (raw_size == 0):
            raise ValueError("ButtonCondAction final-record marker mismatch")
        if raw_size != 0 and raw_size != length + 4:
            raise ValueError("ButtonCondAction CondActionSize/action length mismatch")
        payload = decompressed[offset + 4:offset + 4 + length]
        if event.get("ends_with_action_end") is not (payload[-1] == 0):
            raise ValueError("Button ActionEnd provenance mismatch")
        try:
            parsed = partition_top_level_actions(payload)
        except ActionStructureError:
            status, functions, function_ranges = "source_partition_rejected", None, None
            rejected += 1
        else:
            functions = _count(parsed["declared_function_count"], "bytecode function count")
            # Source-relative half-open ranges locate the actual declared function
            # bodies for restricted FFDec review, without exposing names or bytes.
            function_ranges = [{
                "opcode": "DefineFunction" if rec.opcode == 0x9B else "DefineFunction2",
                "declaration_offset_uncompressed": offset + 4 + rec.start,
                "body_start_uncompressed": offset + 4 + rec.body_start,
                "body_end_uncompressed": offset + 4 + rec.body_end,
                "body_byte_length": rec.body_end - rec.body_start,
            } for rec in parsed["records"] if rec.body_start is not None]
            if (len(function_ranges) != functions or
                    sum(item["body_byte_length"] for item in function_ranges)
                    != parsed["declared_function_body_byte_total"]):
                raise ValueError("Function body range accounting mismatch")
            body_byte_total += parsed["declared_function_body_byte_total"]
            raw_total += functions
            status = ("both_present_unverified" if functions and candidates else
                      "bytecode_only_candidate" if functions else
                      "lexical_only_candidate" if candidates else "neither_detected")
        totals[status] += 1
        lexical_total += candidates
        rows.append({
            "button_character_id": key[0],
            "action_offset_uncompressed": offset,
            "ffdec_export_sha256": lex["ffdec_export_sha256"],
            "bytecode_declared_function_count": functions,
            "bytecode_function_body_ranges": function_ranges,
            "lexical_function_candidate_count": candidates,
            "comparison_class": status,
            "decompiled_semantics_verified": False,
            "runtime_behavior_verified": False,
        })
    if lexical_total != _count(lexical.get("lexical_function_candidate_total"), "lexical total"):
        raise ValueError("Lexical report total mismatch")
    return {
        "source_sha256": source_sha256,
        "compared_button_action_count": len(rows),
        "source_partition_rejected_count": rejected,
        "bytecode_declared_function_total_on_partitioned_records": raw_total,
        "bytecode_function_body_byte_total_on_partitioned_records": body_byte_total,
        "lexical_function_candidate_total": lexical_total,
        "classification_counts": dict(totals),
        "decompiled_semantics_verified": False,
        "runtime_behavior_verified": False,
        "records": rows,
        "limitations": [
            "SWF bytecode declarations and FFDec lexical functions are different representations.",
            "A zero lexical count does not prove FFDec omitted or miscompiled a function.",
            "Function body offsets are half-open source locations, not verified execution paths.",
            "Function bodies are not decoded or semantically compared with FFDec output.",
            "No original script text, function names, SWF bytes, or media are emitted.",
            "No Flash VM execution, semantic equivalence, move or 1:1 fidelity is established.",
        ],
    }


def main():
    from swf_inventory import load_swf
    parser = argparse.ArgumentParser()
    parser.add_argument("--swf", required=True, type=Path)
    parser.add_argument("--buttons", required=True, type=Path)
    parser.add_argument("--lexical", required=True, type=Path)
    parser.add_argument("--crosswalk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_sha = hashlib.sha256(args.swf.read_bytes()).hexdigest()
    data, _ = load_swf(args.swf)
    result = join_button_bytecode_lexical(
        json.loads(args.buttons.read_text(encoding="utf-8")),
        json.loads(args.lexical.read_text(encoding="utf-8")),
        json.loads(args.crosswalk.read_text(encoding="utf-8")), data, source_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
