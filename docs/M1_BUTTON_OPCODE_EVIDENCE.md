# M1 — DefineButton2 embedded ActionRecord opcode framing

This evidence-only pass extends the previously verified 74 button definitions and
72 ButtonCondAction containers. It reads each bounded ActionRecord stream from
the source-hash-verified original SWF, validates record offsets, lengths,
condition flags, tag headers and ActionEnd metadata against the existing
button-action evidence, and counts **opcode bytes only**.

Short ActionRecord opcodes (below 0x80) occupy one byte. Long opcodes
(0x80 and above) have a two-byte little-endian operand length. The first
ActionEnd (0x00) terminates the walk; trailing bytes are reported as
unparsed rather than assumed executable. Malformed/truncated records are
classified, not silently skipped.

Run after the existing button action evidence step:

```sh
python3 tools/build_button_opcode_evidence.py \
  --swf 拳皇wing1.4.swf \
  --manifest build/swf-analysis/swf-manifest.json \
  --buttons build/swf-analysis/button-action-evidence.json \
  --output build/swf-analysis/button-opcode-evidence.json
```

The CI gate checks source provenance, coverage of all button records, byte
accounting, opcode histogram closure and parse-status closure. No operands,
scripts, SWF bytes, images or audio are uploaded. Opcode counts are **not**
a verified AS1/AS2 function inventory, menu behavior, keyboard mapping,
attack command or evidence of runtime reachability. Follow up with verified
ActionRecord operand semantics and FFDec script cross-references.
