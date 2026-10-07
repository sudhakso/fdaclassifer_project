"""Compare two blind relabelling passes with each other and with the existing labels.

Reads the key written by build_reference_sample.py and the per-batch label files
(pass1_batch*.json, pass2_batch*.json). Rejects anything outside the closed label
lists, then reports agreement between the passes, and of each pass with the
flash-lite and Gemini-pro labels.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

SEVERITIES = ("critical", "major", "minor")
CATEGORY_TIER = {
    "contamination and mix-ups": "tier 1",
    "quality control failure": "tier 1",
    "critical process parameter deviation": "tier 2",
    "process not followed": "tier 2",
    "personnel hygiene": "tier 3",
    "equipment and environment hygiene": "tier 3",
    "document control and traceability": "tier 4",
    "inadequate investigation and capa": "tier 4",
    "labeling and packaging": "additional",
    "stability and storage": "additional",
    "supplier and raw material quality": "additional",
    "electronic data integrity": "additional",
}
_SECTION = re.compile(r"\d{2,4}\.\d+")


def section(value: object) -> str | None:
    match = _SECTION.search(value) if isinstance(value, str) else None
    return match.group(0) if match else None


def coarse_tier(value: object) -> str | None:
    text = value.lower() if isinstance(value, str) else ""
    match = re.search(r"tier\s*(\d)", text)
    if match:
        return f"tier {match.group(1)}"
    return "additional" if "additional" in text else None


def load_pass(labels_dir: Path, number: int, expected_ids: set[str]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in sorted(labels_dir.glob(f"pass{number}_batch*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            severity = str(row.get("severity", "")).lower()
            category = str(row.get("risk_category", "")).lower()
            if severity not in SEVERITIES or category not in CATEGORY_TIER:
                raise SystemExit(f"{path.name} {row.get('id')}: label outside the closed lists: {severity!r} / {category!r}")
            rows[row["id"]] = {**row, "severity": severity, "risk_category": category, "cfr_section": section(row.get("cfr_section"))}
    if set(rows) != expected_ids:
        raise SystemExit(f"pass {number}: {len(expected_ids - set(rows))} ids missing, {len(set(rows) - expected_ids)} unexpected")
    return rows


def share(pairs: list[tuple[object, object]]) -> str:
    usable = [(a, b) for a, b in pairs if a is not None and b is not None]
    if not usable:
        return "n/a"
    return f"{sum(a == b for a, b in usable) / len(usable):.1%} (n={len(usable)})"


def confusion(pairs: list[tuple[str, str]], row_name: str, column_name: str) -> None:
    counts = Counter(pairs)
    print(f"   rows={row_name}, cols={column_name}".ljust(34) + "".join(f"{label:>10s}" for label in SEVERITIES))
    for a in SEVERITIES:
        print(f"   {a:>30s} " + "".join(f"{counts[(a, b)]:10d}" for b in SEVERITIES))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--labels-dir", required=True, type=Path)
    args = parser.parse_args()

    key = {row["id"]: row for row in json.loads(args.key.read_text(encoding="utf-8"))}
    first = load_pass(args.labels_dir, 1, set(key))
    second = load_pass(args.labels_dir, 2, set(key))
    ids = sorted(key)
    print(f"rows={len(ids)} | severity counts: pass1={dict(Counter(first[i]['severity'] for i in ids))} pass2={dict(Counter(second[i]['severity'] for i in ids))}")
    print(f"   flash-lite={dict(Counter(key[i]['flash']['severity'] for i in ids))} pro={dict(Counter(key[i]['pro']['severity'] for i in ids))}")

    print("\nSELF-CONSISTENCY (pass 1 vs pass 2, same rubric, independent runs)")
    print("   severity:", share([(first[i]["severity"], second[i]["severity"]) for i in ids]))
    print("   category:", share([(first[i]["risk_category"], second[i]["risk_category"]) for i in ids]))
    print("   tier:    ", share([(CATEGORY_TIER[first[i]["risk_category"]], CATEGORY_TIER[second[i]["risk_category"]]) for i in ids]))
    print("   cfr section:", share([(first[i]["cfr_section"], second[i]["cfr_section"]) for i in ids]))
    confusion([(first[i]["severity"], second[i]["severity"]) for i in ids], "pass 1", "pass 2")
    flips = [i for i in ids if first[i]["severity"] != second[i]["severity"]]
    flagged = [i for i in ids if first[i].get("borderline") or second[i].get("borderline")]
    print(f"   severity flips: {len(flips)} | of those flagged borderline by either pass: {sum(i in flagged for i in flips)} | rows flagged borderline: {len(flagged)}")
    print("   rules cited on flipped rows:", Counter(f"{first[i].get('rule')}/{second[i].get('rule')}" for i in flips).most_common(8))
    print("   rules cited overall (pass 1):", Counter(first[i].get("rule") for i in ids).most_common())

    for name, labels in (("pass 1", first), ("pass 2", second)):
        print(f"\n{name.upper()} vs EXISTING LABELS")
        print("   severity vs flash-lite:", share([(labels[i]["severity"], key[i]["flash"]["severity"]) for i in ids]))
        print("   severity vs pro:       ", share([(labels[i]["severity"], key[i]["pro"]["severity"]) for i in ids]))
        print("   category vs flash-lite:", share([(labels[i]["risk_category"], key[i]["flash"]["risk_category"]) for i in ids]))
        print("   tier vs pro:           ", share([(CATEGORY_TIER[labels[i]["risk_category"]], coarse_tier(key[i]["pro"]["primary_risk_tier"])) for i in ids]))
        print("   cfr section vs flash-lite:", share([(labels[i]["cfr_section"], section(key[i]["flash"]["cfr_reference"])) for i in ids]),
              "| vs pro:", share([(labels[i]["cfr_section"], section(key[i]["pro"]["cfr_reference"])) for i in ids]))
    print("\n   reference on this sample: flash-lite vs pro severity:", share([(key[i]["flash"]["severity"], key[i]["pro"]["severity"]) for i in ids]),
          "| category-tier:", share([(CATEGORY_TIER.get(key[i]["flash"]["risk_category"]), coarse_tier(key[i]["pro"]["primary_risk_tier"])) for i in ids]))

    stable = [i for i in ids if first[i]["severity"] == second[i]["severity"]]
    print(f"\nWHERE BOTH PASSES AGREE ON SEVERITY ({len(stable)} rows)")
    confusion([(first[i]["severity"], key[i]["flash"]["severity"]) for i in stable], "new label", "flash-lite")
    confusion([(first[i]["severity"], key[i]["pro"]["severity"]) for i in stable], "new label", "pro")
    disputed = [i for i in stable if not key[i]["labellers_agree_on_severity"]]
    sides = Counter(
        "flash-lite" if first[i]["severity"] == key[i]["flash"]["severity"] else "pro" if first[i]["severity"] == key[i]["pro"]["severity"] else "neither"
        for i in disputed
    )
    print(f"   on the {len(disputed)} rows where flash-lite and pro disagree, the new label sides with: {dict(sides)}")
    settled = [i for i in stable if key[i]["labellers_agree_on_severity"]]
    print(f"   on the {len(settled)} rows where flash-lite and pro agree, the new label matches them: {sum(first[i]['severity'] == key[i]['flash']['severity'] for i in settled)}")
    three_way = [i for i in ids if len({first[i]["severity"], key[i]["flash"]["severity"], key[i]["pro"]["severity"]}) == 3]
    print(f"\nrows where the new label, flash-lite and pro are all different: {three_way}")
    print("severity flips between passes:", flips)


if __name__ == "__main__":
    main()
