import unittest

from fastapi.testclient import TestClient

from fda_classifier.data import instance_to_text
from fda_classifier.serving.app import Predictor, create_app


class InstanceTextTests(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(instance_to_text("  hello  "), "hello")

    def test_prebuilt_text(self):
        self.assertEqual(instance_to_text({"text": "ready"}), "ready")

    def test_observation_fields(self):
        text = instance_to_text({
            "establishment_type": "Drug Manufacturer",
            "observation_summary": "Incomplete batch records.",
            "full_details": "Missing second reviewer initials.",
        })
        self.assertEqual(
            text,
            "Drug Manufacturer | Summary: Incomplete batch records. "
            "| Details: Missing second reviewer initials.",
        )

    def test_missing_narrative_raises(self):
        with self.assertRaises(ValueError):
            instance_to_text({"establishment_type": "Drug Manufacturer"})


class PredictApiTests(unittest.TestCase):
    def setUp(self):
        self.predictor = Predictor()
        self.predictor.model = object()
        self.predictor.tokenizer = object()
        self.predictor.labels = {
            "severity": ["Minor", "Major", "Critical"],
            "primary_risk_tier": ["Tier 1"],
            "cfr_reference": ["211.192"],
            "max_evidence_tokens": 8,
        }
        self.predictor.model_dir = "/tmp/fake-model"
        self.predictor.predict_instances = lambda instances, parameters=None: [
            {
                "severity": "Major",
                "primary_risk_tier": "Tier 1",
                "cfr_reference": "211.192",
                "fmea_rationale": "Failure Mode: test",
            }
            for _ in instances
        ]
        self.client = TestClient(create_app(predictor=self.predictor, load_on_startup=False))

    def test_health_ok(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_predict_instances(self):
        response = self.client.post(
            "/predict",
            json={
                "instances": [
                    {
                        "establishment_type": "Drug Manufacturer",
                        "observation_summary": "Incomplete batch records.",
                        "full_details": "Missing second reviewer initials.",
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["predictions"]), 1)
        self.assertEqual(body["predictions"][0]["severity"], "Major")

    def test_predict_rejects_empty_instances(self):
        response = self.client.post("/predict", json={"instances": []})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
