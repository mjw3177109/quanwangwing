# M1: Verified role timeline callsites joined to lexical function scopes

This incremental metadata-only join compares hash-verified role timeline callsite line numbers with the function-scope intervals already present in `role-crosswalk.json`. It does not read or publish original ActionScript text.

Inputs: `role-crosswalk.json`, `role-timeline-call-evidence.json` (both produced by the restricted FFDec AS2 export workflow). Output: `role-call-scope-join.json` containing per-call `scope_relation` (`unique`, `overlapping`, `outside`), count of covering scope candidates and lexical scope kind, with closed aggregate counts.

Command:

    python3 tools/build_role_call_scope_join.py --role-crosswalk build/as2-probe/role-crosswalk.json --call-evidence build/as2-probe/role-timeline-call-evidence.json --output build/as2-probe/role-call-scope-join.json

The join rejects mismatched SWF hashes, script provenance, role coverage, malformed intervals, invalid call lines and count mismatches. No function identifiers, string argument contents, source bodies or media are added to the artifact.

**Interpretation boundary:** lexical line containment is not a runtime call graph. In particular, a call in a `function_assignment` candidate does not establish the actual `this` binding or the target MovieClip timeline. Next steps: cross-check function assignment targets and role clip instance binding against original FFDec/DisplayObject evidence before assigning action frames or hitboxes.
