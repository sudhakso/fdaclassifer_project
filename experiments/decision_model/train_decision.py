"""Fine-tune a small LLM with a decision head (Unsloth) on the classifier's data, then score test files.

The model reads the finding together with three questions (severity, risk category, CFR section) whose
criteria are the labelling rubric, and returns a probability for every option of each question.

    python train_decision.py --train train.json --val val.json --cfr-classes cfr_classes.json \
        --output-dir /gcs/bucket/registry/RUN --predict fda=test.json --predictions-dir /gcs/bucket/evaluation

Data files have the trainer's shape: {"records": [{"record_id", "establishment_type",
"observations": [{"observation_number", "full_details", "severity", "primary_risk_tier", "cfr_reference"}]}]}.
Prediction files are written in the shape of ``python -m fda_classifier.infer`` so the same scoring scripts read them.
"""
import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from unsloth import FastDecisionModel, DecisionTrainer, is_bfloat16_supported  # isort: skip, must load before transformers
import torch
from transformers import TrainingArguments

from questions import questions

HEADS = ("severity", "primary_risk_tier", "cfr_reference")


def load_rows(path: str, asked: dict, limit: int | None) -> list[dict]:
    rows = []
    for record in json.loads(Path(path).read_text(encoding="utf-8"))["records"]:
        for observation in record.get("observations") or []:
            gold = {}
            for head in HEADS:
                label = observation.get(head)
                if label is not None:
                    gold[head] = {"label": label if label in asked[head]["criteria"] else "other" if head == "cfr_reference" else label}
            rows.append({
                "record_id": record["record_id"],
                "observation_number": observation["observation_number"],
                "state": f"Establishment type: {record.get('establishment_type') or 'not stated'}\n\n{observation['full_details']}",
                "questions": asked,
                "gold": gold,
            })
    return rows[:limit] if limit else rows


