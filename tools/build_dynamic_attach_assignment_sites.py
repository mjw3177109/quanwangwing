#!/usr/bin/env python3
"""Audit lexical assignment syntax for unresolved AS2 attachMovie identifiers.

Read verified FFDec exports only on the runner; publish hashes and syntax metadata,
never the original source or identifier spelling. This is not a data-flow engine.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from bisect import bisect_right

from build_as2_semantic_index import mask_comments_strings
from build_attach_identifier_references import TOKEN, _kind

SHA = re.compile(r"[0-9a-f]{64}\Z")
ASSIGN = re.compile(r"\s*(>>>=|>>=|<<=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|=(?!=|>))")


def check_sha(value, label):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def count(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid " + label)
    return value


def valid_path(path):
    return (isinstance(path, str) and path.startswith("scripts/")
            and path.endswith(".as") and ".." not in Path(path).parts
            and not Path(path).is_absolute() and "\\" not in path)


def rhs_class(masked, offset):
    tail = masked[offset:].lstrip()
    if re.match(r"function\b", tail):
        return "function_expression_candidate"
    if re.match(r"new\b", tail):
        return "constructor_candidate"
    if re.match(r"[A-Za-z_$][\w$]*", tail):
        return "identifier_candidate"
    if re.match(r"\d", tail):
        return "numeric_candidate"
    if tail.startswith("("):
        return "parenthesized_candidate"
    if tail.startswith("["):
        return "array_candidate"
    if tail.startswith("{"):
        return "object_candidate"
    return "masked_or_unclassified"


def build_assignment_sites(scripts_root, export_index, references):
    source = check_sha(references.get("source_sha256"), "source SHA-256")
    if export_index.get("source_sha256") != source:
        raise ValueError("SWF source SHA-256 mismatch")
    records = export_index.get("files")
    if not isinstance(records, list) or len(records) != count(export_index.get("script_count"), "script count", 1):
        raise ValueError("Invalid script export index")
    if (count(export_index.get("total_bytes"), "export bytes", 1)
            != count(references.get("verified_script_bytes"), "reference bytes", 1)
            or len(records) != count(references.get("verified_script_count"), "reference script count", 1)
            or count(export_index.get("unexpected_empty_count", 0), "unexpected empty count") != 0):
        raise ValueError("Verified script coverage mismatch")
    indexed = {}
    for record in records:
        path = record.get("path")
        if not valid_path(path) or path in indexed:
            raise ValueError("Duplicate or invalid script path")
        check_sha(record.get("sha256"), "script SHA-256")
        count(record.get("size_bytes"), "script size")
        indexed[path] = record
    if sum(r["size_bytes"] for r in records) != export_index["total_bytes"]:
        raise ValueError("Script byte accounting mismatch")
    targets = references.get("targets")
    if not isinstance(targets, list) or len(targets) != count(references.get("identifier_target_count"), "target count", 1):
        raise ValueError("Identifier target coverage mismatch")
    expected = defaultdict(Counter)
    total = 0
    used = set()
    for target in targets:
        digest = check_sha(target.get("identifier_sha256"), "identifier SHA-256")
        if digest in used or target.get("runtime_binding_verified") is not False:
            raise ValueError("Duplicate identifier or unverified binding claim")
        used.add(digest)
        n = count(target.get("occurrence_count"), "occurrence count", 1)
        examples = target.get("examples")
        if target.get("examples_truncated") is not False or not isinstance(examples, list) or len(examples) != n:
            raise ValueError("Incomplete lexical examples")
        total += n
        for ex in examples:
            path, line, kind = ex.get("script_path"), ex.get("line"), ex.get("kind")
            if not valid_path(path) or path not in indexed:
                raise ValueError("Invalid or missing private script path")
            count(line, "reference line", 1)
            if not isinstance(kind, str) or not kind:
                raise ValueError("Invalid reference syntax class")
            if ex.get("runtime_binding_verified") is True:
                raise ValueError("Unverified lexical reference claim")
            expected[path][(digest, line, kind)] += 1
    if total != count(references.get("identifier_occurrence_count"), "occurrence total"):
        raise ValueError("Identifier occurrence accounting mismatch")
    output = []
    observed_total = 0
    for path, expected_refs in sorted(expected.items()):
        record = indexed[path]
        file = scripts_root / path
        if not file.is_file():
            raise ValueError("Missing verified script file")
        raw = file.read_bytes()
        if len(raw) != record["size_bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("AS2 script hash/size mismatch")
        masked = mask_comments_strings(raw.decode("utf-8", errors="replace"))
        newlines = [i for i, c in enumerate(masked) if c == "\n"]
        found = Counter()
        for match in TOKEN.finditer(masked):
            digest = hashlib.sha256(match.group(1).encode("utf-8")).hexdigest()
            if digest not in used:
                continue
            line = bisect_right(newlines, match.start() - 1) + 1
            kind = _kind(masked, match.start(), match.end())
            key = (digest, line, kind)
            found[key] += 1
            op = ASSIGN.match(masked, match.end())
            if op:
                lhs = ("member_property_candidate" if kind == "member_property" else
                       "variable_initializer_candidate" if kind == "variable_declaration" else
                       "direct_assignment_candidate")
                output.append({
                    "identifier_sha256": digest,
                    "script_path_sha256": hashlib.sha256(path.encode("utf-8")).hexdigest(),
                    "line": line,
                    "lhs_class": lhs,
                    "operator": op.group(1),
                    "rhs_class": rhs_class(masked, op.end()),
                    "runtime_binding_verified": False,
                })
        if found != expected_refs:
            raise ValueError("Lexical reference position/kind mismatch")
        observed_total += sum(found.values())
    if observed_total != total:
        raise ValueError("Lexical occurrence total mismatch")
    output.sort(key=lambda x: (x["script_path_sha256"], x["line"], x["identifier_sha256"], x["operator"]))
    return {
        "source_sha256": source,
        "verified_script_count": references["verified_script_count"],
        "identifier_target_count": len(used),
        "identifier_occurrence_count": observed_total,
        "assignment_candidate_count": len(output),
        "lhs_class_counts": dict(sorted(Counter(x["lhs_class"] for x in output).items())),
        "rhs_class_counts": dict(sorted(Counter(x["rhs_class"] for x in output).items())),
        "sites": output,
        "limitations": [
            "Lexical assignment syntax only; neither runtime binding nor data flow is verified.",
            "Member assignments, variable shadowing, masked literals and malformed decompilation can be ambiguous.",
            "Only SHA-256 identifiers and script paths, line numbers and coarse syntax categories are emitted.",
            "Original AS2 source, unmatched literals, original art and audio remain private.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scripts", type=Path, required=True)
    for key in ("export-index", "references", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_assignment_sites(a.scripts, read(a.export_index), read(a.references))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("sites", "limitations")}))


if __name__ == "__main__":
    main()
