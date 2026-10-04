import importlib.util
import unittest
from pathlib import Path


def _load_helper():
    path = Path(__file__).resolve().parents[1] / "scripts" / "pretraining_label_helper.py"
    spec = importlib.util.spec_from_file_location("pretraining_label_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER = _load_helper()


class BatchTests(unittest.TestCase):
    def test_batches_respect_count_and_character_budget(self):
        rows = [{"record_id": str(i), "observation_number": 1, "full_details": "x" * 30} for i in range(5)]
        batches = list(HELPER.iter_batches(rows, batch_size=2, max_input_chars=10_000))
        self.assertEqual([len(batch) for batch in batches], [2, 2, 1])

        tight = list(HELPER.iter_batches(rows, batch_size=10, max_input_chars=80))
        self.assertTrue(all(len(batch) == 1 for batch in tight))
        self.assertEqual(sum(len(batch) for batch in tight), 5)

    def test_labelled_records_keep_narrative_and_citation(self):
        sources = {
            ("307752", "1"): {
                "record_id": "307752",
                "establishment_type": "503B Outsourcing Facility",
                "observation_summary": "Aseptic and quality failures.",
                "observation_number": 1,
                "full_details": "Retain samples contained particles.",
                "citation": {
                    "inspection_id": "1317132",
                    "citation_id": "1177",
                    "act_cfr_number": "21 CFR 211.165",
                    "short_description": "Testing and release",
                },
            },
            ("307752", "2"): {
                "record_id": "307752",
                "establishment_type": "503B Outsourcing Facility",
                "observation_summary": "Aseptic and quality failures.",
                "observation_number": 2,
                "full_details": "Smoke studies did not match production.",
                "citation": None,
            },
        }
        document = HELPER.assemble_labelled_records(
            [
                {
                    "record_id": "307752",
                    "observation_number": 1,
                    "severity": "Critical",
                    "cfr_reference": "211.165",
                    "primary_risk_tier": "Tier 1",
                    "fmea_rationale": "Particulate in sterile product.",
                },
                {
                    "record_id": "307752",
                    "observation_number": 2,
                    "severity": "Major",
                    "cfr_reference": "211.113",
                    "primary_risk_tier": "Tier 2",
                    "fmea_rationale": "Airflow was not unidirectional.",
                },
            ],
            sources,
        )

        self.assertEqual(len(document["records"]), 1)
        record = document["records"][0]
        self.assertEqual(record["establishment_type"], "503B Outsourcing Facility")
        self.assertEqual(record["observation_summary"], "Aseptic and quality failures.")
        self.assertEqual(len(record["observations"]), 2)
        self.assertEqual(record["observations"][0]["full_details"], "Retain samples contained particles.")
        self.assertEqual(record["observations"][0]["citation"]["act_cfr_number"], "21 CFR 211.165")
        self.assertNotIn("inspection_id", record["observations"][0]["citation"])
        self.assertNotIn("citation_id", record["observations"][0]["citation"])
        self.assertEqual(record["observations"][0]["cfr_reference"], "211.165")
        self.assertNotIn("citation", record["observations"][1])
        self.assertEqual(record["observations"][1]["cfr_reference"], "211.113")

    def test_pending_rows_skip_keys_already_scored(self):
        rows = [
            {"record_id": "A", "observation_number": 1},
            {"record_id": "A", "observation_number": 2},
        ]
        done = {HELPER.observation_key(rows[0])}
        pending = [row for row in rows if HELPER.observation_key(row) not in done]
        self.assertEqual(pending, [rows[1]])


if __name__ == "__main__":
    unittest.main()