def update_manifest(path: str, updates: dict) -> None:
    """Merge fields into the run manifest, as fda_classifier.manifest does. This image does not carry that package."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    current = json.loads(destination.read_text(encoding="utf-8")) if destination.is_file() else {}
    current.update(updates)
    destination.write_text(json.dumps(current, indent=2, default=str) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train", required=True)
    parser.add_argument("--val", required=True)
    parser.add_argument("--cfr-classes", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--predict", action="append", default=[], metavar="NAME=FILE")
    parser.add_argument("--predictions-dir")
    parser.add_argument("--base-model", default="unsloth/Qwen3.5-2B")
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accumulation", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--limit", type=int, help="Use only the first N rows of every file (smoke test)")
    parser.add_argument("--manifest", help="Run manifest updated in place. The data build writes the source paths into the same file")
    args = parser.parse_args()
    if args.manifest:
        update_manifest(args.manifest, {
            "run_id": os.environ.get("RUN_ID"),
            "train_data": args.train,
            "eval_data": args.val,
            "base_model": args.base_model,
            "registry": args.output_dir,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "grad_accumulation": args.grad_accumulation,
            "learning_rate": args.learning_rate,
            "max_seq_length": args.max_seq_length,
            "train_status": "running",
            "train_started_at": datetime.now(timezone.utc).isoformat(),
        })

    asked = questions(json.loads(Path(args.cfr_classes).read_text(encoding="utf-8")))
    train_rows = load_rows(args.train, asked, args.limit)
    val_rows = load_rows(args.val, asked, args.limit)
    print(f"rows: train {len(train_rows)}, val {len(val_rows)}", flush=True)

    model, tokenizer = FastDecisionModel.from_pretrained(model_name=args.base_model, max_seq_length=args.max_seq_length, load_in_4bit=True)
    model = FastDecisionModel.get_peft_model(model, r=16, lora_alpha=16, lora_dropout=0, use_gradient_checkpointing="unsloth", random_state=3407)
    train_items, train_report = FastDecisionModel.build_dataset(train_rows, tokenizer, model)
    val_items, val_report = FastDecisionModel.build_dataset(val_rows, tokenizer, model)
    lengths = sorted(len(item["input_ids"]) for item in train_items)
    print(f"train decisions {train_report}, val decisions {val_report}", flush=True)
    print(f"input tokens: median {lengths[len(lengths) // 2]}, 99th {lengths[int(len(lengths) * 0.99)]}, max {lengths[-1]}", flush=True)
    if train_report["skipped"] or val_report["skipped"]:
        raise SystemExit("some decisions were skipped; fix the data or the questions before training")

    local = Path("/tmp/decision_run")
    # A full pass over val takes minutes, so progress checks during training use every seventh row of it.
    progress_items = val_items[::7] if len(val_items) > 700 else val_items
    steps_per_epoch = max(1, len(train_items) // (args.batch_size * args.grad_accumulation))
    trainer = DecisionTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_items,
        eval_dataset=progress_items,
        args=TrainingArguments(
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accumulation,
            num_train_epochs=args.epochs,
            learning_rate=args.learning_rate,
            lr_scheduler_type="cosine",
            warmup_steps=10,
            weight_decay=0.01,
            bf16=is_bfloat16_supported(),
            fp16=not is_bfloat16_supported(),
            eval_strategy="steps",
            eval_steps=max(1, steps_per_epoch // 4),
            save_strategy="no",
            logging_steps=10,
            output_dir=str(local / "trainer"),
            report_to="none",
            seed=3407,
        ),
    )
    started = time.time()
    trainer.train()
    print(f"training took {(time.time() - started) / 60:.1f} min; peak GPU memory {torch.cuda.max_memory_allocated() / 2**30:.1f} GB", flush=True)
    calibration = FastDecisionModel.calibrate(model, tokenizer, val_items)
    print(f"calibration on val: {calibration}", flush=True)

    export = local / "export"
    model.save_pretrained(str(export))
    (export / "questions.json").write_text(json.dumps(asked, indent=1) + "\n", encoding="utf-8")
    summary = {
        "base_model": args.base_model, "max_seq_length": args.max_seq_length, "epochs": args.epochs,
        "train_rows": len(train_rows), "val_rows": len(val_rows), "train_minutes": round((time.time() - started) / 60, 1),
        "calibration": calibration, "log_history": [entry for entry in trainer.state.log_history if any(key.startswith("eval") for key in entry)],
    }
    (export / "training_summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    shutil.copytree(export, args.output_dir, dirs_exist_ok=True)
    print(f"saved to {args.output_dir}", flush=True)
    if args.manifest:
        update_manifest(args.manifest, {
            "train_examples": len(train_rows),
            "eval_examples": len(val_rows),
            "train_metrics": calibration,
            "train_status": "complete",
            "train_finished_at": datetime.now(timezone.utc).isoformat(),
        })

    FastDecisionModel.for_inference(model)
    for spec in args.predict:
        name, path = spec.split("=", 1)
        rows = load_rows(path, asked, args.limit)
        predictions = []
        for index, row in enumerate(rows):
            answers = FastDecisionModel.predict(model, tokenizer, row["state"], asked)
            prediction = {"record_id": row["record_id"], "observation_number": row["observation_number"]}
            for head in HEADS:
                prediction[head] = answers[head]["answer"]
                prediction[f"{head}_confidence"] = round(max(answers[head]["probabilities"].values()), 6)
            prediction["severity_probabilities"] = answers["severity"]["probabilities"]
            predictions.append(prediction)
            if (index + 1) % 200 == 0:
                print(f"{name}: scored {index + 1}/{len(rows)}", flush=True)
        out = Path(args.predictions_dir) / f"predictions-{Path(args.output_dir.rstrip('/')).name}-{name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"predictions": predictions}, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {len(predictions)} predictions to {out}", flush=True)


if __name__ == "__main__":
    main()
