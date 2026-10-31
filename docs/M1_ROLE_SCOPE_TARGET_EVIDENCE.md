# M1 — Role callsite scope assignment-target evidence (metadata only)

This incremental check joins the **hash-verified** role crosswalk with the prior
role callsite/function-scope join. It revalidates each callsite's scope interval,
script SHA-256, role identity and ExportAssets character ID before classifying
the *lexical assignment target shape* of the enclosing function.

Inputs: `role-crosswalk.json` and `role-call-scope-join.json` from the Java 8
FFDec AS2 diagnostic workflow. Output: `role-scope-target-evidence.json`.

```bash
python3 tools/build_role_scope_target_evidence.py \
  --role-crosswalk build/as2-probe/role-crosswalk.json \
  --call-scope-join build/as2-probe/role-call-scope-join.json \
  --output build/as2-probe/role-scope-target-evidence.json
```

The output contains per-call source line, method, lexical receiver class,
function scope line interval, target category and component count. Target
categories distinguish `global_member`, FFDec's `_locN_`-shaped
`ffdec_local_member`, `this_member`, `root_member`, `parent_member`,
`prototype_member`, `other_member`, `bare_identifier`, and `unresolved`.
It includes role ExportAssets character IDs and whether a matching Sprite
timeline exists, **without asserting that the target is that Sprite**.

The output deliberately excludes original function names, target identifiers,
source text, frame labels, and media. CI rejects SHA mismatches, inconsistent
symbol IDs, duplicate roles, scope interval/count discrepancies, and
non-closed category totals. Synthetic unit tests cover both successful and
fail-closed paths. This is not a dynamic `this` binding analysis or a call
graph; `_locN_` is a decompiler-shaped lexical identifier, not proof of a
runtime register binding. No animation frames or combat parameters are inferred.

Next: use private FFDec source and actual DisplayObject creation/placement
paths to prove the target MovieClip instance, then verify its frame labels
and transitions against the original SWF before adding any action data.
