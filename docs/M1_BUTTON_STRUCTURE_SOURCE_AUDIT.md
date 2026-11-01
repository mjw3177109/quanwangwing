# M1 — Original SWF button structural partition audit

This additive gate runs `tools/build_button_structure_audit.py` on the original
SWF in CI, after byte-verifying the complete DefineButton2 action inventory and
the existing opcode report. It uses `partition_top_level_actions` to skip
declared DefineFunction / DefineFunction2 code bodies.

## Scope and evidence

- Every verified ButtonCondAction byte range is accounted for exactly once.
- Records are classified as `partitioned`, `unsupported_nested_scope`, or
  `malformed_or_unsupported`. A rejected record is **not** claimed to have
  a verified top-level partition.
- For partitioned records only, the report compares the old flat first
  ActionEnd offset with the structure-aware first top-level ActionEnd offset,
  and counts declared functions, skipped body bytes and syntactic post-End
  records. It does not treat a post-End record as executed.
- All counts are re-derived from the source-verified byte ranges; CI checks
  aggregate closure and original SWF SHA-256.
- The output `button-structure-audit.json` contains only numeric offsets,
  character IDs, status flags and counts. No raw SWF, ActionScript, function
  names, operands, images or audio are uploaded.

## Run

```sh
python3 -m unittest discover -s tests -p 'test_button_structure_source_audit.py' -v
python3 tools/build_button_structure_audit.py \
  --swf 拳皇wing1.4.swf \
  --manifest build/swf-analysis/swf-manifest.json \
  --buttons build/swf-analysis/button-action-evidence.json \
  --opcodes build/swf-analysis/button-opcode-evidence.json \
  --output build/swf-analysis/button-structure-audit.json
```

## Limits and next gate

This audit is structural only: `runtime_reachability_verified=false` always.
The older flat opcode/tail/static-entry graph remains provisional and is
**not** silently rewritten by this change. Review CI's actual status counts,
investigate unsupported With/Try scopes, then migrate the downstream tail and
entry-graph consumers to structure-aware boundaries with new regression tests.
Do not infer original fighter actions, hitboxes or 1:1 completion from this audit.
