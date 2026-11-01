# M1 — DefineButton2 post-ActionEnd trailing-byte audit

This is a **metadata-only** follow-up to `M1_BUTTON_OPCODE_EVIDENCE.md`.
The existing byte-verified opcode walker reported three original
ButtonCondAction containers with an ActionEnd followed by 171 bytes in
aggregate. These bytes must not be silently treated as executable instructions.

The new `tools/build_button_tail_evidence.py` re-runs the upstream
button opcode audit against the original SWF and checks its report for exact
equality before reading any trailing region. It skips long-opcode operands,
finds the first opcode-boundary ActionEnd, and reports for each tail:

- Original button character ID and verified uncompressed action offset.
- Tail length and zero/nonzero byte counts (no byte values).
- Zero-only, nonzero-only or mixed byte class.
- Whether a **separate syntactic probe** starting after ActionEnd finds
  well-framed candidate records or a malformed/truncated region.

Run after the existing button opcode audit:

```sh
python3 tools/build_button_tail_evidence.py \
  --swf 拳皇wing1.4.swf \
  --manifest build/swf-analysis/swf-manifest.json \
  --buttons build/swf-analysis/button-action-evidence.json \
  --opcodes build/swf-analysis/button-opcode-evidence.json \
  --output build/swf-analysis/button-tail-evidence.json
```

The CI gate checks provenance, exact byte totals, class counts, candidate
status closure, and that **no runtime reachability is asserted**. The
syntactic post-End walk is diagnostic only: even a clean ActionRecord-shaped
tail is not proven to be executed. Runtime control flow, FFDec decompilation,
UI button behavior and AS1/AS2 semantics require separate evidence.

The output contains no original ActionScript, operands, SWF bytes, art,
music or audio. Do not publish original assets or source dumps.


## Pre-End branch-target boundary audit

For each of the verified post-ActionEnd regions, the same tool now walks
top-level ActionJump (0x99) and ActionIf (0x9D) records *before* the first
ActionEnd. It classifies their signed relative byte targets as:

- Candidate post-End ActionRecord boundary, or post-End ActionEnd terminator.
- Interior of a candidate post-End record.
- First ActionEnd boundary.
- Pre-End ActionRecord boundary or interior.
- Outside the action byte range, or invalid branch operand length.

The report emits only counts per class and aggregate counts; it does not
publish branch displacements, operands, byte sequences or decompiled source.
CI verifies that per-record and aggregate counts close exactly.

In addition to the target boundary categories, the report now separates
ActionJump and ActionIf counts for branches targeting a post-End candidate
record boundary and for branches targeting the post-End ActionEnd terminator.
Both categories are emitted per original button action container and in
aggregate. CI independently checks that each split matches its boundary
category and the sum of the per-container values.

This distinction can prioritize later control-flow investigation, but it
does **not** establish a reachable Flash execution path: the analyzer
does not evaluate ActionIf conditions, nested function bodies, WaitForFrame,
or runtime instance state.



**Evidence limit:** A matching byte boundary is not proof that Flash
executes any post-End record. The audit does not model nested function
bodies, conditional values, dynamic evaluation, WaitForFrame skip behavior
or the Flash runtime. An absence of matching targets cannot prove
runtime unreachability. The earlier separate syntactic post-End probe
remains a candidate-only classification.
