#!/usr/bin/env python3
"""Metadata-only triage of original button bytecode versus FFDec event lexical evidence.

A lexical keyword count describes an entire exported button event, not a nested
DefineFunction body. This tool does not infer decompiler errors or VM behavior.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def _index(records, name):
    result = {}
    for row in records:
        key = (row["button_character_id"], row["action_offset_uncompressed"])
        if key in result:
            raise ValueError(f"Duplicate {name} button event provenance")
        result[key] = row
    return result


def build_review_queue(join: dict, lexical: dict, crosswalk: dict, origins: dict) -> dict:
    sha = join["source_sha256"]
    if any(d["source_sha256"] != sha for d in (lexical, crosswalk, origins)):
        raise ValueError("Cross-report SWF source hash mismatch")
    j = _index(join["records"], "join")
    l = _index(lexical["records"], "lexical")
    c = _index(crosswalk["records"], "crosswalk")
    if not (set(j) == set(l) == set(c)):
        raise ValueError("Button event coverage mismatch")
    if (len(j) != join["compared_button_action_count"]
            or len(l) != lexical["audited_button_action_count"]
            or len(c) != crosswalk["matched_export_count"]):
        raise ValueError("Button event summary coverage mismatch")

    origin_index = {}
    for row in origins["records"]:
        key = (row["button_character_id"], row["function_body_start_uncompressed"])
        if key in origin_index:
            raise ValueError("Duplicate function operand provenance")
        origin_index[key] = row

    queue = []
    classifications = Counter()
    used_origins = set()
    for key in sorted(j):
        src, lex, exp = j[key], l[key], c[key]
        classification = src["comparison_class"]
        classifications[classification] += 1
        hashes = (src["ffdec_export_sha256"], lex["ffdec_export_sha256"],
                  exp["ffdec_export_sha256"])
        if len(set(hashes)) != 1 or lex["ffdec_export_path"] != exp["ffdec_export_path"]:
            raise ValueError("FFDec export path or content hash mismatch")
        if src["lexical_function_candidate_count"] != lex["lexical_function_candidate_count"]:
            raise ValueError("Lexical function count mismatch")
        bodies = src.get("bytecode_function_body_ranges") or []
        if classification != "source_partition_rejected" and len(bodies) != src["bytecode_declared_function_count"]:
            raise ValueError("Source function range count mismatch")
        body_rows = []
        for body in bodies:
            origin_key = (key[0], body["body_start_uncompressed"])
            origin = origin_index.get(origin_key)
            if origin is None:
                raise ValueError("Missing source-backed operand provenance")
            used_origins.add(origin_key)
            body_rows.append(origin)
        if classification == "neither_detected":
            continue
        complete = bool(body_rows) and all(
            x["origin_status"] == "bounded_origin_candidates" for x in body_rows)
        queue.append({
            "button_character_id": key[0],
            "action_offset_uncompressed": key[1],
            "comparison_class": classification,
            "ffdec_export_path": exp["ffdec_export_path"],
            "ffdec_export_sha256": hashes[0],
            "source_function_declaration_count": src["bytecode_declared_function_count"],
            "source_function_body_count": len(body_rows),
            "source_action_if_opcode_count": sum(x["source_if_opcode_count"] or 0 for x in body_rows),
            "ffdec_event_lexical_function_candidate_count": lex["lexical_function_candidate_count"],
            "ffdec_event_lexical_if_keyword_count": lex["lexical_branch_keyword_counts"].get("if", 0),
            "ffdec_event_lexical_return_keyword_count": lex["lexical_branch_keyword_counts"].get("return", 0),
            "operand_origin_statuses": sorted({x["origin_status"] for x in body_rows}),
            "operand_origins_complete": complete,
            "source_if_operand_origin_types": sorted({
                kind for x in body_rows for kind in (x["if_operand_origin_counts"] or {})
            }) if complete else None,
            "manual_semantic_review_required": True,
            "decompiled_semantics_verified": False,
            "runtime_behavior_verified": False,
        })
    if used_origins != set(origin_index) or len(origin_index) != origins["function_body_count"]:
        raise ValueError("Unmatched source-backed operand function ranges")
    if dict(classifications) != {k: v for k, v in join["classification_counts"].items() if v}:
        raise ValueError("Source comparison classification totals mismatch")
    return {
        "source_sha256": sha,
        "compared_button_action_count": len(j),
        "manual_review_queue_count": len(queue),
        "manual_review_classification_counts": dict(sorted(Counter(
            x["comparison_class"] for x in queue).items())),
        "decompiled_semantics_verified": False,
        "runtime_behavior_verified": False,
        "records": queue,
        "limitations": [
            "FFDec lexical keyword counts cover the whole button event, not the nested function.",
            "Lexical mismatch is a review candidate, not proof of a decompiler defect.",
            "No source operands, ActionScript body, images, sound or gameplay values are emitted.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    for arg in ("join", "lexical", "crosswalk", "origins", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    inputs = [json.loads(getattr(args, x).read_text(encoding="utf-8"))
              for x in ("join", "lexical", "crosswalk", "origins")]
    report = build_review_queue(*inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("records", "limitations")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
