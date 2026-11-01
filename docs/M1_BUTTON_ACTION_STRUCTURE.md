# M1 — Strict ActionRecord structural partition (foundation)

This isolated, synthetic-test-verified helper `tools/button_action_structure.py` parses
the enclosing AS1/AS2 ActionRecord stream while skipping declared code-body bytes
following `0x9B DefineFunction` and `0x8E DefineFunction2` headers.

It distinguishes the first **top-level** ActionEnd from zero bytes inside a
function body and preserves syntactic post-End records without asserting that
Flash executes them. Malformed lengths, malformed function headers, out-of-bounds
function bodies and unsupported nested `With` / `Try` scopes fail closed.

The helper returns only local structural offsets, opcodes and counts; it does
not return function names, original operands, function bodies, source code or
media. The `runtime_reachability_verified` flag is always false.

## Validation and next gate

```sh
python3 -m unittest discover -s tests -p 'test_button_action_structure.py' -v
```

This is **not yet wired into the existing byte-verified button evidence
pipeline**. The older flat-walk reports remain provisional, and their counts
must not be represented as corrected top-level control-flow facts. Next,
cross-check this partition on the original SWF on the CI runner, handle
remaining nested scopes explicitly, then update upstream opcode/tail/graph
consumers and re-baseline source-derived counts. No original assets should be
uploaded in public artifacts.
