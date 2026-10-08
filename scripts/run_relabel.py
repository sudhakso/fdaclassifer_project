"""Prepare blind batches, label them with the rubric, and write trainer files.

Reads the inspection export and the Gemini-pro labelled file from the mount,
writes blind batches plus labels under the work directory, then writes
train.json, val.json, and test.json for the opus arm.

--provider anthropic labels with Claude through the Message Batches API and
needs ANTHROPIC_API_KEY. --provider gemini needs GEMINI_API_KEY.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fda_classifier.manifest import update_manifest
from label_with_rubric import label_batches, label_batches_anthropic

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "gemini": "gemini-3.1-pro-preview"}


def _run(script: str, arguments: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS)
    subprocess.check_call([sys.executable, str(SCRIPTS / script), *arguments], env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s3-dataset", required=True, type=Path)
    parser.add_argument("--pro-labels", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path, help="Blind batches, universe, and labels")
    parser.add_argument("--output-dir", required=True, type=Path, help="train.json, val.json, test.json")
    parser.add_argument("--rubric", type=Path, default=Path("/app/labeling/severity_rubric.md"))
    parser.add_argument("--provider", choices=sorted(DEFAULT_MODELS), default="gemini")
    parser.add_argument("--model", help="Defaults to claude-opus-5-5 for anthropic and gemini-3.1-pro-preview for gemini")
    parser.add_argument("--reuse-labels", type=Path, help="Labels directory of an earlier release. Anthropic only: its labels are kept when the model and rubric match")
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--manifest", type=Path, help="Run manifest updated in place. Training merges its own fields later")
    args = parser.parse_args()
    args.model = args.model or DEFAULT_MODELS[args.provider]

    if args.manifest:
        update_manifest(args.manifest, {
            "run_id": os.environ.get("RUN_ID"),
            "s3_dataset": str(args.s3_dataset),
            "pro_labels": str(args.pro_labels),
            "rubric": str(args.rubric),
            "label_provider": args.provider,
            "label_model": args.model,
            "relabel_dir": str(args.work_dir),
            "output_dir": str(args.output_dir),
            "relabel_status": "running",
            "relabel_started_at": datetime.now(timezone.utc).isoformat(),
        })

    _run("prepare_relabel_batches.py", [
        "--s3-dataset", str(args.s3_dataset),
        "--pro-labels", str(args.pro_labels),
        "--output-dir", str(args.work_dir),
        "--test-ratio", str(args.test_ratio),
        "--batch-size", str(args.batch_size),
    ])
    if args.provider == "anthropic":
        labelled = label_batches_anthropic(
            args.work_dir / "blind",
            args.work_dir / "labels",
            args.rubric,
            args.model,
            reuse_dir=args.reuse_labels,
            rows_per_request=args.batch_size,
        )
        print(f"labelled {labelled} new observations")
    else:
        labelled = label_batches(
            args.work_dir / "blind",
            args.work_dir / "labels",
            args.rubric,
            args.model,
            pause_seconds=args.pause_seconds,
        )
        print(f"labelled {labelled} new batches")
    _run("assemble_arm.py", [
        "--universe", str(args.work_dir / "universe.json"),
        "--arm", "opus",
        "--relabels-dir", str(args.work_dir / "labels"),
        "--drop-summary",
        "--val-ratio", str(args.val_ratio),
        "--output-dir", str(args.output_dir),
    ])
    if args.manifest:
        update_manifest(args.manifest, {
            "train_data": str(args.output_dir / "train.json"),
            "val_data": str(args.output_dir / "val.json"),
            "test_data": str(args.output_dir / "test.json"),
            "cfr_classes": str(args.output_dir / "cfr_classes.json"),
            "relabel_status": "complete",
            "relabel_finished_at": datetime.now(timezone.utc).isoformat(),
        })


if __name__ == "__main__":
    main()
