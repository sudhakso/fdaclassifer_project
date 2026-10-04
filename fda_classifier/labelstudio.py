"""Turn FDA inspection JSON into Label Studio tasks, then back into training JSON.

The original export has no severity. ``prepare`` writes one Label Studio task per
observation that has ``full_details``, plus a records-shaped sample with the same
rows and no severity. After annotators choose Minor, Major, or Critical,
``apply`` reads the Label Studio export and writes the training file.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import defaultdict
from pathlib import Path

from fda_classifier.data import build_input_text, normalize_label

logger = logging.getLogger(__name__)

LABEL_CONFIG = """<View>
  <Header value="FDA 483 severity"/>
  <Text name="firm" value="$firm_name"/>
  <Text name="establishment" value="$establishment_type"/>
  <Text name="text" value="$text"/>
  <Choices name="severity" toName="text" choice="single" showInline="true">
    <Choice value="Minor"/>
    <Choice value="Major"/>
    <Choice value="Critical"/>
  </Choices>
</View>
"""


def load_json(path: str | Path) -> object:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def iter_narrative_observations(payload: object):
    """Yield (record, observation) pairs that have a non-empty full_details narrative."""
    if isinstance(payload, dict):
        records = payload.get("records")
        if records is None:
            records = payload.get("inspections") or []
    elif isinstance(payload, list):
        records = payload
    else:
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        for observation in record.get("observations") or []:
            if not isinstance(observation, dict):
                continue
            details = observation.get("full_details")
            if isinstance(details, str) and details.strip():
                yield record, observation


def select_observations(pairs: list[tuple[dict, dict]], limit: int, seed: int) -> list[tuple[dict, dict]]:
    """Keep every narrative, or a round-robin sample across inspections when limit is set."""
    if limit <= 0 or limit >= len(pairs):
        return list(pairs)

    buckets: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    order: list[str] = []
    for index, (record, observation) in enumerate(pairs):
        key = str(record.get("record_id") or f"row-{index}")
        if key not in buckets:
            order.append(key)
        buckets[key].append((record, observation))

    random.Random(seed).shuffle(order)
    selected: list[tuple[dict, dict]] = []
    while len(selected) < limit:
        progressed = False
        for key in order:
            bucket = buckets[key]
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def build_task(record: dict, observation: dict) -> dict:
    details = str(observation["full_details"]).strip()
    citation = observation.get("citation") if isinstance(observation.get("citation"), dict) else None
    return {
        "data": {
            "record_id": str(record.get("record_id") or ""),
            "observation_number": observation.get("observation_number"),
            "fei_number": record.get("fei_number") or "",
            "firm_name": record.get("firm_name") or "",
            "establishment_type": record.get("establishment_type") or "",
            "observation_summary": record.get("observation_summary") or "",
            "full_details": details,
            "citation": citation,
            "text": build_input_text(observation, record, details),
        }
    }


def tasks_to_sample(tasks: list[dict]) -> dict:
    """Records-shaped file. Severity is absent until Label Studio annotations are applied."""
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for task in tasks:
        data = task["data"]
        record_id = data["record_id"]
        if record_id not in grouped:
            order.append(record_id)
            grouped[record_id] = {
                "record_id": record_id,
                "fei_number": data["fei_number"],
                "firm_name": data["firm_name"],
                "establishment_type": data["establishment_type"],
                "observation_summary": data["observation_summary"],
                "observations": [],
            }
        observation = {
            "observation_number": data["observation_number"],
            "full_details": data["full_details"],
            "citation": data["citation"],
        }
        grouped[record_id]["observations"].append(observation)
    return {"records": [grouped[record_id] for record_id in order]}


def prepare_tasks(payload: object, limit: int = 0, seed: int = 42) -> list[dict]:
    pairs = select_observations(list(iter_narrative_observations(payload)), limit, seed)
    return [build_task(record, observation) for record, observation in pairs]


def severity_from_task(task: dict) -> str | None:
    annotations = task.get("annotations") or []
    if not annotations:
        return None
    for item in annotations[-1].get("result") or []:
        if item.get("from_name") != "severity":
            continue
        choices = (item.get("value") or {}).get("choices") or []
        if choices:
            return normalize_label(choices[0])
    return None


def apply_annotations(tasks: list[dict]) -> tuple[dict, int]:
    """Return (training records, unlabeled task count). Unlabeled tasks are omitted."""
    labeled: list[dict] = []
    unlabeled = 0
    for task in tasks:
        severity = severity_from_task(task)
        if severity is None:
            unlabeled += 1
            continue
        labeled.append(task)
    sample = tasks_to_sample(labeled)
    for record, task in zip(_observations_in_order(sample), labeled):
        record["severity"] = severity_from_task(task)
    return sample, unlabeled


def _observations_in_order(sample: dict) -> list[dict]:
    observations: list[dict] = []
    for record in sample["records"]:
        observations.extend(record["observations"])
    return observations


def prepare_files(source: Path, tasks_path: Path, sample_path: Path | None, limit: int, seed: int) -> int:
    tasks = prepare_tasks(load_json(source), limit=limit, seed=seed)
    write_json(tasks_path, tasks)
    if sample_path is not None:
        write_json(sample_path, tasks_to_sample(tasks))
    logger.info("Wrote %s Label Studio tasks to %s", len(tasks), tasks_path)
    return len(tasks)


def apply_file(export_path: Path, output_path: Path) -> tuple[int, int]:
    payload = load_json(export_path)
    if isinstance(payload, dict):
        tasks = payload.get("tasks") or payload.get("results") or []
    else:
        tasks = payload
    sample, unlabeled = apply_annotations(list(tasks))
    write_json(output_path, sample)
    labeled = sum(len(record["observations"]) for record in sample["records"])
    logger.info("Wrote %s labeled observations to %s (%s tasks had no severity)", labeled, output_path, unlabeled)
    return labeled, unlabeled


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="Translate FDA JSON into Label Studio tasks")
    prepare.add_argument("--input", required=True, type=Path, help="Original FDA inspection JSON")
    prepare.add_argument("--tasks", required=True, type=Path, help="Label Studio import file")
    prepare.add_argument("--sample", type=Path, help="Records-shaped JSON without severity")
    prepare.add_argument("--limit", type=int, default=0, help="Max observations. 0 keeps every narrative")
    prepare.add_argument("--seed", type=int, default=42)

    apply_parser = commands.add_parser("apply", help="Merge a Label Studio export onto the training JSON")
    apply_parser.add_argument("--export", required=True, type=Path, help="Label Studio JSON export")
    apply_parser.add_argument("--output", required=True, type=Path, help="Training JSON with severity filled in")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args()
    if args.command == "prepare":
        prepare_files(args.input, args.tasks, args.sample, args.limit, args.seed)
        return
    apply_file(args.export, args.output)


if __name__ == "__main__":
    main()
