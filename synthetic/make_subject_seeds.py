"""Sample facts for check-style findings where what the entries are about is part of the facts.

make_check_seeds.py samples the kind of check and leaves its subject to the writer, so most
findings read as gaps in a record and few are about components, a step done differently from its
instruction, or deviations and review. Here each seed also says what the entries concern. The
subjects are the rows of the "Risk category and CFR section" table in
labeling/batch_record_rubric.md; the checks and their defect forms are those of
make_check_seeds.py. Severity, category and section are never mentioned here or to the writers.

    python synthetic/make_subject_seeds.py --count 800 --seed 307 --prefix u --output data/fda_synthetic/subjects/seeds.json
"""
import argparse, json, random
from pathlib import Path
from make_check_seeds import AFTERWARDS, CHECKS, EXTENT, FORMS, PROCESSES, SECOND_CHECK, STEP, VALUES
from make_seeds import pick

PRODUCTION = "executed batch production record"
MASTER = "master production record"
LAB = "analytical record of in-process or release tests"
SUBJECTS = [
    # what the entries concern, single documents, document pairs, checks that fit, weight
    ("the components charged to the batch: their names, lot or reference numbers, weighed and added quantities, and released status",
     [PRODUCTION, "weighing and dispensing record"],
     [(PRODUCTION, "weighing and dispensing record")],
     ["identifiers", "quantities", "restated values", "repeated rows", "signatures", "step against instruction", "referenced attachments", "entry integrity"], 22),
    ("the containers, closures or packaging materials used: their lot numbers, quantities and released status",
     [PRODUCTION],
     [(PRODUCTION, "dispensing record for the containers, closures or packaging materials")],
     ["identifiers", "quantities", "repeated rows", "referenced attachments"], 4),
    ("what was done at a step compared with what the instruction for that step says: the equipment, material, quantity, order, condition or frequency instructed",
     [PRODUCTION, "monitoring log"],
     [(PRODUCTION, MASTER), (PRODUCTION, "separate process parameter sheet")],
     ["instruction followed", "step against instruction", "identifiers", "reading logs", "times and durations", "restated values", "repeated rows"], 24),
    ("deviations and the review of the batch record: whether a departure was raised, recorded, assessed and closed, and whether the review was completed",
     ["batch record review checklist", "deviation log or deviation form", "discrepancy or incident note"],
     [(PRODUCTION, "deviation log or deviation form"), ("batch record review checklist", PRODUCTION)],
     ["deviation handling", "repeated rows", "signatures", "referenced attachments", "limits", "identifiers", "dates", "step against instruction"], 20),
    ("process parameters, in-process results or hold times that have a stated limit",
     ["process parameter sheet", PRODUCTION],
     [(PRODUCTION, "analytical record of in-process tests")],
     ["limits", "reading logs", "times and durations", "restated values"], 5),
    ("the yield of a stage or of the batch and the quantities it is computed from",
     [PRODUCTION],
     [("batch summary or report cover", PRODUCTION)],
     ["quantities", "restated values", "limits"], 2),
    ("release or in-process tests done in the laboratory: results, raw data, calculations and the analyst's and reviewer's entries",
     [LAB, "instrument sample set or sequence printout"],
     [("certificate of analysis", "analytical record of release tests"), ("certificate of analysis", "product specification"), ("instrument sample set or sequence printout", "sample request sheets and analytical reports")],
     ["limits", "restated values", "identifiers", "signatures", "referenced attachments", "entry integrity", "dates"], 7),
    ("labels and packaging: label issue, printing checks, reconciliation and the packaging operation",
     ["label issue and reconciliation record", PRODUCTION],
     [(PRODUCTION, "label issue and reconciliation record")],
     ["quantities", "identifiers", "signatures", "repeated rows"], 3),
    ("line clearance of a manufacturing area or of equipment before the operation",
     ["line clearance checklist", PRODUCTION],
     [(PRODUCTION, "line clearance checklist")],
     ["repeated rows", "signatures", "dates", "times and durations"], 3),
    ("the cleaning status, calibration or use of equipment",
     ["equipment cleaning and use log", "calibration record"],
     [(PRODUCTION, "equipment cleaning and use log")],
     ["identifiers", "dates", "signatures", "repeated rows", "times and durations", "referenced attachments"], 5),
    ("the temperature, humidity or pressure difference of a room",
     ["monitoring log"],
     [(PRODUCTION, "monitoring log")],
     ["reading logs", "limits", "repeated rows"], 2),
    ("electronic records: audit trail, user access and system-generated entries",
     ["audit trail printout", "instrument sample set or sequence printout"],
     [("audit trail printout", LAB)],
     ["entry integrity", "identifiers", "dates", "signatures", "referenced attachments"], 3),
]
EXTRA_CHECKS = [
    # two rows of the rubric table have no check of their own in make_check_seeds.py; same shape as CHECKS
    ("instruction followed", "what the instruction for a step tells the operator to do or use against what the record shows was done or used",
     ["a step the instruction requires has no entries", "the equipment recorded is not the equipment the instruction names", "the material or portion recorded is not the one the instruction names",
      "steps recorded in a different order than instructed", "sampling or monitoring not done at the instructed frequency", "a conditional step carries entries although its condition was not met"], None, 30),
    ("deviation handling", "each departure, out-of-limit entry or discrepancy note in the package against the deviation records and the review of the batch record",
     ["a departure or out-of-limit entry with no deviation raised for it", "a deviation or discrepancy note not entered in the deviation log or not referenced in the batch record", "a deviation still open when the record was reviewed",
      "a deviation closed with no cause or assessment recorded", "the review of the batch record not completed"], None, 30),
]
BY_NAME = {check[0]: check for check in CHECKS + EXTRA_CHECKS}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--prefix", default="u")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    seeds = []
    for index in range(args.count):
        process, establishments, _ = pick(rng, [(row, row[2]) for row in PROCESSES])
        subject, singles, pairs, fitting, _ = pick(rng, [(row, row[4]) for row in SUBJECTS])
        weighted = [(BY_NAME[name], BY_NAME[name][4]) for name in fitting]
        checks = [pick(rng, weighted)]
        if pick(rng, SECOND_CHECK):
            other = pick(rng, weighted)
            if other[0] != checks[0][0]:
                checks.append(other)
        cross = any(check[3] or (check[3] is None and rng.random() < 0.5) for check in checks)
        facts = {
            "process": process,
            "subject": subject,
            "documents": list(rng.choice(pairs)) if cross else [rng.choice(singles)],
            "checks": [{"check": name, "compares": compares, "defect_forms": rng.sample(forms, min(pick(rng, FORMS), len(forms)))} for name, compares, forms, _, _ in checks],
            "extent": pick(rng, EXTENT),
            "values": pick(rng, VALUES),
            "step": pick(rng, STEP),
            "afterwards": pick(rng, AFTERWARDS),
        }
        seeds.append({"seed_id": f"{args.prefix}{index:04d}", "establishment_type": rng.choice(establishments), "facts": facts})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seeds, indent=1) + "\n", encoding="utf-8")
    print(f"{len(seeds)} seeds in {args.output}")


if __name__ == "__main__":
    main()
