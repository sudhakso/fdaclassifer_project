"""Score FDA 483 observations with a trained model.

The result for each observation is the three classification labels plus the
FMEA rationale the evidence decoder gives as the reason for that classification.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

from fda_classifier.data import load_inference_rows
from fda_classifier.model import FdaMultiHeadModel

logger = logging.getLogger(__name__)


def load_model(model_dir: str | Path, device: torch.device | None = None) -> tuple[FdaMultiHeadModel, object, dict]:
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
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(directory)
    return model, tokenizer, labels


def predict(text: str, model_dir: str | Path, max_length: int = 512) -> dict[str, str]:
    model, tokenizer, labels = load_model(model_dir)
    return predict_batch([text], model, tokenizer, labels, max_length=max_length, batch_size=1)[0]


def predict_batch(
    texts: list[str],
    model: FdaMultiHeadModel,
    tokenizer,
    labels: dict,
    max_length: int = 512,
    batch_size: int = 16,
) -> list[dict[str, str]]:
    """Score texts in batches. The evidence decoder runs on the same batch."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    device = next(model.parameters()).device
    max_evidence = int(labels.get("max_evidence_tokens", 128))
    predictions: list[dict[str, str]] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        encoded = tokenizer(
            chunk,
            truncation=True,
            max_length=max_length,
            padding=True,
            return_tensors="pt",
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.no_grad():
            outputs = model(input_ids=encoded["input_ids"], attention_mask=encoded["attention_mask"])
            evidence_ids = model.generate_evidence(
                encoded["input_ids"],
                encoded["attention_mask"],
                max_length=max_evidence,
            )
        severity = outputs["severity_logits"].argmax(dim=-1).tolist()
        tiers = outputs["tier_logits"].argmax(dim=-1).tolist()
        cfrs = outputs["cfr_logits"].argmax(dim=-1).tolist()
        for index in range(len(chunk)):
            predictions.append({
                "severity": labels["severity"][severity[index]],
                "primary_risk_tier": labels["primary_risk_tier"][tiers[index]],
                "cfr_reference": labels["cfr_reference"][cfrs[index]],
                "fmea_rationale": tokenizer.decode(evidence_ids[index], skip_special_tokens=True).strip(),
            })
        logger.info("Scored %s/%s observations", min(start + batch_size, len(texts)), len(texts))
    return predictions


def score_file(input_path: str | Path, model_dir: str | Path, output_path: str | Path, max_length: int, batch_size: int) -> int:
    with open(input_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = load_inference_rows(payload)
    if not rows:
        raise SystemExit(f"No observations with narrative text found in {input_path}")
    logger.info("Loaded %s observations from %s", len(rows), input_path)
    model, tokenizer, labels = load_model(model_dir)
    scored = predict_batch(
        [row["text"] for row in rows],
        model,
        tokenizer,
        labels,
        max_length=max_length,
        batch_size=batch_size,
    )
    predictions = []
    for row, scores in zip(rows, scored):
        item = {key: row[key] for key in ("record_id", "fei_number", "firm_name", "observation_number") if row.get(key) not in (None, "")}
        item.update(scores)
        predictions.append(item)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"predictions": predictions}, handle, indent=2)
        handle.write("\n")
    temporary.replace(destination)
    logger.info("Wrote %s predictions to %s", len(predictions), destination)
    return len(predictions)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", help="Score one observation string and print JSON")
    parser.add_argument("--input", help="JSON file of records, same shape as the training set")
    parser.add_argument("--output", help="Where to write {predictions: [...]} for --input")
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if bool(args.text) == bool(args.input):
        raise SystemExit("Pass either --text or --input")
    if args.text:
        print(json.dumps(predict(args.text, args.model_dir, max_length=args.max_length), indent=2))
        return
    if not args.output:
        raise SystemExit("--output is required with --input")
    score_file(args.input, args.model_dir, args.output, args.max_length, args.batch_size)


if __name__ == "__main__":
    main()
