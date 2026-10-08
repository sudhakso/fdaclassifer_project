"""Fine-tune an encoder on FDA 483 severity, risk tier, and CFR reference."""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import shutil
from collections import Counter
from datetime import datetime, timezone

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModel,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

from fda_classifier.data import (
    LABELS,
    LABEL2ID,
    class_weights,
    load_training_examples,
    stratified_split,
)
from fda_classifier.gcs import download_blob, upload_directory
from fda_classifier.manifest import update_manifest
from fda_classifier.metrics import accuracy, macro_f1
from fda_classifier.model import FdaMultiHeadModel

MAX_EVIDENCE_TOKENS = 128

logger = logging.getLogger(__name__)


class _EncodedObservations(Dataset):
    def __init__(self, encodings: dict, severity: list[int], tier: list[int], cfr: list[int], evidence: list[list[int]]) -> None:
        self.encodings = encodings
        self.severity = severity
        self.tier = tier
        self.cfr = cfr
        self.evidence = evidence

    def __len__(self) -> int:
        return len(self.severity)

    def __getitem__(self, index: int) -> dict:
        item = {key: value[index] for key, value in self.encodings.items()}
        item["severity"] = self.severity[index]
        item["tier"] = self.tier[index]
        item["cfr"] = self.cfr[index]
        item["evidence_ids"] = self.evidence[index]
        return item


class _FdaCollator:
    def __init__(self, tokenizer) -> None:
        self._pad = DataCollatorWithPadding(tokenizer)

    def __call__(self, features: list[dict]) -> dict:
        batch = self._pad([{key: feature[key] for key in ("input_ids", "attention_mask") if key in feature} for feature in features])
        width = max(len(feature["evidence_ids"]) for feature in features)
        batch["evidence_ids"] = torch.tensor(
            [feature["evidence_ids"] + [-100] * (width - len(feature["evidence_ids"])) for feature in features],
            dtype=torch.long,
        )
        batch["severity"] = torch.tensor([feature["severity"] for feature in features], dtype=torch.long)
        batch["tier"] = torch.tensor([feature["tier"] for feature in features], dtype=torch.long)
        batch["cfr"] = torch.tensor([feature["cfr"] for feature in features], dtype=torch.long)
        return batch


