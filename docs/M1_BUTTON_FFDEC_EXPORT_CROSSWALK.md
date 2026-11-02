# M1 — Source-keyed FFDec DefineButton2 export crosswalk

The AS2 diagnostic workflow joins two independently generated metadata sources:

- Byte-verified original SWF DefineButton2 / ButtonCondAction records, produced by tools/build_button_action_evidence.py from the original SWF and manifest.
- SHA-256-indexed FFDec 18.0.0 script export filenames, produced by the existing script-export-index.json validation step. Original decompiled .as files stay on the runner and are NOT uploaded.

Local invocation (after running the existing export and SWF inventory steps):

    python3 tools/build_button_ffdec_export_crosswalk.py --buttons build/as2-probe/button-action-evidence.json --export-index build/as2-probe/script-export-index.json --output build/as2-probe/button-ffdec-export-crosswalk.json
    python3 -m unittest discover -s tests -p 'test_button_ffdec_export_crosswalk.py' -v

The crosswalk uses (character ID, raw condition flags) to match observed FFDec DefineButton2_<id>/BUTTONCONDACTION on(<event>).as paths. The mapping is intentionally limited to flags actually observed in this SWF: 0x0001 (rollOver), 0x0002 (rollOut), 0x0004 (press), 0x0008 (release), and 0x2400 (keyPress Tab). Unknown or combined flags require review and fail closed. This is an observed exporter filename convention, not a general event decoder or proof of game input semantics.

The report includes source uncompressed action offsets, event flags, original action-container byte lengths, FFDec export relative paths, exported file lengths and SHA-256 hashes. It refuses missing, extra, duplicate or malformed button exports, mismatched SWF provenance and inconsistent totals.

A pre-merge local cross-check against the actual main SWF metadata artifact and AS2 probe metadata artifact from 2026-11-02 matched 72/72 action containers to 72 exported files across 68 action-bearing buttons. Complex button IDs 693, 701 and 715 map to separate on(release) exports, allowing a later restricted FFDec body/branch review.

NOT verified: equality of decompiled ActionScript semantics to original bytecode, runtime execution, UI activation, character identity, move data, hitboxes or 1:1 gameplay. No extracted source, SWF bytes, images or audio may be added to this report or published artifact.
