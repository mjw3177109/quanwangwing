# M1 — Partitioned button entry graph (syntactic-only helper)

`tools/button_partitioned_entry_graph.py` builds a bounded graph from the
strict `partition_top_level_actions` result. Unlike the provisional flat graph,
it skips the declared bodies of ActionDefineFunction (0x9B) and
ActionDefineFunction2 (0x8E) when locating **top-level** record boundaries.

It follows ActionJump target edges, ActionIf target and fallthrough edges,
and ordinary syntactic fallthrough. An ActionEnd stops its own path. Targets
inside declared function bodies are classified separately and never enqueued.
Cycles are bounded by a visited set. Malformed Jump/If operands and unsupported
With/Try scopes fail closed rather than silently claiming a valid graph.

The returned data contains counts and classification flags only; no original
operands, source, SWF bytes, artwork or audio. The field
`runtime_reachability_verified` is **always false**. WaitForFrame skip behavior,
conditions, nested function calls and Flash VM state are not interpreted.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_button_partitioned_entry_graph.py' -v
python3 -m unittest discover -s tests -v
```

This is an **isolated helper plus synthetic regression tests**, not yet a
source-verified replacement for `button-static-entry-graph.json`. Existing
metadata reports remain provisional. The next gate is to re-read every original
ButtonCondAction range, compare this graph against the verified partition
metadata, and add a closed aggregate histogram to the CI artifact. Only then
may the new source-backed graph replace the provisional flat graph. Even that
would not prove actual Flash runtime execution or 1:1 fidelity.

## Original SWF source-verified graph audit

`tools/build_button_partitioned_graph_source_audit.py` re-verifies the
original SWF ButtonCondAction ranges through the existing opcode and structural
audits, then applies the bounded partitioned graph to each eligible range.
The hourly workflow writes `button-partitioned-entry-graph.json` (JSON
metadata only) and checks source SHA-256, complete row coverage, rejected
scope counts, and per-record / aggregate branch histogram closure.

Each record is marked `verified_graph`, `unsupported_nested_scope`,
`malformed_or_unsupported`, `missing_top_level_end`, or `graph_rejected`.
Only successfully traversed structural graphs count as verified. Rejected
graphs are visible and never silently counted as successful; CI checks their
coverage without assuming an unverified graph is executable. This does not
overwrite the old flat graph, tail report or any source asset.

To run locally after generating the upstream inventory:

```sh
python3 -m unittest discover -s tests -p 'test_button_partitioned_graph_source_audit.py' -v
python3 tools/build_button_partitioned_graph_source_audit.py \
  --swf 拳皇wing1.4.swf \
  --manifest build/swf-analysis/swf-manifest.json \
  --buttons build/swf-analysis/button-action-evidence.json \
  --opcodes build/swf-analysis/button-opcode-evidence.json \
  --output build/swf-analysis/button-partitioned-entry-graph.json
```

**Evidence boundary:** Even a source-verified syntactic entry path is not
proof of Flash VM execution. Conditions, function calls, WaitForFrame
semantics and runtime state remain unmodeled. No original ActionScript,
operands, SWF, image or audio bytes are included in the report. The next
step is to compare verified graph candidates with restricted FFDec
decompilation and trace real character/action references before migrating
the legacy downstream consumers.
