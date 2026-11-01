# M1 — DefineButton2 static placement crosswalk

`tools/build_button_placement_crosswalk.py` joins three independently produced,
source-hash-matched metadata inventories: `swf-manifest.json`,
`button-action-evidence.json`, and `timeline-index.json`. It checks each button
character ID and definition offset against the original tag inventory, then
checks every matching PlaceObject / PlaceObject2 / PlaceObject3 reference against
its original tag offset, character reference, timeline, frame and depth.

Run after the inventory, timeline and embedded button-action steps:

```sh
python3 tools/build_button_placement_crosswalk.py \
  --manifest build/swf-analysis/swf-manifest.json \
  --buttons build/swf-analysis/button-action-evidence.json \
  --timeline build/swf-analysis/timeline-index.json \
  --output build/swf-analysis/button-placement-crosswalk.json
```

For the verified SWF SHA-256
`cf7d7225b488206b7e19914d2e09ac37aab3f1618a1b32d84f6d8423e7a4eebb`,
the November 1 metadata artifact yields **74** DefineButton2 definitions,
**68** containing embedded action records, and **106** static placement events
across those definitions. All 74 have at least one static placement; **98**
placement events reference action-bearing buttons. Four placements are on the
main timeline and 102 are in nested sprite timelines. These counts are
reproducible from the archived metadata, not inferred from screenshots.

This is a *static reference graph*, not proof that the button is visible,
clickable, reachable in a particular menu state, or bound to a particular
input. It does not follow dynamic `attachMovie`, button event conditions,
script execution or display-list lifetime. IDs, offsets, frames and depths are
not original art or ActionScript source; the tool emits metadata only. Original
SWF, exported scripts, graphics and audio remain separate from the public repo.

## Raw button conditions and frame co-location

The same metadata-only crosswalk now records a histogram of the **raw 16-bit
ButtonCondAction condition flags** and classifies each verified static button
placement according to whether a FrameLabel tag, a script-container tag, both,
or neither appear on the **same timeline and zero-based frame**. CI verifies
that raw-flag counts close against embedded action records and that the four
frame-context categories close against the static placement count. No label
strings or ActionScript bodies are included in the output.

These are structural co-locations, not decoded mouse/keyboard conditions,
reachable menu states, visible button instances, or evidence that a script
actually executes. The original SWF and extracted media remain excluded.

## SWF condition-bit decoding (metadata only)

The crosswalk additionally decodes the nine transition bits of each verified
16-bit ButtonCondAction condition field, and the seven-bit encoded key value
(bits 9..15). It emits transition-bit counts, a numeric key-code histogram,
and mutually exclusive transition-only/key-only/both/neither record counts.
The raw histogram remains available so decoding can be independently checked.
The bit layout follows the SWF DefineButton2 BUTTONCONDACTION specification;
this is a **format-level decoding**, not an observed runtime key binding.

In particular, a nonzero encoded key value does not establish an HTML5
keyboard mapping, a menu selection, or a fighting move. Multiple transition
bits can coexist in one action record; transition-bit totals therefore need
not equal the number of records. No source text, label text, media or SWF bytes
are emitted. The CI gate rejects missing or inconsistent aggregate counts.
