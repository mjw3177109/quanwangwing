#!/usr/bin/env python3
"""Fail-closed, metadata-only join of unresolved attachMovie sites and hashed references.

A lexical reference is not a runtime binding or evidence of a playable character.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")


def _sha(value, label):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid " + label)
    return value


def build_dynamic_attach_reference_join(provenance, references, roles):
    source = _sha(provenance.get("source_sha256"), "source SHA-256")
    if any(x.get("source_sha256") != source for x in (references, roles)):
        raise ValueError("SWF source SHA-256 mismatch")
    if (_count(provenance.get("verified_script_count"), "script count") !=
            _count(references.get("verified_script_count"), "reference script count") or
            _count(provenance.get("verified_script_bytes"), "script bytes") !=
            _count(references.get("verified_script_bytes"), "reference script bytes")):
        raise ValueError("Verified AS2 script coverage mismatch")
    events, targets, role_entries = (provenance.get("events"), references.get("targets"), roles.get("entries"))
    if not all(isinstance(x, list) for x in (events, targets, role_entries)):
        raise ValueError("Invalid evidence rows")
    if (len(events) != _count(provenance.get("dynamic_argument_count"), "dynamic count") or
            len(targets) != _count(references.get("identifier_target_count"), "target count") or
            len(role_entries) != _count(roles.get("role_variant_count"), "role count")):
        raise ValueError("Evidence row accounting mismatch")
    if sum(_count(v, "shape count") for v in provenance.get("argument_shape_counts", {}).values()) != len(events):
        raise ValueError("Argument shape accounting mismatch")
    role_hashes = {_sha(r.get("verified_role_script_sha256"), "role script hash") for r in role_entries}
    if len(role_hashes) != len(role_entries):
        raise ValueError("Duplicate verified role script hash")
    target_map = {}
    for target in targets:
        digest = _sha(target.get("identifier_sha256"), "identifier hash")
        if digest in target_map or target.get("runtime_binding_verified") is not False:
            raise ValueError("Duplicate or unverified identifier target")
        total = _count(target.get("occurrence_count"), "occurrence count")
        counts = [_count(target.get(k), k) for k in
                  ("same_script_before_count", "same_script_at_or_after_count", "other_script_count")]
        contexts = target.get("scope_context_counts")
        if sum(counts) != total or not isinstance(contexts, dict) or sum(
                _count(v, "scope count") for v in contexts.values()) != total:
            raise ValueError("Identifier occurrence accounting mismatch")
        target_map[digest] = target
    expected_sites = Counter()
    output = []
    seen_events = set()
    for event in events:
        path, line = event.get("script_path"), _count(event.get("line"), "attach line")
        if not isinstance(path, str) or not path.startswith("scripts/") or ".." in Path(path).parts or line < 1:
            raise ValueError("Invalid attach site")
        script_hash = _sha(event.get("script_sha256"), "attach script hash")
        arg_hash = _sha(event.get("argument_sha256"), "argument hash")
        key = (path, line, arg_hash)
        if key in seen_events or event.get("runtime_binding_verified") is not False:
            raise ValueError("Duplicate or verified dynamic attach site")
        seen_events.add(key)
        parts = event.get("concatenation_components")
        if not isinstance(parts, list):
            raise ValueError("Invalid concatenation components")
        if event.get("argument_shape") == "identifier":
            identifiers = [(None, _sha(event.get("identifier_sha256"), "argument identifier"))]
        else:
            identifiers = [(_count(p.get("position"), "component position"),
                            _sha(p.get("identifier_sha256"), "component identifier"))
                           for p in parts if p.get("kind") == "identifier"]
        if event.get("argument_shape") == "concatenation" and len(parts) < 2:
            raise ValueError("Truncated concatenation")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Duplicate component identifier")
        enriched = []
        for position, digest in identifiers:
            target = target_map.get(digest)
            if target is None:
                raise ValueError("Missing hashed identifier reference")
            expected_sites[(digest, path, line, position)] += 1
            enriched.append({
                "position": position, "identifier_sha256": digest,
                "occurrence_count": target["occurrence_count"],
                "same_script_before_count": target["same_script_before_count"],
                "same_script_at_or_after_count": target["same_script_at_or_after_count"],
                "other_script_count": target["other_script_count"],
                "scope_context_counts": target["scope_context_counts"],
                "runtime_binding_verified": False,
            })
        output.append({
            "script_path_sha256": hashlib.sha256(path.encode("utf-8")).hexdigest(),
            "script_sha256": script_hash, "line": line,
            "argument_sha256": arg_hash, "argument_shape": event.get("argument_shape"),
            "source_is_verified_role_script": script_hash in role_hashes,
            "identifier_references": enriched,
            "runtime_binding_verified": False,
        })
    actual_sites = Counter()
    for digest, target in target_map.items():
        sites = target.get("attach_sites")
        if not isinstance(sites, list):
            raise ValueError("Invalid identifier attach sites")
        for site in sites:
            position = site.get("component_position")
            if position is not None:
                position = _count(position, "attach component position")
            actual_sites[(digest, site.get("script_path"), _count(site.get("line"), "site line"), position)] += 1
    if actual_sites != expected_sites:
        raise ValueError("Hashed identifier attach-site mismatch")
    if sum(t["occurrence_count"] for t in targets) != _count(
            references.get("identifier_occurrence_count"), "identifier occurrence total"):
        raise ValueError("Identifier occurrence total mismatch")
    return {
        "source_sha256": source,
        "dynamic_attach_count": len(output),
        "identifier_target_count": len(target_map),
        "identifier_occurrence_count": references["identifier_occurrence_count"],
        "calls_in_verified_role_scripts": sum(x["source_is_verified_role_script"] for x in output),
        "events": sorted(output, key=lambda e: (e["script_path_sha256"], e["line"], e["argument_sha256"])),
        "limitations": [
            "Only hashed lexical identifiers and original FFDec metadata are joined.",
            "No variable binding, runtime call path, character selection, move or hitbox is proven.",
            "No plaintext script paths, original source bodies, unmatched literals, images or audio are emitted.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    for name in ("provenance", "references", "roles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build_dynamic_attach_reference_join(load(args.provenance), load(args.references), load(args.roles))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("events", "limitations")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
