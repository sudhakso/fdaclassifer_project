"""Merge labelled synthetic batch record findings into an FDA training arm.

    python synthetic/build_training_arm.py --fda-arm data/fda_arms/opus_nosummary_val \
        --train-findings data/fda_synthetic/full data/fda_synthetic/sparse data/fda_synthetic/checks \
        --test-findings data/fda_synthetic/trial_v6 --test-source data/fda_synthetic/trial --holdout data/fda_synthetic/checks/holdout_seed_ids.json \
        --output data/fda_arms/opus_plus_synthetic_v2

A finding is kept when its two blind readers gave the same severity. All wordings of a finding get
that label and stay in the same split. Synthetic findings are split train/val by finding. The
held-out synthetic test set is a separate batch of findings plus the seed ids listed in --holdout.
"""
import argparse, glob, hashlib, json, os, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fda_classifier.manifest import update_manifest


def section(value):
    match = re.search(r"\d{3}\.\d+", str(value or ""))
    return match.group(0) if match else None


def agreed(labels_dir: Path, findings_dir: Path):
    key = json.load(open(labels_dir / "key.json"))
    labels = {l["id"]: l for path in glob.glob(str(labels_dir / "labels" / "*.json")) for l in json.load(open(path))}
    reads = {}
    for row_id, info in key.items():
        if row_id in labels:
            reads.setdefault(info["seed_id"], {})[info["pass"]] = labels[row_id]
    findings = {f["seed_id"]: f for path in sorted(glob.glob(str(findings_dir / "findings_*.json"))) for f in json.load(open(path))}
    kept, dropped = [], 0
    for seed_id, finding in findings.items():
        pair = reads.get(seed_id, {})
        if set(pair) != {"a", "b"} or pair["a"]["severity"] != pair["b"]["severity"]:
            dropped += 1
            continue
        kept.append({"seed_id": seed_id, "establishment_type": finding["establishment_type"], "wordings": wordings(finding["wordings"]), "label": pair["a"]})
    return kept, dropped


def wordings(written):
    """Three full wordings per finding. Check-style findings are written as separate fields and composed here."""
    if "observation" not in written:
        return written
    return {
        "observation": written["observation"],
        "observation_expected_actual": f"{written['observation']} Expected: {written['expected']} Actual: {written['actual']}",
        "narrative": written["narrative"],
    }


def records(findings, cfr_classes):
    out = []
    for f in findings:
        label = f["label"]
        cfr = section(label.get("cfr_section"))
        for style, text in f["wordings"].items():
            out.append({
                "record_id": f"syn-{f['seed_id']}-{style}",
                "establishment_type": f["establishment_type"],
                "observation_summary": "",
                "observations": [{
                    "observation_number": 1,
                    "full_details": text,
                    "severity": label["severity"].capitalize(),
                    "primary_risk_tier": label["risk_category"].lower(),
                    "cfr_reference": cfr if cfr in cfr_classes else "other",
                    "fmea_rationale": "not used",
                }],
            })
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fda-arm", required=True, type=Path)
    parser.add_argument("--train-findings", required=True, type=Path, nargs="+", help="Folders with findings_*.json, key.json and labels/")
    parser.add_argument("--holdout", type=Path, help="JSON list of seed ids to move from training to the held-out test set")
    parser.add_argument("--test-findings", required=True, type=Path, help="Folder with key.json and labels/ for the held-out findings")
    parser.add_argument("--test-source", required=True, type=Path, help="Folder with the held-out findings_*.json")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--min-cfr-count", type=int, default=10)
    parser.add_argument("--manifest", type=Path, help="Run manifest updated in place with the inputs and the files written")
    args = parser.parse_args()

    train_pool, dropped = [], 0
    for folder in args.train_findings:
        kept, lost = agreed(folder, folder)
        print(f"{folder}: {len(kept)} kept, {lost} dropped | {dict(Counter(f['label']['severity'] for f in kept))}")
        train_pool, dropped = train_pool + kept, dropped + lost
    test, test_dropped = agreed(args.test_findings, args.test_source)
    holdout = set(json.load(open(args.holdout))) if args.holdout else set()
    test += [f for f in train_pool if f["seed_id"] in holdout]
    train_pool = [f for f in train_pool if f["seed_id"] not in holdout]
    print(f"training findings: {len(train_pool)} kept, {dropped} dropped (readers disagree or a read is missing)")
    print(f"held-out findings: {len(test)} kept, {test_dropped} dropped")
    is_val = lambda f: int(hashlib.sha256(f"val:{f['seed_id']}".encode()).hexdigest()[:8], 16) / 16**8 < args.val_ratio
    val, train = [f for f in train_pool if is_val(f)], [f for f in train_pool if not is_val(f)]

    cfr_classes = set(json.load(open(args.fda_arm / "cfr_classes.json")))
    counts = Counter(section(f["label"].get("cfr_section")) for f in train)
    added = {name for name, count in counts.items() if name and count >= args.min_cfr_count} - cfr_classes
    cfr_classes |= added
    print("CFR sections added from synthetic findings:", sorted(added))

    args.output.mkdir(parents=True, exist_ok=True)
    for split, synthetic in (("train", train), ("val", val)):
        fda = json.load(open(args.fda_arm / f"{split}.json"))["records"]
        merged = fda + records(synthetic, cfr_classes)
        (args.output / f"{split}.json").write_text(json.dumps({"records": merged}, ensure_ascii=False) + "\n", encoding="utf-8")
        mix = Counter(o["severity"] for r in merged for o in r["observations"])
        print(f"{split}: {sum(len(r['observations']) for r in fda)} FDA rows + {len(synthetic) * 3} synthetic rows ({len(synthetic)} findings) | severity mix {dict(mix)}")
    (args.output / "synthetic_test.json").write_text(json.dumps({"records": records(test, cfr_classes)}, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.output / "cfr_classes.json").write_text(json.dumps(sorted(cfr_classes)) + "\n")
    print(f"synthetic_test: {len(test) * 3} rows ({len(test)} findings) | severity mix {dict(Counter(f['label']['severity'] for f in test))}")
    for name, group in (("train", train), ("val", val)):
        print(f"synthetic {name} label mix:", dict(Counter(f["label"]["severity"] for f in group)))
    if args.manifest:
        update_manifest(args.manifest, {
            "run_id": os.environ.get("RUN_ID"),
            "fda_arm": str(args.fda_arm),
            "synthetic_train_findings": [str(folder) for folder in args.train_findings],
            "synthetic_test_findings": str(args.test_findings),
            "synthetic_test_source": str(args.test_source),
            "synthetic_holdout": str(args.holdout) if args.holdout else None,
            "synthetic_findings": {"train": len(train), "val": len(val), "test": len(test), "dropped": dropped},
            "train_data": str(args.output / "train.json"),
            "val_data": str(args.output / "val.json"),
            "synthetic_test_data": str(args.output / "synthetic_test.json"),
            "cfr_classes": str(args.output / "cfr_classes.json"),
        })


if __name__ == "__main__":
    main()
