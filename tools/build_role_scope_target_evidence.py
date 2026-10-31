#!/usr/bin/env python3
"""Cross-check lexical role goto scopes with assignment target shapes and symbol IDs.

Evidence only. Assignment targets, receiver names and original AS2 text are never
written to output; a lexical target is not a verified runtime MovieClip binding.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"
TARGET = re.compile(rf"{IDENT}(?:\.{IDENT})*\Z")
KINDS = ("this_member", "root_member", "parent_member", "prototype_member",
         "global_member", "ffdec_local_member", "other_member", "bare_identifier", "unresolved")


def classify_target(name: str, kind: str) -> tuple[str, int]:
    if not isinstance(name, str) or not TARGET.fullmatch(name):
        raise ValueError("Invalid lexical scope target")
    if kind not in ("function_assignment", "prototype_method", "event_callback", "named_function"):
        raise ValueError("Invalid lexical scope kind")
    parts = name.split(".")
    if kind == "named_function" or len(parts) == 1:
        return "bare_identifier", len(parts)
    if "prototype" in parts[:-1]:
        return "prototype_member", len(parts)
    if parts[0] == "_global":
        return "global_member", len(parts)
    if re.fullmatch(r"_loc[0-9]+_", parts[0]):
        return "ffdec_local_member", len(parts)
    return {
        "this": "this_member", "_root": "root_member", "_parent": "parent_member"
    }.get(parts[0], "other_member"), len(parts)


def _role_key(role: dict) -> tuple[str, str]:
    key = (role.get("character_candidate"), role.get("variant"))
    if not all(isinstance(x, str) and x for x in key):
        raise ValueError("Invalid role identity")
    return key


def build_evidence(crosswalk: dict, joined: dict) -> dict:
    sha = crosswalk.get("source_sha256")
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or sha != joined.get("source_sha256"):
        raise ValueError("SWF source SHA-256 mismatch")
    roles = crosswalk.get("roles")
    call_roles = joined.get("roles")
    if (not isinstance(roles, list) or not isinstance(call_roles, list) or not roles
            or len(roles) != crosswalk.get("role_variant_count")
            or len(call_roles) != joined.get("role_variant_count") or len(roles) != len(call_roles)):
        raise ValueError("Role coverage mismatch")
    by_key = {}
    for role in roles:
        key = _role_key(role)
        if key in by_key:
            raise ValueError("Duplicate crosswalk role")
        by_key[key] = role
    counts = Counter({kind: 0 for kind in KINDS})
    pair_counts = Counter()
    rows = []
    seen = set()
    for role in call_roles:
        key = _role_key(role)
        if key in seen or key not in by_key:
            raise ValueError("Duplicate or unknown joined role")
        seen.add(key)
        original = by_key[key]
        if (role.get("verified_as2_script_sha256") != original.get("verified_as2_script_sha256")
                or not isinstance(original.get("verified_as2_script_path"), str)
                or not SHA.fullmatch(str(original.get("verified_as2_script_sha256")))):
            raise ValueError("Role script provenance mismatch")
        symbol_id = original.get("export_assets_character_id")
        if type(symbol_id) is not int or symbol_id <= 0:
            raise ValueError("Invalid ExportAssets character ID")
        sprite = original.get("sprite_timeline")
        if sprite is not None and (not isinstance(sprite, dict) or sprite.get("sprite_character_id") != symbol_id):
            raise ValueError("Role Sprite ID mismatch")
        scopes = original.get("function_scope_candidates")
        if not isinstance(scopes, list) or len(scopes) != original.get("function_scope_candidate_count"):
            raise ValueError("Function scope count mismatch")
        for scope in scopes:
            a, b = scope.get("start_line"), scope.get("end_line")
            if type(a) is not int or type(b) is not int or a <= 0 or b < a:
                raise ValueError("Invalid lexical scope interval")
        calls = role.get("calls")
        if not isinstance(calls, list) or len(calls) != role.get("call_candidate_count"):
            raise ValueError("Callsite coverage mismatch")
        out_calls = []
        for call in calls:
            line = call.get("line")
            if type(line) is not int or line < 1:
                raise ValueError("Invalid callsite line")
            matching = [s for s in scopes if s["start_line"] <= line <= s["end_line"]]
            relation = "outside" if not matching else "unique" if len(matching) == 1 else "overlapping"
            if call.get("scope_relation") != relation or call.get("scope_candidate_count") != len(matching):
                raise ValueError("Lexical scope relation mismatch")
            expected_kind = matching[0]["kind"] if len(matching) == 1 else "unresolved"
            if call.get("scope_kind") != expected_kind:
                raise ValueError("Lexical scope kind mismatch")
            target_kind, depth = (classify_target(matching[0]["name"], expected_kind)
                                  if relation == "unique" else ("unresolved", 0))
            receiver = call.get("receiver_kind")
            if not isinstance(receiver, str) or not receiver:
                raise ValueError("Invalid call receiver category")
            counts[target_kind] += 1
            pair_counts[(receiver, target_kind)] += 1
            out_calls.append({
                "line": line, "method": call.get("method"),
                "receiver_kind": receiver, "scope_relation": relation,
                "scope_target_kind": target_kind, "scope_target_depth": depth,
                "scope_start_line": matching[0]["start_line"] if relation == "unique" else None,
                "scope_end_line": matching[0]["end_line"] if relation == "unique" else None,
                "runtime_binding_verified": False,
            })
        rows.append({
            "character_candidate": key[0], "variant": key[1],
            "export_assets_character_id": symbol_id,
            "verified_as2_script_sha256": original["verified_as2_script_sha256"],
            "sprite_timeline_present": sprite is not None,
            "call_candidate_count": len(out_calls), "calls": out_calls,
        })
    total = sum(counts.values())
    if seen != set(by_key) or total != joined.get("call_candidate_count"):
        raise ValueError("Callsite accounting mismatch")
    return {
        "source_sha256": sha, "role_variant_count": len(rows),
        "call_candidate_count": total,
        "scope_target_kind_counts": dict(counts),
        "receiver_target_pair_counts": [
            {"receiver_kind": a, "target_kind": b, "count": n}
            for (a, b), n in sorted(pair_counts.items())
        ],
        "roles": sorted(rows, key=lambda r: (r["character_candidate"], r["variant"])),
        "limitations": [
            "Function assignment target shapes and goto receivers are lexical candidates only.",
            "ExportAssets symbol ID does not establish a runtime this-binding or animation target.",
            "No original function target names, source bodies, frame labels or media are emitted.",
            "No action frames, hitboxes, damage or verified runtime transitions are inferred.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role-crosswalk", type=Path, required=True)
    parser.add_argument("--call-scope-join", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = build_evidence(
        json.loads(args.role_crosswalk.read_text(encoding="utf-8")),
        json.loads(args.call_scope_join.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: data[k] for k in (
        "role_variant_count", "call_candidate_count", "scope_target_kind_counts",
        "receiver_target_pair_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
