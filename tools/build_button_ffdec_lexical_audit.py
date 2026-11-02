#!/usr/bin/env python3
"""Read restricted FFDec button scripts; emit lexical metadata only.

Counts are not ActionScript/bytecode equivalence or Flash runtime evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from as2_reference_scopes import lexical_function_scopes
from build_as2_semantic_index import FUNCTION, ASSIGNED_FUNCTION, mask_comments_strings
from build_button_ffdec_export_crosswalk import BUTTON_EXPORT, SHA256, OBSERVED_EVENT_LABELS

PRIORITY_BUTTON_IDS = frozenset((693, 701, 715))
BRANCH_WORDS = ("if", "else", "switch", "case", "for", "while", "return")
BRANCH_RE = re.compile(r"\b(?:" + "|".join(BRANCH_WORDS) + r")\b")


def _count(value, name):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid " + name)
    return value


def audit_button_lexical_exports(scripts_root: Path, crosswalk: dict,
                                 export_index: dict) -> dict:
    source = crosswalk.get("source_sha256")
    if (type(source) is not str or not SHA256.fullmatch(source)
            or export_index.get("source_sha256") != source):
        raise ValueError("Source SHA-256 mismatch")
    rows, files = crosswalk.get("records"), export_index.get("files")
    if type(rows) is not list or type(files) is not list:
        raise ValueError("Invalid crosswalk or export rows")
    if (_count(crosswalk.get("matched_export_count"), "matched count") != len(rows)
            or _count(crosswalk.get("source_action_record_count"), "source action count") != len(rows)
            or _count(export_index.get("script_count"), "script count") != len(files)):
        raise ValueError("Source/export coverage mismatch")
    if (crosswalk.get("decompiled_semantics_verified") is not False
            or crosswalk.get("runtime_behavior_verified") is not False):
        raise ValueError("Unsupported semantics or runtime verification claim")
    index = {}
    for item in files:
        path = item.get("path")
        if type(path) is not str or path in index:
            raise ValueError("Invalid or duplicate export path")
        index[path] = item
    if _count(export_index.get("total_bytes"), "export byte total") != sum(
            _count(item.get("size_bytes"), "export size") for item in files):
        raise ValueError("Export byte total mismatch")
    root = scripts_root.resolve(strict=True)
    seen = set()
    result_rows = []
    scopes_total = unmatched_total = 0
    branch_totals = Counter({word: 0 for word in BRANCH_WORDS})
    for record in rows:
        path = record.get("ffdec_export_path")
        cid = _count(record.get("button_character_id"), "button ID")
        match = BUTTON_EXPORT.fullmatch(path) if type(path) is str else None
        if (not match or int(match.group(1)) != cid or path in seen or path not in index
                or record.get("ffdec_event_label") != match.group(2)
                or OBSERVED_EVENT_LABELS.get(record.get("condition_flags")) != match.group(2)):
            raise ValueError("Invalid, duplicate or missing button export mapping")
        seen.add(path)
        if (record.get("decompiled_semantics_verified") is not False
                or record.get("runtime_behavior_verified") is not False):
            raise ValueError("Unsupported row verification claim")
        meta = index[path]
        size = _count(meta.get("size_bytes"), "indexed file size")
        digest = meta.get("sha256")
        if (type(digest) is not str or not SHA256.fullmatch(digest)
                or size != record.get("ffdec_export_size_bytes")
                or digest != record.get("ffdec_export_sha256")):
            raise ValueError("Crosswalk/export hash or size mismatch")
        local = (root / path).resolve(strict=True)
        if not local.is_relative_to(root) or not local.is_file():
            raise ValueError("Unsafe script path")
        raw = local.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("FFDec source file hash or size mismatch")
        masked = mask_comments_strings(raw.decode("utf-8", errors="replace"))
        scopes = lexical_function_scopes(masked)
        assigned = list(ASSIGNED_FUNCTION.finditer(masked))
        candidates = len(assigned) + sum(
            not any(a.start() <= m.start() < a.end() for a in assigned)
            for m in FUNCTION.finditer(masked)
        )
        unmatched = candidates - len(scopes)
        if unmatched < 0:
            raise ValueError("Function candidate accounting mismatch")
        words = Counter(m.group() for m in BRANCH_RE.finditer(masked))
        branch_totals.update(words)
        scopes_total += len(scopes)
        unmatched_total += unmatched
        result_rows.append({
            "button_character_id": cid,
            "action_offset_uncompressed": _count(record.get("action_offset_uncompressed"), "action offset"),
            "ffdec_export_path": path,
            "ffdec_export_sha256": digest,
            "priority_graph_difference_review": cid in PRIORITY_BUTTON_IDS,
            "lexical_function_candidate_count": candidates,
            "lexical_matched_function_scope_count": len(scopes),
            "lexical_unmatched_function_candidate_count": unmatched,
            "lexical_scope_kind_counts": dict(sorted(Counter(s["kind"] for s in scopes).items())),
            "lexical_scope_line_ranges": sorted([[s["start_line"], s["end_line"]] for s in scopes]),
            "lexical_branch_keyword_counts": {w: words[w] for w in BRANCH_WORDS},
            "decompiled_semantics_verified": False,
            "runtime_behavior_verified": False,
        })
    indexed_button_paths = {p for p in index if p.startswith("scripts/DefineButton2_")}
    if len(seen) != len(rows) or indexed_button_paths != seen:
        raise ValueError("Incomplete or extra button export coverage")
    return {
        "source_sha256": source,
        "audited_button_action_count": len(result_rows),
        "priority_review_count": sum(r["priority_graph_difference_review"] for r in result_rows),
        "lexical_function_candidate_total": scopes_total + unmatched_total,
        "lexical_matched_function_scope_total": scopes_total,
        "lexical_unmatched_function_candidate_total": unmatched_total,
        "lexical_branch_keyword_totals": {w: branch_totals[w] for w in BRANCH_WORDS},
        "decompiled_semantics_verified": False,
        "runtime_behavior_verified": False,
        "records": sorted(result_rows, key=lambda r: (r["button_character_id"], r["action_offset_uncompressed"])),
        "limitations": [
            "Lexical AS2 tokens and brace scopes are heuristic; no bytecode equivalence or VM execution is established.",
            "Comments and quoted strings are masked; regex literals and malformed FFDec output can mislead scanning.",
            "Priority IDs come from prior graph-count differences, not proven game behavior.",
            "Only hashes, paths, line ranges and counts are emitted; original scripts stay on the runner.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripts", required=True, type=Path)
    parser.add_argument("--crosswalk", required=True, type=Path)
    parser.add_argument("--export-index", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit_button_lexical_exports(
        args.scripts,
        json.loads(args.crosswalk.read_text(encoding="utf-8")),
        json.loads(args.export_index.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("records", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
