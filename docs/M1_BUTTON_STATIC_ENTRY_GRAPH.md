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

## Unmodeled control opcode breakdown

The metadata report now separates the six top-level opcode classes whose
control-flow semantics the bounded graph does not interpret: 0x8A
(WaitForFrame), 0x8D (WaitForFrame2), 0x8E (DefineFunction2), 0x8F (Try),
0x94 (With), and 0x9B (DefineFunction). Counts are limited to syntactically
visited records and are closed per button and in aggregate by CI. They are
**not** an interpreter trace and do not establish that any nested function,
exception handler or skipped frame body executes. Original operands and
script source remain excluded from public artifacts. Use the resulting
per-opcode counts to prioritize private FFDec source cross-checks.


## Bounded DefineFunction header evidence

For syntactically visited `0x9B DefineFunction` ActionRecords, the
metadata-only audit now validates the null-terminated function name and
parameter strings, the parameter count, and the declared code-body length.
**SWF ActionDefineFunction's code body follows the ActionRecord and is
not included in its Length field.** We check the header's exact boundary
and that the declared body fits within the enclosing action byte stream.
The four classifications are `bounded_body`, `body_out_of_bounds`,
`header_length_mismatch`, and `malformed_header`, with aggregate
parameter/declared-body-byte totals only for bounded bodies. It does **not** publish names, operands,
function bodies, or decompiled scripts. CI requires these counts to close
against the already-verified visited `0x9b` opcode histogram.

A structurally complete header is **not** evidence of function invocation,
execution of the nested body, or valid Flash VM semantics. The next gate is
private FFDec cross-checking of the original function bodies and callsites.

This bounded header audit does not decode the nested function body.
The existing top-level entry graph does not partition nested function
body bytes from top-level ActionRecords, so it may over-approximate
control-flow paths; previous top-level branch counts must not be treated
as validated Flash VM paths.
Reference: SWF File Format Specification v19, ActionDefineFunction (0x9B).

## DefineFunction body-boundary warning (M1 follow-up)

The current static-entry graph is a **provisional flat ActionRecord walk**.
In SWF ActionDefineFunction (`0x9B`), `CodeSize` describes a separate
function-body region following the ActionRecord header; those bytes are **not**
enclosing top-level ActionRecords. Existing flat counts and branch-target
classifications can therefore be inflated by treating function-body bytes
as top-level instructions.

This increment adds three **metadata-only** checks for visited, structurally
bounded DefineFunction headers:

- `visited_define_function_body_shadowed_record_count`: count of provisional
  record-start offsets that fall inside a declared function-body region;
- `visited_define_function_body_contains_first_end`: whether the old
  first-ActionEnd boundary is inside a declared function body;
- `top_level_partition_verified`: false whenever a visited nonempty
  DefineFunction body has not yet been separated from the flat walk.

Aggregate counts are checked in CI. These warnings do **not** fix the upstream
`first_action_end_offset` / opcode/tail parsing, nor establish function
invocation, runtime reachability, or game controls. The next change must
implement a structure-aware parser across all dependent evidence stages and
re-baseline affected counts against the original SWF, without publishing
source code, original operands, art, or audio.
