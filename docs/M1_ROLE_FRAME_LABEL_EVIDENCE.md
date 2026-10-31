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
