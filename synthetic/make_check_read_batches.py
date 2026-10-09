"""Blind batches of check-style findings for two independent readers.

Reader a sees the observation followed by its Expected and Actual parts, reader b the observation alone.

    python synthetic/make_check_read_batches.py <dir with findings_*.json> <rows per batch> <id seed>
"""
import glob, json, random, sys
from pathlib import Path

out, size, seed = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
STYLES = {
    "a": ("observation_expected_actual", lambda w: f"{w['observation']} Expected: {w['expected']} Actual: {w['actual']}"),
    "b": ("observation", lambda w: w["observation"]),
}
findings = [f for path in sorted(glob.glob(str(out / "findings_*.json"))) for f in json.load(open(path))]
assert len({f["seed_id"] for f in findings}) == len(findings), "duplicate seed ids"
rng = random.Random(seed)
ids = rng.sample(range(100000, 999999), len(findings) * 2)
key = {}
(out / "blind").mkdir(parents=True, exist_ok=True); (out / "labels").mkdir(exist_ok=True)
for name, (style, text) in STYLES.items():
    rows = []
    for f in findings:
        row_id = f"r{ids.pop()}"
        key[row_id] = {"seed_id": f["seed_id"], "style": style, "pass": name}
        rows.append({"id": row_id, "establishment_type": f["establishment_type"], "full_details": text(f["wordings"])})
    rng.shuffle(rows)
    for index in range(0, len(rows), size):
        (out / "blind" / f"{name}_{index // size + 1:02d}.json").write_text(json.dumps(rows[index:index + size], indent=1) + "\n")
(out / "key.json").write_text(json.dumps(key) + "\n")
print(len(findings), "findings,", len(key), "rows,", len(list((out / "blind").glob("*.json"))), "batches in", out / "blind")
