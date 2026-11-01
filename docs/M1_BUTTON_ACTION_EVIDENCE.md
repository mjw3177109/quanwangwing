# M1 — DefineButton2 embedded legacy-action inventory

The existing SWF script-container inventory covers DoAction (12), DoInitAction
(59), and ABC-bearing tags (72/82). **DefineButton2 (34) may also contain
ButtonCondAction legacy ActionRecords**. They were previously outside the
script-entry report's scope, so its legacy container count was not a complete
count of all possible embedded action containers.

`tools/build_button_action_evidence.py` reads the original SWF on the
Java 8 / FFDec runner, verifies the original SWF SHA-256 and each DefineButton2
tag header/length/character ID against the inventory, and follows the
ActionOffset and CondActionSize boundaries. It records condition bits, byte
offsets and action-byte lengths, but never writes ActionRecord bytes.

Run locally with the original SWF available:

```sh
python3 tools/build_button_action_evidence.py \
  --swf 拳皇wing1.4.swf \
  --manifest build/swf-analysis/swf-manifest.json \
  --output build/swf-analysis/button-action-evidence.json
```

The output is metadata only. The two-byte ActionOffset is measured from the
beginning of its own field, and a zero CondActionSize marks the final record.
Malformed offsets, sizes or manifest headers fail the run. Missing terminal
ActionEnd bytes and nonzero-sized final records are reported explicitly rather
than silently normalized.

**Evidence boundary:** these are embedded *action containers*, not AS1/AS2
function counts, verified key mappings, attack moves or proof of runtime
execution. A noncanonical trailing byte alone does not establish corruption.
Original SWF, scripts, images, sound and bytecode remain private.
