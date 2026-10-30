# M1: SWF display-depth snapshots (metadata only)

This tool derives static depth-to-character-ID snapshots at each ShowFrame on each original timeline. It reads the verified `swf-manifest.json`, independently checks the original SWF SHA-256 and tag headers, and never writes source artwork, ActionScript, audio or SWF bytes.

```bash
python3 tools/build_display_depth_evidence.py --manifest build/swf-analysis/swf-manifest.json --output build/swf-analysis/display-depth-evidence.json
```

PlaceObject (4), PlaceObject2 (26), PlaceObject3 (70), RemoveObject (5), RemoveObject2 (28) are processed in original tag order. Move-only placement preserves the prior character ID; modifying an absent depth produces `null` and a recorded anomaly. ShowFrame (1) snapshots contain sorted active depths and character IDs. Declared vs observed frame count differences and ambiguous removals are reported, not silently corrected.

This is **not** a renderer: transforms, color, masks, clip depth, runtime `attachMovie`, nested sprite composition and actual frame timing remain unresolved. Do not treat snapshots as original move data, hitboxes, animation fidelity or proof of 1:1 gameplay. Unexpected anomaly counts require investigation against original bytes before using snapshots for rendering.