class _FdaTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        outputs = model(**inputs)
        loss = outputs["loss"]
        return (loss, outputs) if return_outputs else loss

    def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys=None):
        inputs = self._prepare_inputs(inputs)
        with torch.no_grad():
            outputs = model(**inputs)
        loss = outputs["loss"].detach()
        if prediction_loss_only:
            return (loss, None, None)
        predictions = torch.stack([
            outputs["severity_logits"].argmax(dim=-1),
            outputs["tier_logits"].argmax(dim=-1),
            outputs["cfr_logits"].argmax(dim=-1),
        ], dim=1)
        labels = torch.stack([inputs["severity"], inputs["tier"], inputs["cfr"]], dim=1)
        return (loss, predictions, labels)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fda-data-path", required=True, help="Local path or gs:// URI of the JSON dataset")
    parser.add_argument("--output-gcs-uri", required=True, help="Local directory or gs:// URI for the exported model")
    parser.add_argument("--base-model", default="microsoft/deberta-v3-base")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--eval-ratio", type=float, default=0.1)
    parser.add_argument("--eval-data-path", help="Separate labelled file to evaluate on, instead of holding out --eval-ratio")
    parser.add_argument("--warmup-ratio", type=float, default=0.0)
    parser.add_argument("--severity-loss-weight", type=float, default=1.0, help="Multiplier on the severity loss relative to the tier and CFR losses")
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument("--early-stopping-patience", type=int, default=2)
    parser.add_argument(
        "--selection-metric",
        default="f1",
        choices=("f1", "combined"),
        help="Metric that picks the best epoch: severity macro F1, or the mean of that with tier and CFR accuracy",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=-1, help="Override epochs for a smoke run")
    parser.add_argument("--min-eval-f1", type=float, default=0.0, help="Fail the job when macro F1 is below this")
    parser.add_argument("--cache-dir", default="/tmp/training_cache")
    parser.add_argument("--checkpoint-dir", help="Where epoch checkpoints go. A restarted job resumes from the last one found here")
    parser.add_argument("--manifest", help="Run manifest updated in place. Relabel writes the source paths into the same file")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args()
    if args.manifest:
        update_manifest(args.manifest, {
            "run_id": os.environ.get("RUN_ID"),
            "train_data": args.fda_data_path,
            "eval_data": args.eval_data_path,
            "base_model": args.base_model,
            "registry": args.output_gcs_uri,
            "checkpoint_dir": args.checkpoint_dir,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "selection_metric": args.selection_metric,
            "train_status": "running",
            "train_started_at": datetime.now(timezone.utc).isoformat(),
        })
    cache_dir = args.cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    os.environ.setdefault("HF_HOME", os.path.join(cache_dir, "hf"))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    local_data_path = os.path.join(cache_dir, "fda_data.json")
    checkpoint_dir = args.checkpoint_dir or os.path.join(cache_dir, "checkpoints")
    export_dir = os.path.join(cache_dir, "trained_model")

    _stage_input(args.fda_data_path, local_data_path)
    with open(local_data_path, encoding="utf-8") as handle:
        payload = json.load(handle)

    examples, skipped = load_training_examples(payload)
    if skipped:
        logger.warning("Skipped %s observations missing severity, tier, CFR reference, or FMEA rationale", skipped)
    if not examples:
        raise SystemExit("No labeled observations found in the dataset")

    if args.eval_data_path:
        local_eval_path = os.path.join(cache_dir, "fda_eval_data.json")
        _stage_input(args.eval_data_path, local_eval_path)
        with open(local_eval_path, encoding="utf-8") as handle:
            eval_rows, _ = load_training_examples(json.load(handle))
        train_rows = examples
        examples = train_rows + eval_rows
    else:
        train_rows, eval_rows = stratified_split(examples, args.eval_ratio, args.seed)
    label_maps = _label_maps(examples)
    logger.info(
        "Examples=%s train=%s eval=%s severity=%s tiers=%s cfr=%s",
        len(examples),
        len(train_rows),
        len(eval_rows),
        dict(Counter(row["severity"] for row in examples)),
        len(label_maps["primary_risk_tier"]),
        len(label_maps["cfr_reference"]),
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    # The hub checkpoint is stored in float16 and current transformers keeps
    # that dtype on load. AdamW on float16 weights divides by zero (its epsilon
    # and the squared gradients underflow), so the weights must be float32.
    encoder = AutoModel.from_pretrained(args.base_model, torch_dtype=torch.float32)
    model = FdaMultiHeadModel(
        encoder,
        num_severity=len(label_maps["severity"]),
        num_tiers=len(label_maps["primary_risk_tier"]),
        num_cfr=len(label_maps["cfr_reference"]),
        pad_token_id=tokenizer.pad_token_id,
        start_token_id=tokenizer.cls_token_id if tokenizer.cls_token_id is not None else tokenizer.bos_token_id,
        eos_token_id=tokenizer.sep_token_id,
    )
    model.severity_weights = torch.tensor(class_weights([row["severity"] for row in train_rows]), dtype=torch.float)
    model.severity_loss_weight = args.severity_loss_weight
    model.label_smoothing = args.label_smoothing

    train_dataset = _encode(tokenizer, train_rows, args.max_length, label_maps)
    # A max-step smoke run can finish before the first epoch eval, which makes
    # load_best_model_at_end fail. Full runs keep the held-out split.
    use_eval = bool(eval_rows) and args.max_steps <= 0
    eval_dataset = _encode(tokenizer, eval_rows, args.max_length, label_maps) if use_eval else None
    logger.info("Class weights (Minor, Major, Critical)=%s", [round(value, 4) for value in model.severity_weights.tolist()])

    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    use_fp16 = torch.cuda.is_available() and not use_bf16
    training_kwargs = dict(
        output_dir=checkpoint_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        fp16=use_fp16,
        bf16=use_bf16,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=1,
        seed=args.seed,
        report_to="none",
        dataloader_num_workers=2,
        dataloader_pin_memory=torch.cuda.is_available(),
        load_best_model_at_end=eval_dataset is not None,
        metric_for_best_model=args.selection_metric if eval_dataset is not None else None,
        greater_is_better=True,
    )
    if args.max_steps > 0:
        training_kwargs["max_steps"] = args.max_steps
    _set_eval_strategy(training_kwargs, "epoch" if eval_dataset is not None else "no")
    _set_warmup(training_kwargs, args.warmup_ratio)
    training_args = TrainingArguments(**training_kwargs)

    trainer_kwargs = dict(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=_FdaCollator(tokenizer),
        compute_metrics=_compute_metrics if eval_dataset is not None else None,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience)] if eval_dataset is not None else None,
    )
    trainer_signature = inspect.signature(Trainer.__init__)
    if "processing_class" in trainer_signature.parameters:
        trainer_kwargs["processing_class"] = tokenizer
    else:
        trainer_kwargs["tokenizer"] = tokenizer

    trainer = _FdaTrainer(**trainer_kwargs)
    logger.info("Starting fine-tune of %s", args.base_model)
    resume = _last_complete_checkpoint(checkpoint_dir)
    if resume:
        logger.info("Resuming from %s", resume)
    trainer.train(resume_from_checkpoint=resume)
    if not all(torch.isfinite(parameter).all() for parameter in trainer.model.parameters()):
        raise SystemExit("Training produced non-finite weights; nothing was exported")

    metrics = trainer.evaluate() if eval_dataset is not None else {}
    eval_f1 = float(metrics.get("eval_f1", 0.0))
    if eval_dataset is not None and eval_f1 < args.min_eval_f1:
        raise SystemExit(f"eval macro F1 {eval_f1:.4f} is below --min-eval-f1 {args.min_eval_f1}")

    if os.path.exists(export_dir):
        shutil.rmtree(export_dir)
    os.makedirs(export_dir, exist_ok=True)
    trained = trainer.model
    trained.encoder.save_pretrained(export_dir)
    tokenizer.save_pretrained(export_dir)
    _save_heads(export_dir, trained, label_maps, tokenizer)
    summary = {
        "base_model": args.base_model,
        "labels": label_maps,
        "train_examples": len(train_rows),
        "eval_examples": len(eval_rows),
        "metrics": metrics,
    }
    with open(os.path.join(export_dir, "training_summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    _publish(export_dir, args.output_gcs_uri)
    if args.manifest:
        update_manifest(args.manifest, {
            "train_examples": len(train_rows),
            "eval_examples": len(eval_rows),
            "train_metrics": metrics,
            "train_status": "complete",
            "train_finished_at": datetime.now(timezone.utc).isoformat(),
        })
    if args.checkpoint_dir:
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
    logger.info("Fine-tuning job completed")


def _stage_input(source: str, local_path: str) -> None:
    if source.startswith("gs://"):
        logger.info("Downloading %s", source)
        download_blob(source, local_path)
        return
    shutil.copy(source, local_path)


def _publish(export_dir: str, destination: str) -> None:
    if destination.startswith("gs://"):
        logger.info("Uploading fine-tuned weights to %s", destination)
        uploaded = upload_directory(export_dir, destination)
        logger.info("Uploaded %s files", uploaded)
        return
    if os.path.abspath(export_dir) == os.path.abspath(destination):
        return
    if os.path.exists(destination):
        shutil.rmtree(destination)
    shutil.copytree(export_dir, destination)
    logger.info("Wrote model to %s", destination)


def _label_maps(examples: list[dict[str, str]]) -> dict[str, list[str]]:
    return {
        "severity": list(LABELS),
        "primary_risk_tier": sorted({row["primary_risk_tier"] for row in examples}),
        "cfr_reference": sorted({row["cfr_reference"] for row in examples}),
    }


def _encode(tokenizer, rows: list[dict[str, str]], max_length: int, label_maps: dict[str, list[str]]) -> _EncodedObservations:
    encodings = tokenizer(
        [row["text"] for row in rows],
        truncation=True,
        padding=False,
        max_length=max_length,
    )
    severity_ids = [LABEL2ID[row["severity"]] for row in rows]
    tier_to_id = {label: index for index, label in enumerate(label_maps["primary_risk_tier"])}
    cfr_to_id = {label: index for index, label in enumerate(label_maps["cfr_reference"])}
    tier_ids = [tier_to_id[row["primary_risk_tier"]] for row in rows]
    cfr_ids = [cfr_to_id[row["cfr_reference"]] for row in rows]
    evidence = []
    for row in rows:
        token_ids = tokenizer.encode(
            row["fmea_rationale"],
            add_special_tokens=False,
            truncation=True,
            max_length=MAX_EVIDENCE_TOKENS - 1,
        )
        if tokenizer.sep_token_id is not None:
            token_ids.append(tokenizer.sep_token_id)
        evidence.append(token_ids)
    return _EncodedObservations(encodings, severity_ids, tier_ids, cfr_ids, evidence)


def _save_heads(export_dir: str, model: FdaMultiHeadModel, label_maps: dict[str, list[str]], tokenizer) -> None:
    maps = {**label_maps, "max_evidence_tokens": MAX_EVIDENCE_TOKENS}
    with open(os.path.join(export_dir, "labels.json"), "w", encoding="utf-8") as handle:
        json.dump(maps, handle, indent=2)
        handle.write("\n")
    torch.save(
        {
            "severity_head": model.severity_head.state_dict(),
            "tier_head": model.tier_head.state_dict(),
            "cfr_head": model.cfr_head.state_dict(),
            "evidence_proj": model.evidence_proj.state_dict(),
            "evidence_rnn": model.evidence_rnn.state_dict(),
            "pad_token_id": tokenizer.pad_token_id,
            "start_token_id": model.start_token_id,
            "eos_token_id": model.eos_token_id,
        },
        os.path.join(export_dir, "heads.pt"),
    )


def _compute_metrics(eval_pred) -> dict[str, float]:
    predictions, labels = eval_pred
    severity_pred = predictions[:, 0].tolist()
    severity_gold = labels[:, 0].tolist()
    metrics = {
        "accuracy": accuracy(severity_pred, severity_gold),
        "f1": macro_f1(severity_pred, severity_gold),
        "tier_accuracy": accuracy(predictions[:, 1].tolist(), labels[:, 1].tolist()),
        "cfr_accuracy": accuracy(predictions[:, 2].tolist(), labels[:, 2].tolist()),
    }
    metrics["combined"] = (metrics["f1"] + metrics["tier_accuracy"] + metrics["cfr_accuracy"]) / 3
    return metrics


def _set_eval_strategy(kwargs: dict, strategy: str) -> None:
    parameters = inspect.signature(TrainingArguments.__init__).parameters
    if "eval_strategy" in parameters:
        kwargs["eval_strategy"] = strategy
    else:
        kwargs["evaluation_strategy"] = strategy


def _last_complete_checkpoint(checkpoint_dir: str) -> str | None:
    """Newest checkpoint that finished writing.

    The Trainer writes trainer_state.json last, so a directory without it was cut
    off mid-save (for example by a node shutdown) and cannot be resumed from.
    """
    if not os.path.isdir(checkpoint_dir):
        return None
    steps = [
        int(name.removeprefix("checkpoint-"))
        for name in os.listdir(checkpoint_dir)
        if name.startswith("checkpoint-")
        and name.removeprefix("checkpoint-").isdigit()
        and os.path.isfile(os.path.join(checkpoint_dir, name, "trainer_state.json"))
    ]
    return os.path.join(checkpoint_dir, f"checkpoint-{max(steps)}") if steps else None


def _set_warmup(kwargs: dict, ratio: float) -> None:
    """Newer transformers dropped warmup_ratio and read a fractional warmup_steps as a ratio."""
    if ratio <= 0:
        return
    parameters = inspect.signature(TrainingArguments.__init__).parameters
    if "warmup_ratio" in parameters:
        kwargs["warmup_ratio"] = ratio
    else:
        kwargs["warmup_steps"] = ratio


if __name__ == "__main__":
    main()
