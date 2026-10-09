"""Score models on the held-out synthetic findings, by family and wording.

    python synthetic/score_synthetic_test.py synthetic_test.json name=predictions.json [name=predictions.json ...]

A predictions file is either the output of ``python -m fda_classifier.infer``
({"predictions": [{"record_id": "syn-<seed>-<wording>", ...}]}) or a list saved by
score_endpoint.py ([{"id": "<seed>|<wording>", ...}]). Several files may share one name.
"""
import json, sys
from collections import defaultdict

FAMILIES = {"s": "fuller", "n": "sparse", "k": "check-style"}
WORDINGS = {"k": ("observation", "observation_expected_actual", "narrative")}
DEFAULT_WORDINGS = ("short", "expected_actual", "narrative")

truth = {}
for record in json.load(open(sys.argv[1]))["records"]:
    _, seed, wording = record["record_id"].split("-", 2)
    truth[(seed, wording)] = record["observations"][0]

models = defaultdict(dict)
for argument in sys.argv[2:]:
    name, path = argument.split("=", 1)
    payload = json.load(open(path))
    for row in payload["predictions"] if isinstance(payload, dict) else payload:
        key = tuple(row["record_id"].split("-", 2)[1:]) if "record_id" in row else tuple(row["id"].split("|"))
        if key in truth:
            models[name][key] = row

pct = lambda hits, total: f"{100 * hits / total:5.1f}%" if total else "  n/a"
for name, predictions in models.items():
    missing = set(truth) - set(predictions)
    print(f"\n{name}: {len(predictions)} of {len(truth)} rows scored" + (f", {len(missing)} missing" if missing else ""))
    for prefix, family in FAMILIES.items():
        seeds = sorted({seed for seed, _ in truth if seed.startswith(prefix)})
        if not seeds:
            continue
        wordings = WORDINGS.get(prefix, DEFAULT_WORDINGS)
        print(f"  {family} findings: {len(seeds)}")
        for wording in wordings:
            keys = [(seed, wording) for seed in seeds if (seed, wording) in predictions]
            right = lambda field: sum(predictions[key][field] == truth[key][field] for key in keys)
            print(f"    {wording:<28s} severity {pct(right('severity'), len(keys))}  risk category {pct(right('primary_risk_tier'), len(keys))}  "
                  f"cfr {pct(right('cfr_reference'), len(keys))}")
        complete = [seed for seed in seeds if all((seed, wording) in predictions for wording in wordings)]
        flips = sum(len({predictions[(seed, wording)]["severity"] for wording in wordings}) > 1 for seed in complete)
        all_right = sum(all(predictions[(seed, wording)]["severity"] == truth[(seed, wording)]["severity"] for wording in wordings) for seed in complete)
        print(f"    severity changes with the wording on {pct(flips, len(complete))} of findings; right in all three wordings on {pct(all_right, len(complete))}")
        for level in ("Minor", "Major", "Critical"):
            keys = [key for key in predictions if key[0].startswith(prefix) and truth[key]["severity"] == level]
            print(f"    true {level:<8s} rows {len(keys):4d}  severity right {pct(sum(predictions[key]['severity'] == level for key in keys), len(keys))}")
