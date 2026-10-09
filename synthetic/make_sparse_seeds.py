"""Sample facts for sparse findings: notes that say only what a field or page of the record shows.

Real review findings are mostly like this: one sentence about one place in the record, located by
step or page number, with no measured values, no word on whether anyone noticed, and often a vague
count. Severity is never mentioned here or to the writers.

    python synthetic/make_sparse_seeds.py --count 800 --seed 31 --output data/fda_synthetic/sparse/seeds.json
"""
import argparse, json, random
from pathlib import Path
from make_seeds import COMMON_AREAS, PRODUCTS, pick

LAPSES = [
    ("performed-by initials or signature not present", 9),
    ("verified-by or checked-by signature not present", 8),
    ("date of an entry not present", 6),
    ("time of an entry not present, or start or end time not recorded", 6),
    ("a field left blank", 8),
    ("unused field or section left blank without a strike-through or N/A", 5),
    ("correction not initialled, dated or explained", 7),
    ("entry overwritten or written over an earlier entry", 4),
    ("entry cannot be read", 4),
    ("a date or time that is wrong or out of order (wrong year, a time earlier than the step before it)", 5),
    ("the same value recorded differently in two places of the record", 5),
    ("units missing from a recorded value", 3),
    ("page number missing or out of sequence", 3),
    ("a referenced attachment or printout not in the record", 5),
    ("equipment identification field not filled in", 4),
    ("lot number field blank, or the lot differs from another page", 5),
    ("calculation not shown, or the result differs when recalculated", 4),
    ("checkbox or yes/no question on a checklist not answered", 4),
    ("signature present with no printed name or not matching the signature log", 2),
    ("document number, version or effective date missing from a page or form", 3),
    ("entry made in pencil, with correction fluid, or with ditto marks or arrows", 3),
    ("recorded value outside the range printed on the form", 4),
    ("approval or review block unsigned (master document, review checklist, or deviation form)", 4),
    ("entries for different signers appear in the same handwriting, or identical values repeated down a column", 2),
    ("sample quantity, count or label count entry missing or not adding up", 3),
]
BUNDLE = [(1, 75), (2, 17), (3, 8)]
LOCATION = [("identify the place only by step number, page, table or section title; do not say what the step does", 60), ("name what the step is", 40)]
COUNT = [
    ("one entry", 45),
    ("an exact count of two to four entries", 15),
    ("say 'several' or 'multiple' and give one or two example locations, with no total", 25),
    ("say it occurs throughout the section or on most pages, with no total", 10),
    ("an exact count above five", 5),
]
NUMBERS = [("no measured values and no limits; only page, step, table or field references", 85), ("give the recorded value but no limit", 8), ("give the recorded value and its limit", 7)]
CERTAINTY = [("state it plainly", 88), ("the reviewer could not tell whether the entry is absent or only unreadable in the copy reviewed; say so", 12)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--prefix", default="n")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    seeds = []
    for index in range(args.count):
        product, establishments, areas = rng.choice(PRODUCTS)
        lapses = []
        while len(lapses) < pick(rng, BUNDLE) and len(lapses) < 3:
            lapse = pick(rng, LAPSES)
            if lapse not in lapses:
                lapses.append(lapse)
        seeds.append({
            "seed_id": f"{args.prefix}{index:04d}",
            "establishment_type": rng.choice(establishments),
            "facts": {
                "product": product,
                "record_area": rng.choice(COMMON_AREAS + areas * 2),
                "lapses": lapses,
                "location": pick(rng, LOCATION),
                "count": pick(rng, COUNT),
                "numbers": pick(rng, NUMBERS),
                "certainty": pick(rng, CERTAINTY),
            },
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seeds, indent=1) + "\n", encoding="utf-8")
    print(f"{len(seeds)} seeds in {args.output}")


if __name__ == "__main__":
    main()
