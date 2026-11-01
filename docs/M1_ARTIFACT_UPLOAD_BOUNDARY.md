# M1 artifact upload boundary

The public repository's scheduled SWF analysis now uploads **JSON metadata
only**. Previously, the artifact glob also included tags.log, which can
contain truncated hexadecimal previews of original SWF tag bytes. The logs
remain available in the temporary runner workspace for analysis but are no
longer copied into new swf-analysis artifacts.

This is a defense-in-depth change. Historical artifacts retain their own
seven-day retention period; this commit does not delete or revoke those
already created. Original SWF, FFDec exports, ActionScript, graphics and
audio remain excluded. GitHub job logs may still include diagnostic text
and should not print original asset payloads.
