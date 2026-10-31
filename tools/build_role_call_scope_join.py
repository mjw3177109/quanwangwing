#!/usr/bin/env python3
"""Join hash-verified role goto callsites to existing lexical function scopes.

Metadata only. Line containment is not a verified call graph or MovieClip binding.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

RELATIONS = ("unique", "overlapping", "outside")


def _key(role: dict) -> tuple[str, str]:
    key = (role.get("character_candidate"), role.get("variant"))
    if not all(isinstance(value, str) and value for value in key):
        raise ValueError("Invalid role identity")
    return key


def build_join(crosswalk: dict, evidence: dict) -> dict:
    sha = crosswalk.get("source_sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha) or sha != evidence.get("source_sha256"):
        raise ValueError("SWF source SHA-256 mismatch")
    source_roles = crosswalk.get("roles")
    call_roles = evidence.get("roles")
    if (not isinstance(source_roles, list) or not isinstance(call_roles, list)
            or len(source_roles) != crosswalk.get("role_variant_count")
            or len(call_roles) != evidence.get("role_variant_count")
            or len(source_roles) != len(call_roles)):
        raise ValueError("Role coverage mismatch")
    by_key = {}
    for role in source_roles:
        key = _key(role)
        if key in by_key:
            raise ValueError("Duplicate role in crosswalk")
        by_key[key] = role
    seen = set()
    result = []
    totals = Counter({name: 0 for name in RELATIONS})
    scope_kinds = Counter({"unresolved": 0})
    for role in call_roles:
        key = _key(role)
        if key in seen or key not in by_key:
            raise ValueError("Duplicate or unknown role in call evidence")
        seen.add(key)
        original = by_key[key]
        if (role.get("verified_as2_script_path") != original.get("verified_as2_script_path")
                or role.get("verified_as2_script_sha256") != original.get("verified_as2_script_sha256")):
            raise ValueError("Role script provenance mismatch")
        scopes = original.get("function_scope_candidates")
        if (not isinstance(scopes, list)
                or original.get("function_scope_candidate_count") != len(scopes)):
            raise ValueError("Function scope coverage mismatch")
        for scope in scopes:
            start, end = scope.get("start_line"), scope.get("end_line")
            if (type(start) is not int or type(end) is not int or start < 1 or end < start
                    or not isinstance(scope.get("kind"), str) or not scope["kind"]):
                raise ValueError("Invalid lexical function scope")
        calls = role.get("calls")
        if not isinstance(calls, list) or role.get("call_candidate_count") != len(calls):
            raise ValueError("Callsite count mismatch")
        joined = []
        for call in calls:
            line = call.get("line")
            if type(line) is not int or line < 1:
                raise ValueError("Invalid callsite line")
            matching = [s for s in scopes if s["start_line"] <= line <= s["end_line"]]
            relation = "outside" if not matching else "unique" if len(matching) == 1 else "overlapping"
            kind = matching[0]["kind"] if len(matching) == 1 else "unresolved"
            totals[relation] += 1
            scope_kinds[kind] += 1
            joined.append({
                "line": line,
                "method": call.get("method"),
                "receiver_kind": call.get("receiver_kind"),
                "argument_kind": call.get("argument_kind"),
                "scope_relation": relation,
                "scope_candidate_count": len(matching),
                "scope_kind": kind,
            })
        result.append({
            "character_candidate": key[0],
            "variant": key[1],
            "verified_as2_script_sha256": original["verified_as2_script_sha256"],
            "call_candidate_count": len(joined),
            "calls": joined,
        })
    if seen != set(by_key) or sum(totals.values()) != evidence.get("call_candidate_count"):
        raise ValueError("Callsite accounting mismatch")
    return {
        "source_sha256": sha,
        "role_variant_count": len(result),
        "call_candidate_count": sum(totals.values()),
        "scope_relation_counts": dict(totals),
        "scope_kind_counts": dict(sorted(scope_kinds.items())),
        "roles": sorted(result, key=lambda r: (r["character_candidate"], r["variant"])),
        "limitations": [
            "Scope containment is lexical line-interval evidence, not verified execution or call graph.",
            "Function assignment scope does not establish this-binding or target MovieClip identity.",
            "Overlapping or missing scopes are explicitly unresolved; no move/frame data is inferred.",
            "No original ActionScript bodies, function names, string arguments or media are emitted.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--role-crosswalk", type=Path, required=True)
    p.add_argument("--call-evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = build_join(
        json.loads(args.role_crosswalk.read_text(encoding="utf-8")),
        json.loads(args.call_evidence.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("role_variant_count", "call_candidate_count", "scope_relation_counts", "scope_kind_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
