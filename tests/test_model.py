import unittest

import torch
from torch import nn

from fda_classifier.model import FdaMultiHeadModel


class _TinyEncoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.embed = nn.Embedding(30, 8)
        self.config = type("Config", (), {"hidden_size": 8})()

    def get_input_embeddings(self):
        return self.embed

    def forward(self, input_ids, attention_mask=None):
        del attention_mask
        hidden = self.embed(input_ids)
        return type("Output", (), {"last_hidden_state": hidden})()


class ModelTests(unittest.TestCase):
    def test_loss_covers_three_heads_and_evidence(self):
        model = FdaMultiHeadModel(
            _TinyEncoder(),
            num_severity=3,
            num_tiers=4,
            num_cfr=5,
            pad_token_id=0,
            start_token_id=1,
            eos_token_id=2,
        )
        outputs = model(
            input_ids=torch.randint(3, 30, (2, 6)),
            attention_mask=torch.ones(2, 6, dtype=torch.long),
            severity=torch.tensor([0, 2]),
            tier=torch.tensor([1, 3]),
            cfr=torch.tensor([4, 0]),
            evidence_ids=torch.tensor([[5, 6, 2], [7, 2, -100]]),
        )
        self.assertTrue(torch.isfinite(outputs["loss"]))
        self.assertEqual(tuple(outputs["severity_logits"].shape), (2, 3))
        self.assertEqual(tuple(outputs["tier_logits"].shape), (2, 4))
        self.assertEqual(tuple(outputs["cfr_logits"].shape), (2, 5))

        evidence = model.generate_evidence(torch.randint(3, 30, (1, 4)), torch.ones(1, 4, dtype=torch.long), max_length=3)
        self.assertEqual(evidence.shape[0], 1)
        self.assertGreaterEqual(evidence.shape[1], 1)

    def test_severity_weight_and_label_smoothing_change_the_loss(self):
        torch.manual_seed(0)
        model = FdaMultiHeadModel(_TinyEncoder(), num_severity=3, num_tiers=4, num_cfr=5, pad_token_id=0, start_token_id=1)
        batch = dict(
            input_ids=torch.randint(3, 30, (2, 6)),
            severity=torch.tensor([0, 2]),
            tier=torch.tensor([1, 3]),
            cfr=torch.tensor([4, 0]),
        )
        base = model(**batch)["loss"].item()
        model.severity_loss_weight = 3.0
        weighted = model(**batch)["loss"].item()
        model.severity_loss_weight = 1.0
        model.label_smoothing = 0.1
        smoothed = model(**batch)["loss"].item()
        self.assertGreater(weighted, base)
        self.assertNotAlmostEqual(smoothed, base, places=4)


if __name__ == "__main__":
    unittest.main()
