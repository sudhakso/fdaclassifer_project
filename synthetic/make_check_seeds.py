"""Sample facts for findings shaped like the output of a rule-based batch record review.

Such a review applies one check to one record and reports every entry that fails it in a single
finding, so a finding often lists several places and several forms of the same defect, cites
documents and pages, and says nothing about what happened afterwards. The check kinds below are
the general kinds of condition such a review tests. Severity is never mentioned here or to the
writers.

    python synthetic/make_check_seeds.py --count 1500 --seed 97 --prefix k --output data/fda_synthetic/checks/seeds.json
"""
import argparse, json, random
from pathlib import Path
from make_seeds import pick

PROCESSES = [
    # description, establishment types, weight
    ("active pharmaceutical ingredient by chemical synthesis: reaction, quench, extraction, distillation, crystallisation, centrifuging, drying, milling", ["API Manufacturer"], 30),
    ("pharmaceutical intermediate: reaction, work-up, isolation, drying", ["API Manufacturer", "Manufacturer"], 10),
    ("film-coated tablets or hard capsules", ["Drug Manufacturer", "Drug Product Manufacturer", "Human Drug Manufacturer"], 22),
    ("oral liquid, cream, gel or ointment", ["Drug Manufacturer", "Manufacturer"], 14),
    ("sterile injectable or ophthalmic product", ["Sterile Drug Manufacturer", "Producer of Sterile Drug Products"], 16),
    ("contract manufacture of a product for another company", ["Manufacturer", "Pharmaceutical Manufacturer"], 8),
]
SINGLE = ["executed batch production record", "process parameter sheet", "monitoring log", "weighing and dispensing table", "sample register", "review checklist", "equipment cleaning and use log", "analytical record of in-process or release tests", "approval block of a master or executed record"]
CROSS = [
    ("executed batch production record", "analytical record of in-process tests"),
    ("executed batch production record", "in-process sample request or requisition sheets"),
    ("certificate of analysis", "analytical record of release tests"),
    ("certificate of analysis", "product specification"),
    ("executed batch production record", "separate process parameter sheet"),
    ("instrument sample set or sequence printout", "sample request sheets and analytical reports"),
    ("executed batch production record", "weighing and dispensing record"),
    ("batch summary or report cover", "executed batch production record"),
]
CHECKS = [
    # name, what the check compares, forms the defect can take, cross-document, weight
    ("limits", "a recorded result or reading against the limit, range or specification stated for it",
     ["result outside its limit", "result recorded without units", "result field blank", "no limit stated on the record for the result"], False, 9),
    ("restated values", "a value restated in a summary document against the source record",
     ["the two documents show different values", "value present in one document and absent from the other", "units or rounding differ"], True, 7),
    ("step against instruction", "the quantity, temperature, duration or condition a step instructs against what was recorded, remarks included",
     ["recorded value differs from the instructed one", "recorded value outside the instructed range", "value not recorded", "a conditional step carries entries although its condition was not met", "an instructed step has no entries"], False, 10),
    ("times and durations", "start time, end time and stated duration of steps, and the order of steps in time",
     ["stated duration does not equal end minus start", "end time earlier than start time", "a step overlaps another step on the same equipment", "a time falls outside the batch period"], False, 8),
    ("reading logs", "periodic readings: each in range, taken at the stated frequency, covering the stated period",
     ["reading outside its range", "gap longer than the stated frequency", "readings stop before the end of the period", "readings carry no verification sign-off"], False, 7),
    ("identifiers", "lot, batch, sample, requisition, document version and page numbers kept consistent across the package",
     ["a number differs between two places", "a number is missing in one place", "a typing variant of the same number", "page numbering missing or out of sequence", "a code of the wrong kind entered in the field"], None, 10),
    ("dates", "dates valid, in sequence and inside the operation period",
     ["wrong year", "date earlier than the preceding step", "date after batch completion", "date malformed or incomplete"], False, 8),
    ("signatures", "performer, verifier, review and approval fields of each executed step and each approval block",
     ["performer signature missing", "verifier signature missing", "signature present with no date", "date beside the signature malformed", "one person signed as both performer and verifier", "approval block blank"], False, 13),
    ("quantities", "issued, used, returned and produced quantities and the yield recomputed from them",
     ["recomputed figure differs from the recorded one", "a quantity not recorded", "yield outside its stated range", "reconciliation does not balance"], False, 7),
    ("referenced attachments", "tests, reports or attachments a record refers to, present in the package or not",
     ["referenced report not in the package", "attachment belongs to a different sample or batch", "result entered with no request or report behind it"], True, 7),
    ("repeated rows", "each used row of a table, register, checklist or log complete, in range and in sequence",
     ["cells blank in used rows", "unused rows not struck through or marked not applicable", "checklist item not answered", "contradictory selections on a checklist", "a row out of sequence"], False, 9),
    ("entry integrity", "how entries and corrections are made",
     ["overwritten or obscured entry", "correction without initials, date or reason", "value changed with no explanation", "entry illegible", "identical values repeated down a column"], False, 5),
]
FORMS = [(1, 45), (2, 38), (3, 17)]
EXTENT = [
    ("one entry", 22),
    ("two to four entries; name each place", 30),
    ("six to twelve entries; list the places", 16),
    ("many entries; say 'multiple' and name two or three examples, with no total", 18),
    ("every entry of the table, section or document", 14),
]
VALUES = [("quote the values exactly as written on the record", 45), ("quote one or two values that are malformed as written, as a scan would show them", 12), ("no values; only document, page, step, table and field references", 43)]
AFTERWARDS = [("say nothing about deviations, investigations, review or release", 82), ("state that no deviation, remark or explanation is recorded for it", 12), ("state that a deviation or remark is recorded against it", 6)]
SECOND_CHECK = [(False, 80), (True, 20)]
STEP = [("name what the step or test is", 55), ("identify steps only by operation, step, table or page number", 45)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--prefix", default="c")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    weighted = [(check, check[4]) for check in CHECKS]
    seeds = []
    for index in range(args.count):
        process, establishments, _ = pick(rng, [(row, row[2]) for row in PROCESSES])
        checks = [pick(rng, weighted)]
        if pick(rng, SECOND_CHECK):
            other = pick(rng, weighted)
            if other[0] != checks[0][0]:
                checks.append(other)
        cross = any(check[3] or (check[3] is None and rng.random() < 0.5) for check in checks)
        facts = {
            "process": process,
            "documents": list(rng.choice(CROSS)) if cross else [rng.choice(SINGLE)],
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
