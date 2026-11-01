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
