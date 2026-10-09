"""Blind batches for two independent readers: reader a sees the expected_actual wording, reader b the short one.

    python synthetic/make_read_batches.py <dir with findings_*.json> <output dir> <rows per batch> <id seed>
"""
import glob, json, random, sys
from pathlib import Path

source, out, size, seed = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
findings = [f for path in sorted(glob.glob(str(source / "findings_*.json"))) for f in json.load(open(path))]
assert len({f["seed_id"] for f in findings}) == len(findings), "duplicate seed ids"
rng = random.Random(seed)
ids = rng.sample(range(100000, 999999), len(findings) * 2)
key = {}
(out / "blind").mkdir(parents=True, exist_ok=True); (out / "labels").mkdir(exist_ok=True)
for name, style in (("a", "expected_actual"), ("b", "short")):
    rows = []
    for f in findings:
        row_id = f"r{ids.pop()}"
        key[row_id] = {"seed_id": f["seed_id"], "style": style, "pass": name}
        rows.append({"id": row_id, "establishment_type": f["establishment_type"], "full_details": f["wordings"][style]})
    rng.shuffle(rows)
    for index in range(0, len(rows), size):
        (out / "blind" / f"{name}_{index // size + 1:02d}.json").write_text(json.dumps(rows[index:index + size], indent=1) + "\n")
(out / "key.json").write_text(json.dumps(key) + "\n")
print(len(findings), "findings,", len(key), "rows,", len(list((out / "blind").glob("*.json"))), "batches in", out / "blind")
