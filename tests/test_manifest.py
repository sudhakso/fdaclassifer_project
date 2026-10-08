import json
import tempfile
import unittest
from pathlib import Path

from fda_classifier.manifest import update_manifest


class UpdateManifestTests(unittest.TestCase):
    def test_creates_the_file_and_keeps_fields_from_the_other_stage(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "runs" / "fda-1" / "manifest.json"
            update_manifest(path, {"run_id": "fda-1", "s3_dataset": "sources/s3/a.json", "relabel_status": "complete"})
            update_manifest(path, {"registry": "registry/fda-1/", "train_status": "complete"})
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written["s3_dataset"], "sources/s3/a.json")
            self.assertEqual(written["relabel_status"], "complete")
            self.assertEqual(written["registry"], "registry/fda-1/")
            self.assertEqual(written["train_status"], "complete")
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
