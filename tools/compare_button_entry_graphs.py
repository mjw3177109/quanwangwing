#!/usr/bin/env python3
"""Compare legacy flat and partition-aware button graphs by verified source key.

This is metadata-only diagnostic evidence, not a migration of legacy consumers
or proof that a syntactic Flash action path executes at runtime.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid nonnegative count: {label}")
    return value


def _flag(value, label):
    if type(value) is not bool:
        raise ValueError(f"Invalid boolean flag: {label}")
    return value


def _index(rows, label):
    result = {}
    for row in rows:
        key = (row["button_character_id"], row["action_offset_uncompressed"])
        if (any(type(x) is not int or x < 0 for x in key) or key in result):
            raise ValueError(f"Duplicate or invalid {label} source key")
        result[key] = row
    return result


def compare_entry_graphs(legacy: dict, partitioned: dict) -> dict:
    """Join legacy tail-only rows against all partitioned rows; never guess gaps."""
    source = legacy["source_sha256"]
    if (type(source) is not str or len(source) != 64
            or any(ch not in "0123456789abcdef" for ch in source)
            or partitioned["source_sha256"] != source):
        raise ValueError("Entry graph source SHA-256 mismatch")
    old_rows = legacy["graphs"]
    new_rows = partitioned["records"]
    if (_count(legacy["graph_record_count"], "legacy graph count") != len(old_rows)
            or _count(partitioned["embedded_action_record_count"],
                      "partitioned action count") != len(new_rows)):
        raise ValueError("Entry graph source row coverage mismatch")
    if (_flag(legacy["runtime_reachability_verified"], "legacy runtime")
            or _flag(partitioned["runtime_reachability_verified"],
                     "partitioned runtime")):
        raise ValueError("Unverified runtime execution claimed")
    old_index = _index(old_rows, "legacy")
    new_index = _index(new_rows, "partitioned")
    if not old_index.keys() <= new_index.keys():
        raise ValueError("Legacy graph missing from partitioned source coverage")
    if (_count(partitioned["graph_verified_count"], "verified graph count") !=
            sum(row["graph_verified"] is True for row in new_rows)):
        raise ValueError("Partitioned graph verified-count mismatch")

    compared = skipped = changed_paths = changed_visits = changed_post_end = 0
    visit_delta = post_end_delta = shadowed_legacy = 0
    status_counts = Counter()
    rows = []
    for key, old in old_index.items():
        new = new_index[key]
        if (_flag(old["runtime_reachability_verified"], "legacy row runtime")
                or _flag(new["runtime_reachability_verified"], "new row runtime")):
            raise ValueError("Unverified row runtime execution claimed")
        shadowed = _count(old["visited_define_function_body_shadowed_record_count"],
                          "legacy function-body shadowed count")
        shadowed_legacy += shadowed
        row = {
            "button_character_id": key[0],
            "action_offset_uncompressed": key[1],
            "legacy_partition_verified": _flag(
                old["top_level_partition_verified"], "legacy partition"),
            "legacy_function_body_shadowed_record_count": shadowed,
            "partitioned_status": new["status"],
            "comparison_status": None,
        }
        if _flag(new["graph_verified"], "partitioned verified"):
            if new["status"] != "verified_graph":
                raise ValueError("Verified graph has inconsistent status")
            old_visits = _count(old["visited_top_level_record_count"], "old visits")
            new_visits = _count(new["visited_record_count"], "new visits")
            old_tail = _count(old["visited_post_end_candidate_record_count"],
                              "old post-End candidates")
            new_tail = _count(new["visited_post_end_record_count"],
                              "new post-End candidates")
            old_path = _flag(old["syntactic_entry_path_to_post_end_candidate"],
                             "old syntactic path")
            new_path = _flag(new["syntactic_entry_path_to_post_end_record"],
                             "new syntactic path")
            dv, dt = new_visits - old_visits, new_tail - old_tail
            visit_delta += dv
            post_end_delta += dt
            changed_visits += int(dv != 0)
            changed_post_end += int(dt != 0)
            changed_paths += int(old_path != new_path)
            compared += 1
            row.update({
                "comparison_status": "compared",
                "legacy_visited_records": old_visits,
                "partitioned_visited_records": new_visits,
                "visited_record_delta": dv,
                "legacy_post_end_candidates": old_tail,
                "partitioned_post_end_candidates": new_tail,
                "post_end_candidate_delta": dt,
                "legacy_syntactic_post_end_path": old_path,
                "partitioned_syntactic_post_end_path": new_path,
                "syntactic_path_changed": old_path != new_path,
            })
        else:
            if new["status"] == "verified_graph":
                raise ValueError("Unverified graph has verified status")
            skipped += 1
            row["comparison_status"] = "new_graph_unverified"
        status_counts[row["comparison_status"]] += 1
        rows.append(row)

    if compared + skipped != len(old_rows) or sum(status_counts.values()) != len(rows):
        raise ValueError("Entry graph comparison accounting mismatch")
    return {
        "source_sha256": source,
        "legacy_tail_graph_count": len(old_rows),
        "partitioned_source_graph_count": len(new_rows),
        "compared_count": compared,
        "new_graph_unverified_count": skipped,
        "legacy_shadowed_function_body_record_total": shadowed_legacy,
        "changed_visited_record_count": changed_visits,
        "changed_post_end_candidate_count": changed_post_end,
        "changed_syntactic_path_count": changed_paths,
        "visited_record_delta_total": visit_delta,
        "post_end_candidate_delta_total": post_end_delta,
        "comparison_status_counts": dict(status_counts),
        "runtime_reachability_verified": False,
        "legacy_graph_replaced": False,
        "records": rows,
        "limitations": [
            "Only legacy tail-subset rows with verified partitioned graphs are comparable.",
            "Differences reflect syntactic parser boundaries, not Flash runtime behavior.",
            "Unverified partitioned graphs are excluded from numerical comparisons.",
            "Original SWF, ActionScript, operands, images and audio are not emitted.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    for arg in ("legacy", "partitioned", "output"):
        parser.add_argument("--" + arg, required=True, type=Path)
    args = parser.parse_args()
    report = compare_entry_graphs(
        json.loads(args.legacy.read_text(encoding="utf-8")),
        json.loads(args.partitioned.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
