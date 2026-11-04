import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_role_timeline_argument_provenance import build_evidence
from build_role_timeline_call_evidence import scan_calls


SOURCE_SHA = "a" * 64
SCRIPT_PATH = "scripts/__Packages/Kyo_role.as"


def make_fixture(source: bytes):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = root / SCRIPT_PATH
        script.parent.mkdir(parents=True)
        script.write_bytes(source)
        digest = hashlib.sha256(source).hexdigest()
        parsed = scan_calls(source)
        calls = {
            "source_sha256": SOURCE_SHA,
            "role_variant_count": 1,
            "call_candidate_count": len(parsed),
            "argument_kind_counts": {
                "integer_literal": sum(x["argument_kind"] == "integer_literal" for x in parsed),
                "string_literal": sum(x["argument_kind"] == "string_literal" for x in parsed),
                "dynamic_or_unresolved": sum(x["argument_kind"] == "dynamic_or_unresolved" for x in parsed),
            },
            "roles": [{
                "character_candidate": "Kyo", "variant": "base",
                "verified_as2_script_path": SCRIPT_PATH,
                "verified_as2_script_sha256": digest,
                "call_candidate_count": len(parsed), "calls": parsed,
            }],
        }
        scope_calls = [{
            "line": call["line"], "method": call["method"],
            "receiver_kind": call["receiver_kind"],
            "scope_relation": "unique", "scope_target_kind": "this_member",
            "scope_start_line": 1, "scope_end_line": len(source.decode().splitlines()),
            "runtime_binding_verified": False,
        } for call in parsed]
        scopes = {
            "source_sha256": SOURCE_SHA, "role_variant_count": 1,
            "call_candidate_count": len(parsed),
            "roles": [{
                "character_candidate": "Kyo", "variant": "base",
                "verified_as2_script_sha256": digest,
                "call_candidate_count": len(scope_calls), "calls": scope_calls,
            }],
        }
        crosswalk = {
            "source_sha256": SOURCE_SHA, "role_variant_count": 1,
            "roles": [{
                "character_candidate": "Kyo", "variant": "base",
                "verified_as2_script_path": SCRIPT_PATH,
                "verified_as2_script_sha256": digest,
                "verified_as2_script_size_bytes": len(source),
            }],
        }
        export = {
            "source_sha256": SOURCE_SHA, "script_count": 1,
            "total_bytes": len(source), "unexpected_empty_count": 0,
            "files": [{"path": SCRIPT_PATH, "size_bytes": len(source), "sha256": digest}],
        }
        timeline = {
            "source_sha256": SOURCE_SHA, "timeline_count": 1,
            "timelines": [{"timeline": "sprite:123",
                           "frame_labels": [{"label": "idle"}]}],
        }
        return root, export, crosswalk, calls, scopes, timeline, script


