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



def _source_scope(body: dict, origin: dict, payload_start: int, payload_end: int) -> dict:
    """Validate and expose half-open source coordinates, never source bytes."""
    keys = ("declaration_offset_uncompressed", "body_start_uncompressed",
            "body_end_uncompressed", "body_byte_length")
    values = [body.get(k) for k in keys]
    if any(type(v) is not int for v in values):
        raise ValueError("Invalid source function scope coordinates")
    declaration, start, end, size = values
    if not (payload_start <= declaration < start <= end <= payload_end and size == end - start):
        raise ValueError("Invalid source function scope boundaries")
    status = body.get("body_partition_status")
    if status not in ("partitioned", "rejected"):
        raise ValueError("Invalid source function scope partition status")
    # Cross-check complete origin evidence against the source ActionRecord histogram.
    if status == "partitioned" and origin.get("origin_status") == "bounded_origin_candidates":
        histogram = body.get("body_opcode_histogram")
        total = body.get("body_top_level_record_count")
        if (type(histogram) is not dict or type(total) is not int or total < 0
                or any(type(n) is not int or n < 0 for n in histogram.values())
                or sum(histogram.values()) != total):
            raise ValueError("Source function opcode histogram mismatch")
        for opcode, field in (("0x1c", "source_get_variable_opcode_count"),
                              ("0x1d", "source_set_variable_opcode_count"),
                              ("0x9d", "source_if_opcode_count")):
            if origin.get(field) != histogram.get(opcode, 0):
                raise ValueError("Source function operand opcode count mismatch")
    return {
        "declaration_offset_uncompressed": declaration,
        "body_start_uncompressed": start,
        "body_end_uncompressed_exclusive": end,
        "body_byte_length": size,
        "body_partition_status": status,
        "operand_origin_status": origin["origin_status"],
        "source_action_if_opcode_count": origin["source_if_opcode_count"],
    }


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
        # Preserve exact FFDec event-level review coordinates, not inferred
        # nested-function line mappings. Every hit is counted, including repeats.
        line_hits = lex.get("lexical_branch_keyword_line_numbers")
        word_counts = lex.get("lexical_branch_keyword_counts")
        if type(line_hits) is not dict or set(line_hits) != {"if", "return"} or type(word_counts) is not dict:
            raise ValueError("Missing FFDec branch line evidence")
        for word in ("if", "return"):
            lines, count = line_hits[word], word_counts.get(word)
            if (type(lines) is not list or type(count) is not int or count < 0
                    or len(lines) != count or any(type(n) is not int or n < 1 for n in lines)
                    or lines != sorted(lines)):
                raise ValueError("FFDec branch line/count mismatch")
        # Crosswalk event lengths were checked against the original SWF bytes.
        event_length = exp.get("source_action_byte_length")
        if type(event_length) is not int or event_length <= 0:
            raise ValueError("Invalid source button event payload length")
        payload_start = key[1] + 4  # CondActionSize and CondFlags
        payload_end = payload_start + event_length
        bodies = src.get("bytecode_function_body_ranges") or []
        if classification != "source_partition_rejected" and len(bodies) != src["bytecode_declared_function_count"]:
            raise ValueError("Source function range count mismatch")
        body_rows = []
        scope_rows = []
        seen_starts = set()
        last_body_end = payload_start
        for body in sorted(bodies, key=lambda item: item["declaration_offset_uncompressed"]):
            origin_key = (key[0], body["body_start_uncompressed"])
            origin = origin_index.get(origin_key)
            if origin is None:
                raise ValueError("Missing source-backed operand provenance")
            if origin_key in seen_starts:
                raise ValueError("Duplicate source function scope")
            seen_starts.add(origin_key)
            scope = _source_scope(body, origin, payload_start, payload_end)
            if scope["declaration_offset_uncompressed"] < last_body_end:
                raise ValueError("Overlapping source function scopes")
            last_body_end = scope["body_end_uncompressed_exclusive"]
            scope_rows.append(scope)
            used_origins.add(origin_key)
            body_rows.append(origin)
        if classification == "neither_detected":
            continue
        complete = bool(body_rows) and all(
            x["origin_status"] == "bounded_origin_candidates" for x in body_rows) and all(
            x["body_partition_status"] == "partitioned" for x in scope_rows)
        queue.append({
            "button_character_id": key[0],
            "action_offset_uncompressed": key[1],
            "comparison_class": classification,
            "ffdec_export_path": exp["ffdec_export_path"],
            "ffdec_export_sha256": hashes[0],
            "source_function_declaration_count": src["bytecode_declared_function_count"],
            "source_function_body_count": len(body_rows),
            "source_function_scopes": scope_rows,
            "source_action_if_opcode_count": sum(x["source_if_opcode_count"] or 0 for x in body_rows),
            "ffdec_event_lexical_function_candidate_count": lex["lexical_function_candidate_count"],
            "ffdec_event_lexical_if_keyword_count": lex["lexical_branch_keyword_counts"].get("if", 0),
            "ffdec_event_lexical_return_keyword_count": lex["lexical_branch_keyword_counts"].get("return", 0),
            "ffdec_event_lexical_if_line_numbers": line_hits["if"],
            "ffdec_event_lexical_return_line_numbers": line_hits["return"],
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
            "FFDec lexical keyword counts and line numbers cover the whole button event, not the nested function.",
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
