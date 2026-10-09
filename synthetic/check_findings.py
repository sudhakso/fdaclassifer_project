"""Check writer output: every seed present, three wordings, length ranges, no grading words, silence respected."""
import json, re, sys
seeds_path, findings_path = sys.argv[1:3]
seeds = {s["seed_id"]: s for s in json.load(open(seeds_path))}
findings = json.load(open(findings_path))
GRADING = re.compile(r"\b(minor|major|critical(?!-| zone| step| process| parameter)|serious|significant|severe|concern|risk|violation)\b", re.I)
LIMITS = {"short": (10, 40), "expected_actual": (36, 88), "narrative": (36, 98)}
problems, lengths = [], {k: [] for k in LIMITS}
seen = set()
for f in findings:
    sid = f.get("seed_id"); seen.add(sid)
    if sid not in seeds: problems.append(f"{sid}: unknown seed"); continue
    w = f.get("wordings", {})
    for style, (lo, hi) in LIMITS.items():
        text = w.get(style, "")
        n = len(text.split()); lengths[style].append(n)
        if not lo <= n <= hi: problems.append(f"{sid} {style}: {n} words")
        if GRADING.search(text): problems.append(f"{sid} {style}: grading word '{GRADING.search(text).group(0)}'")
    if "Expected:" not in w.get("expected_actual", "") or "Actual:" not in w.get("expected_actual", ""):
        problems.append(f"{sid}: expected_actual lacks its two parts")
    facts = seeds[sid]["facts"]
    joined = " ".join(w.values()).lower()
    if facts["batch_status"].startswith("say nothing") and re.search(r"batch (was|is|has been) released|released (batch|for)|quality unit approv|under review|qa approv", joined):
        problems.append(f"{sid}: mentions batch status although the seed says nothing")
    if facts["handling"].startswith("say nothing") and re.search(r"\bdeviation\b", joined) and "deviation" not in facts["issue"] and "deviation" not in facts["record_area"]:
        problems.append(f"{sid}: mentions a deviation although the seed says nothing about handling")
missing = sorted(set(seeds) - seen)
print(f"{len(findings)} findings, {len(missing)} seeds missing, {len(problems)} problems")
for style, values in lengths.items():
    if values: print(f"  {style}: words min {min(values)} median {sorted(values)[len(values)//2]} max {max(values)}")
for p in problems[:25]: print("  -", p)
texts = [w for f in findings for w in f.get("wordings", {}).values()]
openers = [" ".join(t.split()[:3]).lower() for t in texts]
from collections import Counter
print("  most common openings:", Counter(openers).most_common(4))
