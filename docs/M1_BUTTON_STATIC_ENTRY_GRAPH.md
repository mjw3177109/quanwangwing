# M1 — Bounded top-level button ActionRecord entry graph

This incremental audit addresses the three original DefineButton2 action
containers with ActionEnd trailing regions. It is **not** a Flash runtime
interpreter and makes **no claim of runtime reachability**.

## Evidence and execution

The input is the original `拳皇wing1.4.swf`, the FFDec-backed SWF manifest,
and the byte-verified button action, opcode and tail reports. The new tool
recomputes the upstream tail report from original bytes and rejects any
mismatched metadata before producing a graph.

```sh
python3 tools/build_button_static_entry_graph.py \
  --swf 拳皇wing1.4.swf \
  --manifest build/swf-analysis/swf-manifest.json \
  --buttons build/swf-analysis/button-action-evidence.json \
  --opcodes build/swf-analysis/button-opcode-evidence.json \
  --tails build/swf-analysis/button-tail-evidence.json \
  --output build/swf-analysis/button-static-entry-graph.json
```

The graph begins at the first top-level ActionRecord, treats ActionEnd as a
terminator, follows ActionJump's target edge, and follows both the target and
fallthrough edges of ActionIf. It follows only exact record boundaries and
rejects malformed record lengths. It counts unsupported control-flow opcodes
and invalid visited branch targets rather than silently declaring a complete
analysis. No branch displacement, operand, original script or raw SWF byte is
written to JSON.

The invalid *visited* branch targets are now classified without exposing
operand bytes or displacements: malformed two-byte branch operands,
targets before the action stream, targets at/after its end, and targets
inside (rather than at the start of) an ActionRecord. Each graph reports
the four class counts, and CI verifies both per-graph and aggregate count
closure. These categories help prioritize FFDec cross-checks but do not
prove the underlying branch is executed by Flash.

The report distinguishes a **syntactic top-level entry path candidate**
from a matching branch target that may itself be unreachable from the
action entry. Both are weaker than execution evidence. In particular,
ActionIf condition values, WaitForFrame skip semantics, nested functions,
With/Try bodies, event state and runtime VM behavior are **not modeled**.
A path candidate does not prove execution, and no path in this bounded
model does not prove unreachability.

CI verifies the source SHA, exact number of audited tail records, aggregate
count closure and that every runtime-reachability flag remains false.
The JSON-only artifact is safe to publish as metadata. Original SWF, FFDec
script dumps, character images, sounds and music must remain local or in
restricted storage.

## Next evidence gate

Compare any entry-path candidates against FFDec's decompilation on the
private runner, then investigate the AS1/AS2 function and UI timeline
contexts. Only original verified frame, sprite, input and hitbox data may
be used in the HTML5 game implementation.
