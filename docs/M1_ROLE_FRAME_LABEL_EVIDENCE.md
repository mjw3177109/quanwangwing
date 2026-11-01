# M1 — Original SWF FrameLabel cross-check (metadata only)

This probe compares **hash-verified** FFDec AS2 role gotoAndPlay / gotoAndStop
string-literal candidates with actual FrameLabel tags from the original SWF
timeline-index.json. It checks script SHA-256, role identity, ExportAssets ID,
callsite order, source lines and method/argument/receiver classification before
comparing label text **inside the temporary Actions runner**.

Output role-frame-label-evidence.json records only the number of candidates
matching a label on the role's ExportAssets Sprite timeline, on other SWF
timelines, on neither, or with an unsupported escaped/complex literal. It
never publishes the label string, original ActionScript or original media.
A unique same-Sprite label match is only a **lexical candidate**, not a
verified this binding, move transition, hitbox or action frame.

Run after the AS2 export, timeline index, role crosswalk and callsite probe:

```bash
python3 tools/build_role_frame_label_evidence.py \
  --scripts build/as2-probe/exports/scripts \
  --export-index build/as2-probe/script-export-index.json \
  --role-crosswalk build/as2-probe/role-crosswalk.json \
  --call-evidence build/as2-probe/role-timeline-call-evidence.json \
  --timeline-index build/as2-probe/timeline-index.json \
  --output build/as2-probe/role-frame-label-evidence.json
```

Do not convert these results to gameplay JSON until MovieClip instance bindings,
actual frame labels and transitions are validated against FFDec and the original
Flash runtime. Unparsed escapes are reported rather than guessed.

## Static Sprite placement cross-check

The same verified string-literal callsites are now compared against a **static,
directed DefineSprite placement graph** built from the original SWF timeline
index's PlaceObject / PlaceObject2 / PlaceObject3 events. An edge A -> B
means that a placement event in timeline A references the DefineSprite
character ID for timeline B. Shape/button placements are not Sprite edges.

For each candidate label the analyzer records whether a matching timeline is
the role's own ExportAssets Sprite, a directly placed Sprite, a transitively
placed Sprite, or outside this static graph. It records minimum placement
hop count, candidate timeline counts and category totals; the report **does
not include original label strings or source/media bytes**. The traversal
is cycle-safe and the category totals must close against the number of
verified string-literal calls.

**Interpretation:** This graph is the union of static placements across
all frames, not a runtime display list. It ignores display depth changes,
time, dynamic attachMovie, ActionScript-created instances, and the
runtime receiver of this. An absent static path is *not* proof that a
label cannot be reached at runtime. In particular, the 16 role ExportAssets
Sprites may be zero-frame initialization symbols rather than the actual
visual MovieClips. Do not infer moves, frame numbers or hitboxes from
this classification.

The existing CLI invocation and metadata-only artifact remain unchanged;
the output now also includes static_placement_relation_counts and
per-call placement relationship metadata.