class RoleTimelineArgumentProvenanceTests(unittest.TestCase):
    def run_fixture(self, source):
        root, export, crosswalk, calls, scopes, timeline, script = make_fixture(source)
        try:
            result = build_evidence(root, export, crosswalk, calls, scopes, timeline)
            return result
        finally:
            # TemporaryDirectory is owned by make_fixture; keep its root alive until
            # build_evidence has completed, then the caller only uses the JSON result.
            pass

    def test_prior_string_assignment_matches_original_frame_label(self):
        source = (b"function update() {\n"
                  b"  var frameName = \\"idle\\";\n"
                  b"  this.gotoAndStop(frameName);\n"
                  b"}\n")
        result = self.run_fixture(source)
        self.assertEqual(result["dynamic_call_count"], 1)
        self.assertEqual(result["prior_assignment_candidate_count"], 1)
        self.assertEqual(result["prior_frame_label_assignment_candidate_count"], 1)
        self.assertEqual(result["calls_with_prior_frame_label_assignment_candidate_count"], 1)
        ref = result["events"][0]["identifier_references"][0]
        self.assertEqual(ref["prior_assignments"][0]["line"], 2)
        self.assertEqual(ref["prior_assignments"][0]["matching_timeline_count"], 1)
        self.assertFalse(result["events"][0]["runtime_binding_verified"])

    def test_comments_and_string_contents_do_not_create_assignments(self):
        source = (b"function update() {\n"
                  b"  // frameName = \\"wrong\\";\n"
                  b"  var note = \\"frameName = fake\\";\n"
                  b"  var frameName = \\"idle\\";\n"
                  b"  this.gotoAndStop(frameName);\n"
                  b"}\n")
        result = self.run_fixture(source)
        ref = result["events"][0]["identifier_references"][0]
        self.assertEqual(ref["prior_assignment_candidate_count"], 1)
        self.assertEqual(ref["prior_assignments"][0]["line"], 4)

    def test_assignment_outside_function_interval_is_not_joined(self):
        source = (b"var frameName = \\"idle\\";\n"
                  b"function update() {\n"
                  b"  this.gotoAndStop(frameName);\n"
                  b"}\n")
        result = self.run_fixture(source)
        ref = result["events"][0]["identifier_references"][0]
        self.assertEqual(ref["prior_assignment_candidate_count"], 0)
        self.assertEqual(ref["parameter_declaration_candidate_count"], 0)

    def test_concatenation_keeps_literal_and_identifier_evidence_separate(self):
        source = (b"function update() {\n"
                  b"  var frameName = \\"idle\\";\n"
                  b"  this.gotoAndStop(frameName + \\"_alt\\");\n"
                  b"}\n")
        result = self.run_fixture(source)
        event = result["events"][0]
        self.assertEqual(event["argument_shape"], "concatenation")
        self.assertEqual(event["literal_component_count"], 1)
        self.assertEqual(event["identifier_reference_count"], 1)
        self.assertEqual(event["identifier_references"][0]["prior_frame_label_assignment_candidate_count"], 1)
        self.assertEqual(event["literal_components"][1]["matching_timeline_count"], 0)

    def test_parameter_is_reported_without_claiming_binding(self):
        source = (b"function update(frameName) {\n"
                  b"  this.gotoAndStop(frameName);\n"
                  b"}\n")
        result = self.run_fixture(source)
        ref = result["events"][0]["identifier_references"][0]
        self.assertEqual(ref["parameter_declaration_candidate_count"], 1)
        self.assertEqual(ref["prior_assignment_candidate_count"], 0)
        self.assertFalse(ref["runtime_binding_verified"])

    def test_plaintext_identifiers_and_labels_are_not_published(self):
        source = (b"function update(privateFrameName) {\n"
                  b"  var privateLocal = \\"idle\\";\n"
                  b"  this.gotoAndStop(privateFrameName + privateLocal);\n"
                  b"}\n")
        result = self.run_fixture(source)
        serialized = json.dumps(result)
        self.assertNotIn("privateFrameName", serialized)
        self.assertNotIn("privateLocal", serialized)
        self.assertNotIn("idle", serialized)
        self.assertNotIn(SCRIPT_PATH, serialized)

    def test_source_hash_and_script_hash_mismatches_fail_closed(self):
        root, export, crosswalk, calls, scopes, timeline, script = make_fixture(
            b"function update() { this.gotoAndStop(frameName); }\n")
        export["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SWF source SHA-256 mismatch"):
            build_evidence(root, export, crosswalk, calls, scopes, timeline)
        export["source_sha256"] = SOURCE_SHA
        export["files"][0]["sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "Role script hash/length mismatch"):
            build_evidence(root, export, crosswalk, calls, scopes, timeline)

    def test_duplicate_role_and_call_accounting_fail_closed(self):
        root, export, crosswalk, calls, scopes, timeline, script = make_fixture(
            b"function update() { this.gotoAndStop(frameName); }\n")
        crosswalk["roles"].append(copy.deepcopy(crosswalk["roles"][0]))
        crosswalk["role_variant_count"] = 2
        with self.assertRaisesRegex(ValueError, "Duplicate or invalid role identity"):
            build_evidence(root, export, crosswalk, calls, scopes, timeline)
        root, export, crosswalk, calls, scopes, timeline, script = make_fixture(
            b"function update() { this.gotoAndStop(frameName); }\n")
        calls["call_candidate_count"] = 2
        with self.assertRaisesRegex(ValueError, "Role call total accounting mismatch"):
            build_evidence(root, export, crosswalk, calls, scopes, timeline)


if __name__ == "__main__":
    unittest.main()
