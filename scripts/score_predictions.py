"""Score a model's test predictions against every reference label set.

Predictions come from ``python -m fda_classifier.infer`` run on an arm's test.json.
They are joined to the fixed universe on (record_id, observation_number) and scored
against the relabelled set, the flash-lite labels, the Gemini-pro severity, and,
for CFR section, the FDA citation where one is attached.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fda_classifier.metrics import accuracy, macro_f1  # noqa: E402

from assemble_arm import load_relabels, section  # noqa: E402

SEVERITIES = ("minor", "major", "critical")


def report(name: str, pairs: list[tuple[str | None, str | None]]) -> None:
    usable = [(pred, gold) for pred, gold in pairs if pred is not None and gold is not None]
    if not usable:
        print(f"   {name:<34s} n/a")
        return
    classes = sorted({gold for _, gold in usable} | {pred for pred, _ in usable})
    index = {label: position for position, label in enumerate(classes)}
    predictions = [index[pred] for pred, _ in usable]
    golds = [index[gold] for _, gold in usable]
    majority = max(Counter(golds).values()) / len(golds)
    print(f"   {name:<34s} accuracy={accuracy(predictions, golds):.1%} macro_f1={macro_f1(predictions, golds, len(classes)):.3f} "
          f"majority_baseline={majority:.1%} n={len(usable)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--universe", required=True, type=Path)
    parser.add_argument("--cfr-classes", required=True, type=Path, help="cfr_classes.json of the arm the model was trained on")
    parser.add_argument("--relabels-dir", type=Path)
    parser.add_argument("--min-match-score", type=float, default=0.8)
    args = parser.parse_args()

    test = {(row["record_id"], str(row["observation_number"])): row
            for row in json.loads(args.universe.read_text(encoding="utf-8")) if row["split"] == "test"}
    predictions = {(str(row.get("record_id")), str(row.get("observation_number"))): row
                   for row in json.loads(args.predictions.read_text(encoding="utf-8"))["predictions"]}
    if set(predictions) != set(test):
        raise SystemExit(f"predictions do not match the test set: {len(set(test) - set(predictions))} missing, {len(set(predictions) - set(test))} unexpected")
    cfr_classes = set(json.loads(args.cfr_classes.read_text(encoding="utf-8")))
    relabels = load_relabels(args.relabels_dir) if args.relabels_dir else {}

    def folded(value: object) -> str | None:
        name = section(value)
        if name is None:
            return None
        return name if name in cfr_classes else "other"

    rows = []
    for key, row in test.items():
        prediction = predictions[key]
        relabel = relabels.get(row["id"])
        if relabel is not None and relabel.get("in_scope") is False:
            continue
        citation = row["citation"] if isinstance(row.get("citation"), dict) else None
        rows.append({
            "pred_severity": prediction["severity"].lower(),
            "pred_category": prediction["primary_risk_tier"],
            "pred_cfr": prediction["cfr_reference"],
            "opus": relabel,
            "flash": row["flash"],
            "pro_severity": row["pro"]["severity"],
            "citation_section": section(citation.get("act_cfr_number")) if citation else None,
            "citation_score": (citation.get("match_score") or 0) if citation else 0,
        })
    print(f"test rows scored: {len(rows)} (of {len(test)}; out-of-scope rows are excluded)")
    print("predicted severity:", dict(Counter(row["pred_severity"] for row in rows)), "| distinct predicted categories:",
          len({row["pred_category"] for row in rows}), "| distinct predicted cfr:", len({row["pred_cfr"] for row in rows}))

    print("\nSEVERITY")
    report("vs relabelled set", [(row["pred_severity"], row["opus"]["severity"].lower() if row["opus"] else None) for row in rows])
    report("vs flash-lite", [(row["pred_severity"], row["flash"]["severity"]) for row in rows])
    report("vs Gemini pro", [(row["pred_severity"], row["pro_severity"]) for row in rows])
    consensus = [row for row in rows if row["opus"] and row["opus"]["severity"].lower() == row["flash"]["severity"] == row["pro_severity"]]
    report("where all three labellers agree", [(row["pred_severity"], row["flash"]["severity"]) for row in consensus])
    if any(row["opus"] for row in rows):
        counts = Counter((row["opus"]["severity"].lower(), row["pred_severity"]) for row in rows if row["opus"])
        print("   confusion (rows=relabelled set, cols=model)".ljust(48) + "".join(f"{label:>10s}" for label in SEVERITIES))
        for gold in SEVERITIES:
            print(f"   {gold:>44s} " + "".join(f"{counts[(gold, pred)]:10d}" for pred in SEVERITIES))

    print("\nRISK CATEGORY")
    report("vs relabelled set", [(row["pred_category"], row["opus"]["risk_category"].lower() if row["opus"] else None) for row in rows])
    report("vs flash-lite", [(row["pred_category"], row["flash"]["risk_category"]) for row in rows])

    print("\nCFR SECTION (sections outside the model's classes count as 'other')")
    report("vs relabelled set", [(row["pred_cfr"], folded(row["opus"].get("cfr_section")) if row["opus"] else None) for row in rows])
    report("vs flash-lite", [(row["pred_cfr"], folded(row["flash"]["cfr_reference"])) for row in rows])
    cited = [row for row in rows if row["citation_section"]]
    report("vs FDA citation, all matches", [(row["pred_cfr"], folded(row["citation_section"])) for row in cited])
    report(f"vs FDA citation, score >= {args.min_match_score}", [(row["pred_cfr"], folded(row["citation_section"])) for row in cited if row["citation_score"] >= args.min_match_score])


if __name__ == "__main__":
    main()
