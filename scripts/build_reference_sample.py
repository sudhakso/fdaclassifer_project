"""Draw a stratified sample of drug GMP observations for blind relabelling.

Candidates are observations that carry both a flash-lite label (the S3 dataset)
and a Gemini-pro label (the earlier training file), and whose flash-lite CFR
reference is in 21 CFR 210 or 211. The sample is spread evenly over risk
category and over whether the two labellers agree on severity, with at most
one observation per inspection.

Writes blind batches (establishment type and narrative only) and, in a
separate directory, a key file with the existing labels.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

_DRUG_PARTS = ("210", "211")
_CFR_PART = re.compile(r"\b(\d{2,4})\.\d+")


def cfr_part(value: object) -> str | None:
    match = _CFR_PART.search(value) if isinstance(value, str) else None
    return match.group(1) if match else None


def candidates(s3_payload: dict, pro_payload: dict) -> list[dict]:
    pro = {
        (str(record.get("record_id")), str(observation.get("observation_number"))): observation
        for record in pro_payload["records"]
        for observation in record["observations"]
    }
    rows: list[dict] = []
    for record in s3_payload["records"]:
        for observation in record.get("observations") or []:
            key = (str(record.get("record_id")), str(observation.get("observation_number")))
            other = pro.get(key)
            if other is None or not observation.get("severity") or not other.get("severity"):
                continue
            if observation.get("risk_category") in (None, "unknown"):
                continue
            if cfr_part(observation.get("cfr_reference")) not in _DRUG_PARTS:
                continue
            rows.append({
                "record_id": key[0],
                "observation_number": observation.get("observation_number"),
                "establishment_type": record.get("establishment_type") or "",
                "full_details": observation["full_details"].strip(),
                "flash": {
                    "severity": observation["severity"],
                    "risk_category": observation.get("risk_category"),
                    "cfr_reference": observation.get("cfr_reference"),
                },
                "pro": {
                    "severity": other["severity"].lower(),
                    "primary_risk_tier": other.get("primary_risk_tier"),
                    "cfr_reference": other.get("cfr_reference"),
                },
            })
    return rows


def draw(rows: list[dict], size: int, seed: int) -> list[dict]:
    """Round-robin over (category, agreement) cells so every cell is filled evenly."""
    rng = random.Random(seed)
    cells: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for row in rows:
        agree = row["flash"]["severity"] == row["pro"]["severity"]
        cells[(row["flash"]["risk_category"], agree)].append(row)
    order = sorted(cells)
    for key in order:
        rng.shuffle(cells[key])
    picked: list[dict] = []
    used_inspections: set[str] = set()
    while len(picked) < size:
        progressed = False
        for key in order:
            while cells[key] and cells[key][-1]["record_id"] in used_inspections:
                cells[key].pop()
            if not cells[key]:
                continue
            row = cells[key].pop()
            used_inspections.add(row["record_id"])
            picked.append({**row, "labellers_agree_on_severity": key[1]})
            progressed = True
            if len(picked) >= size:
                break
        if not progressed:
            break
    rng.shuffle(picked)
    for index, row in enumerate(picked, start=1):
        row["id"] = f"R{index:03d}"
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s3-dataset", required=True, type=Path)
    parser.add_argument("--pro-labels", required=True, type=Path)
    parser.add_argument("--blind-dir", required=True, type=Path, help="Batches the labellers read")
    parser.add_argument("--key", required=True, type=Path, help="Existing labels, kept away from the labellers")
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with open(args.s3_dataset, encoding="utf-8") as handle:
        s3_payload = json.load(handle)
    with open(args.pro_labels, encoding="utf-8") as handle:
        pro_payload = json.load(handle)
    rows = candidates(s3_payload, pro_payload)
    sample = draw(rows, args.size, args.seed)

    args.blind_dir.mkdir(parents=True, exist_ok=True)
    args.key.parent.mkdir(parents=True, exist_ok=True)
    blind_fields = ("id", "establishment_type", "full_details")
    for start in range(0, len(sample), args.batch_size):
        batch = [{field: row[field] for field in blind_fields} for row in sample[start:start + args.batch_size]]
        path = args.blind_dir / f"batch_{start // args.batch_size + 1}.json"
        path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    key_rows = [{field: value for field, value in row.items() if field != "full_details"} for row in sample]
    args.key.write_text(json.dumps(key_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"candidates={len(rows)} sampled={len(sample)} inspections={len({row['record_id'] for row in sample})}")
    print("agree on severity:", dict(Counter(row["labellers_agree_on_severity"] for row in sample)))
    print("per category:", dict(Counter(row["flash"]["risk_category"] for row in sample)))
    print("flash severity:", dict(Counter(row["flash"]["severity"] for row in sample)))
    print("pro severity:", dict(Counter(row["pro"]["severity"] for row in sample)))


if __name__ == "__main__":
    main()
