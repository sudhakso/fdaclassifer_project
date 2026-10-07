"""Encoder with classification heads plus an FMEA evidence decoder.

The classification heads are severity, primary_risk_tier, and cfr_reference.
The evidence decoder is trained on fmea_rationale and is what inference returns
as the reason for that classification.
"""

from __future__ import annotations

import torch
from torch import nn


class FdaMultiHeadModel(nn.Module):
    def __init__(
        self,
        encoder: nn.Module,
        num_severity: int,
        num_tiers: int,
        num_cfr: int,
        pad_token_id: int,
        start_token_id: int,
        eos_token_id: int | None = None,
    ) -> None:
        super().__init__()
        self.encoder = encoder
        hidden = encoder.config.hidden_size
        self.severity_head = nn.Linear(hidden, num_severity)
        self.tier_head = nn.Linear(hidden, num_tiers)
        self.cfr_head = nn.Linear(hidden, num_cfr)
        self.evidence_proj = nn.Linear(hidden, hidden)
        self.evidence_rnn = nn.GRU(hidden, hidden, batch_first=True)
        self.pad_token_id = pad_token_id
        self.start_token_id = start_token_id
        self.eos_token_id = eos_token_id
        self.severity_weights: torch.Tensor | None = None
        self.severity_loss_weight = 1.0
        self.label_smoothing = 0.0

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        severity: torch.Tensor | None = None,
        tier: torch.Tensor | None = None,
        cfr: torch.Tensor | None = None,
        evidence_ids: torch.Tensor | None = None,
        **kwargs,
    ) -> dict:
        del kwargs
        hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0]
        severity_logits = self.severity_head(hidden)
        tier_logits = self.tier_head(hidden)
        cfr_logits = self.cfr_head(hidden)
        loss = None
        if severity is not None and tier is not None and cfr is not None:
            weight = None
            if self.severity_weights is not None:
                weight = self.severity_weights.to(device=severity_logits.device, dtype=severity_logits.dtype)
            smoothing = self.label_smoothing
            loss = (
                self.severity_loss_weight
                * nn.functional.cross_entropy(severity_logits, severity, weight=weight, label_smoothing=smoothing)
                + nn.functional.cross_entropy(tier_logits, tier, label_smoothing=smoothing)
                + nn.functional.cross_entropy(cfr_logits, cfr, label_smoothing=smoothing)
            )
            if evidence_ids is not None and (evidence_ids >= 0).any():
                loss = loss + self._evidence_loss(hidden, evidence_ids)
        return {
            "loss": loss,
            "severity_logits": severity_logits,
            "tier_logits": tier_logits,
            "cfr_logits": cfr_logits,
        }

    def generate_evidence(self, input_ids: torch.Tensor, attention_mask: torch.Tensor | None, max_length: int) -> torch.Tensor:
        """Greedy-decode an FMEA rationale conditioned on the observation."""
        hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0]
        state = torch.tanh(self.evidence_proj(hidden)).unsqueeze(0)
        token = torch.full((hidden.size(0), 1), self.start_token_id, dtype=torch.long, device=hidden.device)
        pieces: list[torch.Tensor] = []
        for _ in range(max_length):
            embedded = self.encoder.get_input_embeddings()(token)
            output, state = self.evidence_rnn(embedded, state)
            logits = nn.functional.linear(output[:, -1], self.encoder.get_input_embeddings().weight)
            token = logits.argmax(dim=-1, keepdim=True)
            pieces.append(token)
            if self.eos_token_id is not None and bool((token == self.eos_token_id).all()):
                break
        return torch.cat(pieces, dim=1)

    def _evidence_loss(self, cls: torch.Tensor, evidence_ids: torch.Tensor) -> torch.Tensor:
        token_ids = evidence_ids.clone()
        token_ids[token_ids < 0] = self.pad_token_id
        start = torch.full(
            (token_ids.size(0), 1),
            self.start_token_id,
            dtype=torch.long,
            device=token_ids.device,
        )
        decoder_in = torch.cat([start, token_ids[:, :-1]], dim=1)
        embedded = self.encoder.get_input_embeddings()(decoder_in)
        state = torch.tanh(self.evidence_proj(cls)).unsqueeze(0)
        output, _ = self.evidence_rnn(embedded, state)
        logits = nn.functional.linear(output, self.encoder.get_input_embeddings().weight)
        return nn.functional.cross_entropy(
            logits.reshape(-1, logits.size(-1)),
            evidence_ids.reshape(-1),
            ignore_index=-100,
        )
