#!/usr/bin/env python3
"""Join verified AS2 lexical assignment sites with hashed function-body references.

Consumes metadata only; it does not read or publish original ActionScript.
A lexical function-body match is not a runtime binding or call graph edge.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")


def digest(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Invalid SHA-256")
    return value


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid count or line")
    return value


def build_function_body_join(assignments, references, joined):
    source = digest(assignments.get("source_sha256"))
    if any(report.get("source_sha256") != source for report in (references, joined)):
        raise ValueError("SWF source mismatch")
    targets = references.get("targets")
    sites = assignments.get("sites")
    events = joined.get("events")
    if not all(isinstance(rows, list) for rows in (targets, sites, events)):
        raise ValueError("Missing evidence rows")
    if (len(targets) != integer(references.get("identifier_target_count"), 1)
            or len(sites) != integer(assignments.get("assignment_candidate_count"))
            or len(events) != integer(joined.get("dynamic_attach_count"))):
        raise ValueError("Evidence row accounting mismatch")
    for report in (assignments, joined):
        if (integer(report.get("identifier_target_count")) != len(targets)
                or integer(report.get("identifier_occurrence_count")) !=
                integer(references.get("identifier_occurrence_count"))):
            raise ValueError("Identifier coverage mismatch")
    target_map = {}
    count = 0
    for target in targets:
        key = digest(target.get("identifier_sha256"))
        examples = target.get("examples")
        n = integer(target.get("occurrence_count"), 1)
        if (key in target_map or target.get("runtime_binding_verified") is not False
                or target.get("examples_truncated") is not False
                or not isinstance(examples, list) or len(examples) != n):
            raise ValueError("Incomplete or duplicate lexical references")
        for ex in examples:
            path = ex.get("script_path")
            if (not isinstance(path, str) or not path.startswith("scripts/")
                    or not path.endswith(".as") or ".." in Path(path).parts
                    or "\\" in path):
                raise ValueError("Invalid private script path")
            integer(ex.get("line"), 1)
            if ex.get("context") not in ("outside_recognized_function",
                    "function_body_reference", "parameter_declaration_candidate",
                    "signature_reference"):
                raise ValueError("Invalid lexical context")
        target_map[key] = examples
        count += n
    if count != references["identifier_occurrence_count"]:
        raise ValueError("Reference occurrence mismatch")
    used = set()
    for event in events:
        if event.get("runtime_binding_verified") is not False:
            raise ValueError("Unverified call reported as verified")
        for ref in event.get("identifier_references", []):
            if ref.get("runtime_binding_verified") is not False:
                raise ValueError("Unverified call identifier reported as verified")
            used.add(digest(ref.get("identifier_sha256")))
    if used != set(target_map):
        raise ValueError("Attach identifier target coverage mismatch")
    output = []
    seen = set()
    for site in sites:
        owner = digest(site.get("identifier_sha256"))
        path_hash = digest(site.get("script_path_sha256"))
        line = integer(site.get("line"), 1)
        key = (owner, path_hash, line)
        if key in seen or owner not in target_map or site.get("runtime_binding_verified") is not False:
            raise ValueError("Duplicate or unverified assignment site")
        seen.add(key)
        if site.get("rhs_class") != "function_expression_candidate":
            continue
        if site.get("operator") != "=" or site.get("lhs_class") != "direct_assignment_candidate":
            raise ValueError("Inconsistent function assignment syntax")
        origin = [e for e in target_map[owner]
                  if hashlib.sha256(e["script_path"].encode()).hexdigest() == path_hash
                  and e["line"] == line and e.get("kind") == "assignment_target_candidate"]
        if len(origin) != 1:
            raise ValueError("Function assignment lacks exact source reference")
        matches = []
        for other, examples in target_map.items():
            if other == owner:
                continue
            for ex in examples:
                if hashlib.sha256(ex["script_path"].encode()).hexdigest() != path_hash:
                    continue
                scope = ex.get("scope_candidate")
                if ex.get("context") != "function_body_reference" or not isinstance(scope, dict):
                    continue
                if (scope.get("kind") != "function_assignment"
                        or scope.get("name_sha256") != owner
                        or integer(scope.get("start_line"), 1) != line
                        or integer(scope.get("end_line"), line) < ex["line"]
                        or scope.get("runtime_binding_verified") is not False):
                    continue
                matches.append({"other_identifier_sha256": other,
                                "reference_line": ex["line"],
                                "reference_kind": ex.get("kind"),
                                "function_end_line": scope["end_line"]})
        matches.sort(key=lambda x: (x["other_identifier_sha256"], x["reference_line"], str(x["reference_kind"])))
        output.append({"identifier_sha256": owner, "script_path_sha256": path_hash,
                       "assignment_line": line, "function_body_cross_target_references": matches,
                       "runtime_binding_verified": False})
    output.sort(key=lambda x: (x["script_path_sha256"], x["assignment_line"], x["identifier_sha256"]))
    return {"source_sha256": source, "verified_script_count": references["verified_script_count"],
            "identifier_target_count": len(target_map), "identifier_occurrence_count": count,
            "function_assignment_candidate_count": len(output),
            "function_assignments_with_cross_target_body_references": sum(bool(x["function_body_cross_target_references"]) for x in output),
            "cross_target_body_reference_count": sum(len(x["function_body_cross_target_references"]) for x in output),
            "cross_target_member_property_count": sum(m["reference_kind"] == "member_property" for x in output for m in x["function_body_cross_target_references"]),
            "sites": output,
            "limitations": ["Lexical function scope candidates only; runtime call, variable binding and data flow are not established.",
                            "Hash-only script paths and identifiers; original ActionScript, art and audio remain private."]}


def main():
    parser = argparse.ArgumentParser()
    for name in ("assignments", "references", "joined", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_function_body_join(read(args.assignments), read(args.references), read(args.joined))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("sites", "limitations")}))


if __name__ == "__main__":
    main()
