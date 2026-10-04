import unittest

from fda_classifier.labelstudio import apply_annotations, prepare_tasks


FDA = {
    "records": [
        {
            "record_id": "A",
            "fei_number": "1",
            "firm_name": "Alpha",
            "establishment_type": "Outsourcing Facility",
            "observation_summary": "Aseptic failures.",
            "observations": [
                {
                    "observation_number": 1,
                    "full_details": "Smoke studies did not match production.",
                    "description": "ignored short text",
                    "citation": {
                        "act_cfr_number": "21 CFR 211.113",
                        "short_description": "Control of microbiological contamination",
                        "match_score": 0.5,
                    },
                },
                {
                    "observation_number": 2,
                    "full_details": "   ",
                    "citation": None,
                },
            ],
        },
        {
            "record_id": "B",
            "firm_name": "Beta",
            "establishment_type": "Drug Manufacturer",
            "observation_summary": "Laboratory controls.",
            "observations": [
                {
                    "observation_number": 1,
                    "full_details": "OOS results were invalidated without review.",
                    "citation": None,
                }
            ],
        },
    ]
}


class PrepareTests(unittest.TestCase):
    def test_prepare_keeps_narratives_and_citation_text(self):
        tasks = prepare_tasks(FDA)

        self.assertEqual(len(tasks), 2)
        first = tasks[0]["data"]
        self.assertEqual(first["record_id"], "A")
        self.assertNotIn("ignored short text", first["text"])
        self.assertIn("Smoke studies did not match production.", first["text"])
        self.assertIn("Citation: 21 CFR 211.113 — Control of microbiological contamination", first["text"])
        self.assertIsNone(tasks[1]["data"]["citation"])
        self.assertNotIn("Citation:", tasks[1]["data"]["text"])

    def test_limit_round_robin_takes_one_observation_from_each_inspection(self):
        tasks = prepare_tasks(FDA, limit=2, seed=1)
        self.assertEqual({task["data"]["record_id"] for task in tasks}, {"A", "B"})


class ApplyTests(unittest.TestCase):
    def test_apply_writes_severity_and_skips_unlabeled_tasks(self):
        tasks = prepare_tasks(FDA)
        tasks[0]["annotations"] = [
            {
                "result": [
                    {
                        "from_name": "severity",
                        "type": "choices",
                        "value": {"choices": ["critical"]},
                    }
                ]
            }
        ]

        sample, unlabeled = apply_annotations(tasks)

        self.assertEqual(unlabeled, 1)
        self.assertEqual(len(sample["records"]), 1)
        observation = sample["records"][0]["observations"][0]
        self.assertEqual(observation["severity"], "Critical")
        self.assertEqual(observation["citation"]["act_cfr_number"], "21 CFR 211.113")
        self.assertNotIn("match_score", observation["full_details"])


if __name__ == "__main__":
    unittest.main()
