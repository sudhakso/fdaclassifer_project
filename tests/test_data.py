import unittest

from fda_classifier.data import (
    class_weights,
    flatten_observations,
    load_inference_rows,
    load_training_examples,
    normalize_cfr,
    normalize_tier,
    stratified_split,
)


NESTED = {
    "records": [
        {
            "establishment_type": "503B Outsourcing Facility",
            "observation_summary": "Aseptic processing and investigation failures.",
            "firm_name": "Example Pharma",
            "observations": [
                {
                    "description": "Short form that must not replace full_details.",
                    "full_details": "Batch records were missing a page number.",
                    "severity": "minor",
                    "citation": {
                        "act_cfr_number": "21 CFR 211.188",
                        "short_description": "Batch production and control records",
                        "long_description": "Batch production and control records shall be prepared for each batch.",
                        "match_score": 0.72,
                    },
                },
                {
                    "full_details": "No written procedure for complaint review.",
                    "severity": "Major",
                },
                {
                    "full_details": "Sterility failures were not investigated.",
                    "label": "Critical",
                },
                {"full_details": "Unlabeled row", "severity": "NAI"},
            ],
        }
    ]
}


class FlattenTests(unittest.TestCase):
    def test_record_text_is_establishment_summary_and_full_details(self):
        examples, skipped = flatten_observations(NESTED)

        self.assertEqual(skipped, 1)
        self.assertEqual([row["label"] for row in examples], ["Minor", "Major", "Critical"])
        self.assertEqual(
            examples[0]["text"],
            "503B Outsourcing Facility | Summary: Aseptic processing and investigation failures. "
            "| Details: Batch records were missing a page number. "
            "| Citation: 21 CFR 211.188 — Batch production and control records "
            "— Batch production and control records shall be prepared for each batch.",
        )
        self.assertNotIn("Short form", examples[0]["text"])
        self.assertNotIn("0.72", examples[0]["text"])
        self.assertTrue(examples[1]["text"].endswith("Details: No written procedure for complaint review."))
        self.assertNotIn("Citation:", examples[2]["text"])

    def test_flat_list_uses_the_same_template(self):
        examples, skipped = flatten_observations(
            [{"text": "Label mix-up on the line.", "severity": "Critical"}]
        )
        self.assertEqual(skipped, 0)
        self.assertEqual(examples[0]["label"], "Critical")
        self.assertEqual(
            examples[0]["text"],
            " | Summary:  | Details: Label mix-up on the line.",
        )


class LabelledRecordTests(unittest.TestCase):
    def test_labelled_record_keeps_three_targets_and_rationale(self):
        examples, skipped = load_training_examples({
            "records": [
                {
                    "establishment_type": "503B Outsourcing Facility",
                    "observation_summary": "Aseptic failures.",
                    "observations": [
                        {
                            "full_details": "Particle counts were paused during filling.",
                            "severity": "Critical",
                            "primary_risk_tier": "Tier 1 — Patient Safety Risks",
                            "cfr_reference": "21 CFR §211.113",
                            "fmea_rationale": "Failure Mode: monitoring gap. Cause: paused counter. Impact: contamination.",
                            "citation": {
                                "act_cfr_number": "21 CFR 211.113",
                                "short_description": "Control of microbiological contamination",
                            },
                        },
                        {
                            "full_details": "Missing a target.",
                            "severity": "Major",
                        },
                    ],
                }
            ]
        })

        self.assertEqual(skipped, 1)
        self.assertEqual(len(examples), 1)
        row = examples[0]
        self.assertEqual(row["severity"], "Critical")
        self.assertEqual(row["primary_risk_tier"], "Tier 1 — Direct Patient Safety Risks")
        self.assertEqual(row["cfr_reference"], "211.113")
        self.assertIn("Failure Mode: monitoring gap", row["fmea_rationale"])
        self.assertIn("Citation: 21 CFR 211.113", row["text"])
        self.assertIn("503B Outsourcing Facility | Summary: Aseptic failures.", row["text"])

    def test_inference_rows_keep_identifiers_without_labels(self):
        rows = load_inference_rows({
            "records": [
                {
                    "record_id": "307752",
                    "fei_number": "3001234567",
                    "firm_name": "Example Pharma LLC",
                    "establishment_type": "503B Outsourcing Facility",
                    "observation_summary": "Aseptic failures.",
                    "observations": [
                        {
                            "observation_number": 1,
                            "full_details": "Particle counts were paused during filling.",
                        },
                        {"observation_number": 2},
                    ],
                }
            ]
        })

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_id"], "307752")
        self.assertEqual(rows[0]["observation_number"], 1)
        self.assertIn("Details: Particle counts were paused during filling.", rows[0]["text"])

    def test_cfr_and_tier_normalization(self):
        self.assertEqual(normalize_cfr("CFR §211.165 / CFR §211.160"), "211.165 / 211.160")
        self.assertEqual(normalize_cfr("21 CFR Part 11"), "Part 11")
        self.assertEqual(
            normalize_tier("Additional Tier — Supplier/raw material quality lapses"),
            "Additional FDA-Relevant Risks - Supplier/raw material quality lapses",
        )


class SplitTests(unittest.TestCase):
    def test_stratified_split_keeps_every_class_in_train(self):
        examples, _ = flatten_observations(NESTED)
        doubled = examples + examples
        train, evaluation = stratified_split(doubled, eval_ratio=0.5, seed=1)

        self.assertEqual(len(train) + len(evaluation), len(doubled))
        self.assertEqual({row["label"] for row in train}, {"Minor", "Major", "Critical"})
        self.assertTrue(evaluation)

    def test_class_weights_upweight_the_rare_label(self):
        weights = class_weights(["Minor", "Minor", "Major", "Critical"])
        self.assertGreater(weights[2], weights[0])
        self.assertAlmostEqual(sum(weight * count for weight, count in zip(weights, (2, 1, 1))) / 4, 1.0)


if __name__ == "__main__":
    unittest.main()
