"""Fix the experiment universe and split, and write blind batches for relabelling.

The universe is every drug GMP observation that carries both existing label sets
(see build_reference_sample.candidates). Firms are split into train and test, so
every later experiment arm trains and is scored on the same rows. Test rows are
written to the first batches so they are relabelled first.

A firm's split never changes when observations are added. Firms listed in the
split file keep the split recorded there (the 2026-10-07 experiment split). Any
other firm is placed by a hash of its id.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from build_reference_sample import candidates

DEFAULT_SPLIT_FILE = Path(__file__).resolve().parents[1] / "labeling" / "firm_split.json"


def firm_fraction(firm: str, salt: str) -> float:
    """A fixed number in [0, 1) for a firm, independent of which other firms exist."""
    return int(hashlib.sha256(f"{salt}:{firm}".encode("utf-8")).hexdigest()[:8], 16) / 16**8


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s3-dataset", required=True, type=Path)
    parser.add_argument("--pro-labels", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--split-file", type=Path, default=DEFAULT_SPLIT_FILE, help="JSON object of firm id to train or test")
    parser.add_argument("--seed", type=int, default=42, help="Order of rows within the batches only")
    args = parser.parse_args()

    with open(args.s3_dataset, encoding="utf-8") as handle:
        s3_payload = json.load(handle)
    with open(args.pro_labels, encoding="utf-8") as handle:
        pro_payload = json.load(handle)

    inspections = {str(record.get("record_id")): record for record in s3_payload["records"]}
    citations = {
        (str(record.get("record_id")), str(observation.get("observation_number"))): observation.get("citation")
        for record in pro_payload["records"]
        for observation in record["observations"]
    }
    rows = candidates(s3_payload, pro_payload)
    for row in rows:
        inspection = inspections[row["record_id"]]
        row["id"] = f"{row['record_id']}-{row['observation_number']}"
        row["firm"] = (inspection.get("fei_number") or "").strip() or f"inspection-{row['record_id']}"
        row["observation_summary"] = inspection.get("observation_summary") or ""
        row["citation"] = citations.get((row["record_id"], str(row["observation_number"])))

    rng = random.Random(args.seed)
    firms = {row["firm"] for row in rows}
    recorded = json.loads(args.split_file.read_text(encoding="utf-8")) if args.split_file.is_file() else {}
    for row in rows:
        hashed = "test" if firm_fraction(row["firm"], "test") < args.test_ratio else "train"
        row["split"] = recorded.get(row["firm"], hashed)

    test = [row for row in rows if row["split"] == "test"]
    train = [row for row in rows if row["split"] == "train"]
    rng.shuffle(test)
    rng.shuffle(train)
    ordered = test + train

    blind_dir = args.output_dir / "blind"
    blind_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "labels").mkdir(exist_ok=True)
    blind_fields = ("id", "establishment_type", "full_details")
    batches = 0
    for start in range(0, len(ordered), args.batch_size):
        batches += 1
        batch = [{field: row[field] for field in blind_fields} for row in ordered[start:start + args.batch_size]]
        (blind_dir / f"batch_{batches:03d}.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "universe.json").write_text(json.dumps(ordered, ensure_ascii=False) + "\n", encoding="utf-8")

    train_text = {row["full_details"] for row in train}
    print(f"universe={len(rows)} firms={len(firms)} train={len(train)} test={len(test)} batches={batches}")
    print(f"firms with a recorded split: {len(firms & set(recorded))}, placed by hash: {len(firms - set(recorded))}")
    print(f"test batches are 1 to {-(-len(test) // args.batch_size)} (the last of them also holds train rows)")
    print("firms in both splits:", len({row["firm"] for row in train} & {row["firm"] for row in test}))
    print("test narratives that also appear word for word in train:", sum(row["full_details"] in train_text for row in test))
    print("test rows with an FDA citation:", sum(isinstance(row["citation"], dict) for row in test))
    print("flash-lite severity, test:", dict(Counter(row["flash"]["severity"] for row in test)))


if __name__ == "__main__":
    main()
