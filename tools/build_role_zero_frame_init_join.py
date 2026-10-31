#!/usr/bin/env python3
"""Cross-check role candidates with zero-frame AS2/DoInitAction evidence, metadata only."""
import argparse
import hashlib
import json
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{64}\Z")

def uint(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid " + label)
    return value

def build_role_zero_frame_init_join(roles, zero):
    sha = roles.get("source_sha256")
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or zero.get("source_sha256") != sha:
        raise ValueError("SWF SHA-256 mismatch")
    rs, zs = roles.get("roles"), zero.get("entries")
    if (not isinstance(rs, list) or not isinstance(zs, list)
            or uint(roles.get("role_variant_count"), "role count") != len(rs)
            or uint(zero.get("zero_sprite_export_count"), "zero count") != len(zs)):
        raise ValueError("Evidence row accounting mismatch")
    zmap = {}
    for z in zs:
        cid = uint(z.get("sprite_character_id"), "zero-frame ID")
        if cid == 0 or cid in zmap:
            raise ValueError("Duplicate zero-frame ID")
        zmap[cid] = z
    seen, output = set(), []
    for r in rs:
        cid = uint(r.get("export_assets_character_id"), "role ID")
        if cid == 0 or cid in seen:
            raise ValueError("Duplicate role ID")
        seen.add(cid)
        path = r.get("verified_as2_script_path")
        if not isinstance(path, str) or not path.startswith("scripts/") or not path.endswith(".as"):
            raise ValueError("Invalid verified role path")
        path_sha = hashlib.sha256(path.encode("utf-8")).hexdigest()
        script_sha = r.get("verified_as2_script_sha256")
        if not isinstance(script_sha, str) or not SHA.fullmatch(script_sha):
            raise ValueError("Invalid role script SHA-256")
        refs = r.get("do_init_action_targets")
        if not isinstance(refs, list) or uint(r.get("do_init_action_target_count"), "role init count") != len(refs):
            raise ValueError("Role init count mismatch")
        ref_keys = [(x.get("parent_timeline"), uint(x.get("frame"), "role frame"),
                     uint(x.get("offset_uncompressed"), "role offset")) for x in refs]
        if len(set(ref_keys)) != len(ref_keys):
            raise ValueError("Duplicate role init reference")
        z = zmap.get(cid)
        matched = False
        if z is not None:
            tags = z.get("init_script_tags")
            if not isinstance(tags, list) or uint(z.get("do_init_action_target_count"), "zero init count") != len(tags):
                raise ValueError("Zero-frame init count mismatch")
            keys = [(t.get("timeline"), uint(t.get("frame_zero_based"), "zero frame"),
                     uint(t.get("offset_uncompressed"), "zero offset")) for t in tags]
            if len(set(keys)) != len(keys) or set(keys) != set(ref_keys):
                raise ValueError("DoInitAction evidence disagree")
            matched = (z.get("classification") == "verified_path_match"
                       and z.get("candidate_script_path_sha256") == path_sha
                       and z.get("verified_script_sha256") == script_sha)
        output.append({
            "role_character_id": cid,
            "role_variant": r.get("variant"),
            "role_name_sha256": hashlib.sha256(str(r.get("character_candidate")).encode("utf-8")).hexdigest(),
            "verified_role_script_sha256": script_sha,
            "zero_show_frame_sprite": z is not None,
            "same_verified_class_path": matched,
            "static_do_init_action_count": len(ref_keys),
            "direct_placement_count": uint(r.get("direct_placement_count"), "placement count"),
            "init_tag_positions": [{"timeline": t, "frame_zero_based": f, "offset_uncompressed": o}
                                   for t, f, o in sorted(ref_keys)],
        })
    return {
        "source_sha256": sha,
        "role_variant_count": len(output),
        "role_variants_with_zero_show_frame": sum(x["zero_show_frame_sprite"] for x in output),
        "role_variants_with_same_verified_class_path": sum(x["same_verified_class_path"] for x in output),
        "role_init_reference_count": sum(x["static_do_init_action_count"] for x in output),
        "entries": sorted(output, key=lambda x: x["role_character_id"]),
        "limitations": [
            "Only static SWF and FFDec metadata is joined; no runtime execution is established.",
            "Role candidates are not proven selectable characters or visible animations.",
            "No source bodies, plaintext script paths, export names, artwork or audio are emitted.",
        ],
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--roles", type=Path, required=True)
    p.add_argument("--zero", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = build_role_zero_frame_init_join(
        json.loads(a.roles.read_text(encoding="utf-8")),
        json.loads(a.zero.read_text(encoding="utf-8")))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("entries", "limitations")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
