# M1 — Role FrameLabel candidates versus literal attachMovie ExportAssets

This evidence-only join narrows possible original animation Sprite timelines without
guessing an ActionScript MovieClip receiver or action frame. It runs inside the
Java 8 / FFDec AS2 export job after the existing FrameLabel and attachMovie
probes have completed.

The join checks the original SWF source SHA-256 across seven evidence inputs,
validates the verified role script bytes against the export index, re-scans
gotoAndPlay/gotoAndStop callsites, and checks each previously reported
FrameLabel candidate count. It then intersects matching DefineSprite timelines
with SWF ExportAssets character IDs and the IDs of **literal**
attachMovie ExportAssets arguments found in verified FFDec scripts.

Four exclusive per-call classifications are emitted:

- no_sprite_label_candidate
- sprite_not_exported
- exported_no_literal_attach
- literal_attach_overlap

A literal attachMovie match means only that the same exported Sprite symbol
appears at a lexical attachMovie callsite somewhere in the exported scripts.
It does **not** establish that the call executes, that the role owns the
instance, or that the goto call targets that Sprite. Dynamic attachMovie
arguments remain unresolved and are counted separately.

Run within the private Actions workspace:

~~~sh
python3 tools/build_role_label_attach_join.py \
  --scripts build/as2-probe/exports/scripts \
  --export-index build/as2-probe/script-export-index.json \
  --role-crosswalk build/as2-probe/role-crosswalk.json \
  --call-evidence build/as2-probe/role-timeline-call-evidence.json \
  --frame-label-evidence build/as2-probe/role-frame-label-evidence.json \
  --timeline-index build/as2-probe/timeline-index.json \
  --asset-index build/as2-probe/asset-index.json \
  --attach-evidence build/as2-probe/runtime-attach-evidence.json \
  --output build/as2-probe/role-label-attach-join.json
~~~

The artifact contains only per-role and per-call counts, verified role script
SHA-256 values, callsite line numbers, and exclusive classifications. Original
FrameLabel strings, candidate Sprite character IDs, ExportAssets names,
ActionScript bodies, images, audio and original SWF bytes are not emitted.

The next step is to verify actual runtime instance creation and receiver
binding against the original Flash behavior, then recover real action frames,
hitboxes, sound triggers and combat timing. No 1:1 claim is justified here.
