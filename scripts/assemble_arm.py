"""Write trainer-ready files for one label set (an experiment arm).

Every arm uses the same universe, the same firm-level split, and the same input
text. Only the three classification labels differ:

  flash  the flash-lite labels from the S3 dataset
  opus   the relabelled set (rows marked out of scope or not yet labelled are dropped)

The risk category goes into the trainer's ``primary_risk_tier`` field. CFR
references are reduced to section level, and sections with fewer than
``--min-cfr-count`` training rows become ``other``. The rationale is a fixed
placeholder in every arm, so the evidence decoder cannot favour one arm.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

_SECTION = re.compile(r"\d{2,4}\.\d+")
RATIONALE_PLACEHOLDER = "not used"


def section(value: object) -> str | None:
    match = _SECTION.search(value) if isinstance(value, str) else None
    return match.group(0) if match else None


def load_relabels(labels_dir: Path) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for path in sorted(labels_dir.glob("batch_*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            labels[row["id"]] = row
    return labels


def arm_labels(row: dict, arm: str, relabels: dict[str, dict]) -> dict | None:
    if arm == "flash":
        source = row["flash"]
        return {"severity": source["severity"], "risk_category": source["risk_category"], "cfr_section": section(source["cfr_reference"])}
    label = relabels.get(row["id"])
    if label is None or label.get("in_scope") is False:
        return None
    return {"severity": label["severity"].lower(), "risk_category": label["risk_category"].lower(), "cfr_section": section(label.get("cfr_section"))}


def to_records(
    rows: list[dict],
    labels: dict[str, dict] | None,
    cfr_classes: set[str] | None,
    drop_summary: bool = False,
    topics: dict[str, list[str]] | None = None,
) -> dict:
    grouped: dict[str, dict] = {}
    for row in rows:
        record = grouped.setdefault(row["record_id"], {
            "record_id": row["record_id"],
            "establishment_type": row["establishment_type"],
            "observation_summary": "" if drop_summary else row["observation_summary"],
            "observations": [],
        })
        details = row["full_details"]
        if topics and topics.get(row["id"]):
            details = f"{details} | Topics: {'; '.join(topics[row['id']])}"
        observation = {"observation_number": row["observation_number"], "full_details": details}
        if labels is not None:
            label = labels[row["id"]]
            observation.update({
                "severity": label["severity"].capitalize(),
                "primary_risk_tier": label["risk_category"],
                "cfr_reference": label["cfr_section"] if label["cfr_section"] in cfr_classes else "other",
                "fmea_rationale": RATIONALE_PLACEHOLDER,
            })
        record["observations"].append(observation)
    return {"records": list(grouped.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=("flash", "opus"))
    parser.add_argument("--relabels-dir", type=Path, help="Relabel output directory, required for --arm opus")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--min-cfr-count", type=int, default=10)
    parser.add_argument("--drop-summary", action="store_true", help="Leave the inspection-wide summary out of the input text")
    parser.add_argument("--val-ratio", type=float, default=0.0, help="Share of training firms written to val.json instead of train.json")
    parser.add_argument("--drop-borderline", action="store_true", help="Leave relabelled rows flagged borderline out of train.json")
    parser.add_argument(
        "--fda-cfr-min-score",
        type=float,
        help="In train and val, use the attached FDA citation's CFR section in place of the arm's label when the citation match score is at least this",
    )
    parser.add_argument("--topics-from", type=Path, help="S3 dataset whose per-observation topic categories are appended to the input text")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    relabels = load_relabels(args.relabels_dir) if args.arm == "opus" else {}
    topics = None
    if args.topics_from:
        source = json.loads(args.topics_from.read_text(encoding="utf-8"))
        topics = {
            f"{record.get('record_id')}-{observation.get('observation_number')}": [str(name) for name in observation.get("categories") or []]
            for record in source["records"]
            for observation in record.get("observations") or []
        }
    train_rows = [row for row in universe if row["split"] == "train"]
    labels = {row["id"]: label for row in train_rows if (label := arm_labels(row, args.arm, relabels)) is not None}
    kept = [row for row in train_rows if row["id"] in labels]
    if args.fda_cfr_min_score is not None:
        replaced = changed = 0
        for row in kept:
            citation = row["citation"] if isinstance(row.get("citation"), dict) else {}
            fda_section = section(citation.get("act_cfr_number"))
            if fda_section and (citation.get("match_score") or 0) >= args.fda_cfr_min_score:
                replaced += 1
                changed += fda_section != labels[row["id"]]["cfr_section"]
                labels[row["id"]]["cfr_section"] = fda_section
        print(f"FDA citation used as the CFR label on {replaced} rows; it differs from the arm's label on {changed}")
    if args.drop_borderline:
        kept = [row for row in kept if not relabels[row["id"]].get("borderline")]
    val_rows: list[dict] = []
    if args.val_ratio > 0:
        firms = sorted({row["firm"] for row in kept})
        random.Random(args.seed).shuffle(firms)
        val_firms = set(firms[: round(len(firms) * args.val_ratio)])
        val_rows = [row for row in kept if row["firm"] in val_firms]
        kept = [row for row in kept if row["firm"] not in val_firms]
    labels_train = {row["id"]: labels[row["id"]] for row in kept}
    counts = Counter(label["cfr_section"] for label in labels_train.values())
    cfr_classes = {name for name, count in counts.items() if name and count >= args.min_cfr_count}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "train.json").write_text(json.dumps(to_records(kept, labels, cfr_classes, args.drop_summary, topics), ensure_ascii=False) + "\n", encoding="utf-8")
    if val_rows:
        (args.output_dir / "val.json").write_text(json.dumps(to_records(val_rows, labels, cfr_classes, args.drop_summary, topics), ensure_ascii=False) + "\n", encoding="utf-8")
    test_rows = [row for row in universe if row["split"] == "test"]
    (args.output_dir / "test.json").write_text(json.dumps(to_records(test_rows, None, None, args.drop_summary, topics), ensure_ascii=False) + "\n", encoding="utf-8")
    (args.output_dir / "cfr_classes.json").write_text(json.dumps(sorted(cfr_classes)) + "\n", encoding="utf-8")

    print(f"arm={args.arm} train rows={len(kept)} val rows={len(val_rows)} (dropped {len(train_rows) - len(kept) - len(val_rows)}) test rows={len(test_rows)}")
    print("train severity:", dict(Counter(label["severity"] for label in labels_train.values())))
    print("categories:", len({label["risk_category"] for label in labels_train.values()}), "| cfr classes:", len(cfr_classes) + 1,
          f"| train rows folded into other: {sum(label['cfr_section'] not in cfr_classes for label in labels_train.values())}")


if __name__ == "__main__":
    main()
