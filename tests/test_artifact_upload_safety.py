import unittest
from pathlib import Path


class ArtifactUploadSafetyTests(unittest.TestCase):
    def test_swf_analysis_artifact_only_includes_json_metadata(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/swf-analysis.yml").read_text(encoding="utf-8")
        marker = "- name: Upload JSON metadata only (no raw tag logs or source bytes)"
        self.assertEqual(workflow.count(marker), 1)
        upload = workflow.split(marker, 1)[1]
        self.assertIn("build/swf-analysis/*.json", upload)
        self.assertNotIn("build/swf-analysis/*.log", upload)
        self.assertNotIn("build/swf-analysis/*.xml", upload)
        self.assertNotIn("build/swf-analysis/*.as", upload)
        self.assertNotIn("build/swf-analysis/*.swf", upload)


if __name__ == "__main__":
    unittest.main()
