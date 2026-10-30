import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_attach_identifier_references import build_identifier_references


def fixture(root, sources, target="suffix"):
    records = []
    for rel, data in sources.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        records.append({"path": rel, "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    sha = "a" * 64
    index = {"source_sha256": sha, "script_count": len(records),
             "unexpected_empty_count": 0, "files": records}
    site = {"script_path": next(iter(sources)), "line": 3,
            "argument_shape": "concatenation", "concatenation_components": [
                {"kind": "identifier", "position": 1,
                 "identifier_sha256": hashlib.sha256(target.encode()).hexdigest()}]}
    provenance = {"source_sha256": sha, "dynamic_argument_count": 1,
                  "verified_script_bytes": sum(map(len, sources.values())),
                  "events": [site]}
    return index, provenance


class IdentifierReferencesTests(unittest.TestCase):
    def test_hashed_occurrences_and_cross_script_counts(self):
        sources = {
            "scripts/frame_17/DoAction.as":
                b'var suffix = "privateName";\n// suffix = "ignored"\nattachMovie("prefix" + suffix, "a", 1);\n',
            "scripts/Other.as": b'function test(suffix) { return suffix; }\n',
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, provenance = fixture(root, sources)
            result = build_identifier_references(root, index, provenance)
            target = result["targets"][0]
            self.assertEqual(result["identifier_target_count"], 1)
            self.assertEqual(target["occurrence_count"], 4)
            self.assertEqual(target["same_script_before_count"], 1)
            self.assertEqual(target["same_script_at_or_after_count"], 1)
            self.assertEqual(target["other_script_count"], 2)
            self.assertEqual(target["syntax_counts"]["variable_declaration"], 1)
            self.assertNotIn("privateName", json.dumps(result))
            self.assertNotIn('"suffix"', json.dumps(result))
            self.assertNotIn('"prefix"', json.dumps(result))

    def test_string_and_comment_occurrences_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sources = {"scripts/a.as": b'// suffix\nvar x="suffix";\nattachMovie("p" + suffix, "a", 1);'}
            index, provenance = fixture(root, sources)
            result = build_identifier_references(root, index, provenance)
            self.assertEqual(result["targets"][0]["occurrence_count"], 1)

    def test_tampered_script_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sources = {"scripts/a.as": b'attachMovie("p" + suffix, "a", 1);'}
            index, provenance = fixture(root, sources)
            index["files"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash/length mismatch"):
                build_identifier_references(root, index, provenance)

    def test_wrong_source_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, provenance = fixture(root, {"scripts/a.as": b'suffix'})
            provenance["source_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "SWF source SHA-256 mismatch"):
                build_identifier_references(root, index, provenance)

    def test_duplicate_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, provenance = fixture(root, {"scripts/a.as": b'suffix'})
            index["files"].append(dict(index["files"][0]))
            index["script_count"] = 2
            with self.assertRaisesRegex(ValueError, "Duplicate or invalid"):
                build_identifier_references(root, index, provenance)

    def test_invalid_identifier_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, provenance = fixture(root, {"scripts/a.as": b'suffix'})
            provenance["events"][0]["concatenation_components"][0]["identifier_sha256"] = "bad"
            with self.assertRaisesRegex(ValueError, "Invalid hashed"):
                build_identifier_references(root, index, provenance)

    def test_empty_target_still_verifies_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            index, provenance = fixture(root, {"scripts/a.as": b'var x=1;'})
            provenance["events"][0]["concatenation_components"] = []
            result = build_identifier_references(root, index, provenance)
            self.assertEqual(result["identifier_target_count"], 0)
            self.assertEqual(result["verified_script_count"], 1)


if __name__ == "__main__":
    unittest.main()
