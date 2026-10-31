#!/usr/bin/env python3
"""Metadata-only lexical proximity of unresolved attachMovie identifier pairs."""
import argparse
from collections import defaultdict
from itertools import combinations
import hashlib
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
CONTEXTS = {"outside_recognized_function", "parameter_declaration_candidate",
            "signature_reference", "function_body_reference"}


def digest(value, label):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def number(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid " + label)
    return value


def scope_relation(a, b):
    x, y = a["scope_candidate"], b["scope_candidate"]
    if x and y and all(x[k] == y[k] for k in
                       ("name_sha256", "start_line", "end_line", "kind")):
        return "same_lexical_function_candidate"
    if x is None and y is None:
        return "both_outside_recognized_function"
    return "different_or_unrecognized_scope"


def build_scope_pairs(references, joined):
    source = digest(references.get("source_sha256"), "source SHA-256")
    if joined.get("source_sha256") != source:
        raise ValueError("SWF source SHA-256 mismatch")
    targets, events = references.get("targets"), joined.get("events")
    if not isinstance(targets, list) or not isinstance(events, list):
        raise ValueError("Invalid evidence rows")
    if len(targets) != number(references.get("identifier_target_count"), "target count"):
        raise ValueError("Identifier target count mismatch")
    if len(targets) != number(joined.get("identifier_target_count"), "joined target count"):
        raise ValueError("Joined target count mismatch")
    if len(events) != number(joined.get("dynamic_attach_count"), "dynamic count"):
        raise ValueError("Dynamic count mismatch")
    number(references.get("verified_script_count"), "script count", 1)
    number(references.get("verified_script_bytes"), "script bytes", 1)
    used = set()
    for event in events:
        if event.get("runtime_binding_verified") is not False:
            raise ValueError("Unverified runtime binding claim")
        refs = event.get("identifier_references")
        if not isinstance(refs, list):
            raise ValueError("Invalid joined identifier references")
        for ref in refs:
            if ref.get("runtime_binding_verified") is not False:
                raise ValueError("Unverified runtime identifier claim")
            used.add(digest(ref.get("identifier_sha256"), "joined identifier hash"))
    groups = {}
    total = 0
    for target in targets:
        key = digest(target.get("identifier_sha256"), "identifier hash")
        if key in groups or target.get("runtime_binding_verified") is not False:
            raise ValueError("Duplicate or verified identifier target")
        count = number(target.get("occurrence_count"), "occurrence count", 1)
        examples = target.get("examples")
        if (target.get("examples_truncated") is not False
                or not isinstance(examples, list) or len(examples) != count):
            raise ValueError("Incomplete bounded lexical examples")
        paths = defaultdict(list)
        for ex in examples:
            path = ex.get("script_path")
            line = number(ex.get("line"), "reference line", 1)
            if (not isinstance(path, str) or not path.startswith("scripts/")
                    or not path.endswith(".as") or ".." in Path(path).parts):
                raise ValueError("Invalid private script path")
            context, scope = ex.get("context"), ex.get("scope_candidate")
            if context not in CONTEXTS:
                raise ValueError("Invalid lexical context")
            if context == "outside_recognized_function":
                if scope is not None:
                    raise ValueError("Unexpected function scope")
            else:
                if not isinstance(scope, dict):
                    raise ValueError("Missing lexical scope candidate")
                digest(scope.get("name_sha256"), "scope hash")
                start = number(scope.get("start_line"), "scope start", 1)
                end = number(scope.get("end_line"), "scope end", start)
                if not start <= line <= end or scope.get("runtime_binding_verified") is not False:
                    raise ValueError("Invalid lexical scope bounds or claim")
                if scope.get("kind") not in ("named_function", "function_assignment"):
                    raise ValueError("Invalid function kind")
            paths[path].append(ex)
        groups[key] = paths
        total += count
    if set(groups) != used:
        raise ValueError("Joined target coverage mismatch")
    if (total != number(references.get("identifier_occurrence_count"), "reference total")
            or total != number(joined.get("identifier_occurrence_count"), "joined total")):
        raise ValueError("Identifier occurrence total mismatch")
    rows = []
    for a, b in combinations(sorted(groups), 2):
        for path in sorted(set(groups[a]) & set(groups[b])):
            left, right = groups[a][path], groups[b][path]
            distance, la, lb, ea, eb = min(
                ((abs(x["line"] - y["line"]), x["line"], y["line"], x, y)
                 for x in left for y in right),
                key=lambda v: (v[0], v[1], v[2]))
            rows.append({
                "identifier_a_sha256": a, "identifier_b_sha256": b,
                "script_path_sha256": hashlib.sha256(path.encode()).hexdigest(),
                "occurrences_a": len(left), "occurrences_b": len(right),
                "closest_line_a": la, "closest_line_b": lb,
                "minimum_line_gap": distance,
                "closest_scope_relation": scope_relation(ea, eb),
                "runtime_binding_verified": False,
            })
    return {
        "source_sha256": source,
        "verified_script_count": references["verified_script_count"],
        "identifier_target_count": len(groups),
        "identifier_occurrence_count": total,
        "shared_script_count": len(rows),
        "shared_scripts_with_gap_at_most_2": sum(x["minimum_line_gap"] <= 2 for x in rows),
        "shared_scripts_with_gap_at_most_5": sum(x["minimum_line_gap"] <= 5 for x in rows),
        "shared_scripts_with_same_function_candidate": sum(
            x["closest_scope_relation"] == "same_lexical_function_candidate" for x in rows),
        "pairs": rows,
        "limitations": [
            "Complete bounded lexical examples only; no ActionScript execution is checked.",
            "Proximity and matching lexical function do not prove binding or data flow.",
            "No plaintext script paths, original source, unknown literals, images or audio are emitted.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    for name in ("references", "joined", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    args = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_scope_pairs(read(args.references), read(args.joined))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("pairs", "limitations")}))


if __name__ == "__main__":
    main()
