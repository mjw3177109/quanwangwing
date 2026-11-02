# M1 — Source-keyed button graph comparison

The hourly SWF analysis workflow now runs
`tools/compare_button_entry_graphs.py` after both existing button entry
graph reports have been generated. It joins the **legacy tail-only subset** to
the full source-verified partitioned report using
`(button_character_id, action_offset_uncompressed)`, never row order or
guessed character/action labels.

Inputs:
- `build/swf-analysis/button-static-entry-graph.json` — provisional
  flat analysis of records with post-ActionEnd bytes.
- `build/swf-analysis/button-partitioned-entry-graph.json` — verified
  top-level partition, including DefineFunction body boundaries.

Output: `build/swf-analysis/button-entry-graph-comparison.json` (metadata only).

For source-matched, graph-verified rows the report records differences in
visited syntactic record count, post-End candidate count and the boolean
syntactic path flag. A rejected or unsupported partitioned graph is **excluded**
from numeric comparison, with an explicit unverified status. It is not silently
treated as zero. All source keys, SHA-256 provenance, coverage and aggregate
deltas must close; malformed input fails CI. The workflow publishes only JSON.

## Validation

```sh
python3 -m unittest discover -s tests -p 'test_compare_button_entry_graphs.py' -v
python3 -m unittest discover -s tests -v
python3 tools/compare_button_entry_graphs.py \
  --legacy build/swf-analysis/button-static-entry-graph.json \
  --partitioned build/swf-analysis/button-partitioned-entry-graph.json \
  --output build/swf-analysis/button-entry-graph-comparison.json
```

The comparison **does not replace** the old graph, claim runtime reachability,
interpret Flash conditions, execute function calls, or prove 1:1 behavior.
It is a bounded diagnostic for prioritizing source-backed FFDec cross-checks.
No original SWF, extracted scripts, operands, artwork or audio are included.

## Partitioned-only row integrity gate

The comparison also validates **every** partitioned source row, including rows
outside the legacy tail subset. No row may claim Flash runtime execution, and
`graph_verified` must agree with the `verified_graph` status. A malformed
partitioned-only row now fails the comparison instead of escaping checks merely
because it has no legacy counterpart. Three synthetic regression tests cover
these cases; the hourly workflow already runs the complete Python test suite.
This is metadata validation, not new evidence of game behavior.

## Complete partitioned status accounting

The comparison also requires the source graph's five-category
`graph_status_counts` histogram to exactly match **all** 72 (or however many
the verified source reports) partitioned action rows, including those with no
legacy tail match. Unknown statuses, missing categories, forged totals and
non-integer counts fail closed. This closes a gap where a producer's declared
rejected/unsupported row totals could diverge from its actual rows while the
three legacy-matched rows still compared successfully. This is metadata
integrity only; no new Flash execution evidence or original asset bytes.

## Numeric difference triage (not runtime verification)

Verified source-matched rows now receive a metadata-only `difference_class`:
`unchanged` means all three compared values match;
`shadowed_body_only_candidate` means the visit delta equals the negative
legacy shadowed-function-body count, while post-End count and syntactic path
remain unchanged; all other differences are `requires_source_review`.
Unverified rows have **no** difference class and are excluded from the
histogram. CI checks that all compared rows are classified exactly once.
A shadowed-body-only numeric match is **not** proof of causality or Flash
runtime behavior: verify with restricted FFDec source before migration.
