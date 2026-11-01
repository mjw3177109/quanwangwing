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
