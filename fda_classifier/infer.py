"""Run a trained FDA model on one observation.

The result is the three classification labels plus the FMEA rationale the
evidence decoder gives as the reason for that classification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

from fda_classifier.model import FdaMultiHeadModel


def load_model(model_dir: str | Path) -> tuple[FdaMultiHeadModel, object, dict]:
    directory = Path(model_dir)
    with open(directory / "labels.json", encoding="utf-8") as handle:
        labels = json.load(handle)
    with open(directory / "heads.pt", "rb") as handle:
        heads = torch.load(handle, map_location="cpu", weights_only=False)
    encoder = AutoModel.from_pretrained(directory)
    model = FdaMultiHeadModel(
        encoder,
        num_severity=len(labels["severity"]),
        num_tiers=len(labels["primary_risk_tier"]),
        num_cfr=len(labels["cfr_reference"]),
        pad_token_id=heads["pad_token_id"],
        start_token_id=heads["start_token_id"],
        eos_token_id=heads["eos_token_id"],
    )
    model.severity_head.load_state_dict(heads["severity_head"])
    model.tier_head.load_state_dict(heads["tier_head"])
    model.cfr_head.load_state_dict(heads["cfr_head"])
    model.evidence_proj.load_state_dict(heads["evidence_proj"])
    model.evidence_rnn.load_state_dict(heads["evidence_rnn"])
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(directory)
    return model, tokenizer, labels


def predict(text: str, model_dir: str | Path, max_length: int = 512) -> dict[str, str]:
    model, tokenizer, labels = load_model(model_dir)
    encoded = tokenizer(text, truncation=True, max_length=max_length, return_tensors="pt")
    with torch.no_grad():
        outputs = model(input_ids=encoded["input_ids"], attention_mask=encoded["attention_mask"])
        evidence_ids = model.generate_evidence(
            encoded["input_ids"],
            encoded["attention_mask"],
            max_length=int(labels.get("max_evidence_tokens", 128)),
        )
    evidence = tokenizer.decode(evidence_ids[0], skip_special_tokens=True).strip()
    return {
        "severity": labels["severity"][int(outputs["severity_logits"].argmax(dim=-1)[0])],
        "primary_risk_tier": labels["primary_risk_tier"][int(outputs["tier_logits"].argmax(dim=-1)[0])],
        "cfr_reference": labels["cfr_reference"][int(outputs["cfr_logits"].argmax(dim=-1)[0])],
        "fmea_rationale": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    print(json.dumps(predict(args.text, args.model_dir), indent=2))


if __name__ == "__main__":
    main()
