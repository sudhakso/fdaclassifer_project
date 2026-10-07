import json
import tempfile
import unittest
from pathlib import Path

from label_with_rubric import batch_is_complete, normalize_label


class NormalizeLabelTests(unittest.TestCase):
    def test_accepts_a_rubric_category(self):
        label = normalize_label({
            "severity": "critical",
            "risk_category": "Contamination and mix-ups",
            "cfr_section": "211.113",
            "rule": "R1",
            "borderline": False,
            "in_scope": True,
            "reason": "ISO 5 wipe was non-sterile.",
        }, "307752-1")
        self.assertEqual(label["severity"], "Critical")
        self.assertEqual(label["risk_category"], "contamination and mix-ups")
        self.assertEqual(label["id"], "307752-1")

    def test_rejects_a_free_text_tier(self):
        with self.assertRaises(ValueError):
            normalize_label({
                "severity": "Major",
                "risk_category": "Tier 1 — Direct Patient Safety Risks",
                "cfr_section": "211.113",
            }, "1-1")


class BatchCompleteTests(unittest.TestCase):
    def test_complete_when_ids_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blind = root / "batch_001.json"
            labels = root / "labels.json"
            blind.write_text(json.dumps([{"id": "a"}, {"id": "b"}]), encoding="utf-8")
            labels.write_text(json.dumps([{"id": "b"}, {"id": "a"}]), encoding="utf-8")
            self.assertTrue(batch_is_complete(blind, labels))


if __name__ == "__main__":
    unittest.main()
