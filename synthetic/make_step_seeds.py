"""Sample facts for check-style findings where the kind of step is part of the facts.

make_check_seeds.py leaves the step to the writer, so few findings name the steps the rubric
treats as critical. Here each seed says which kind of step the entries belong to, for two checks:
signatures, and whether the record is consistent with itself. The step kinds are the rubric's own
list of critical steps plus steps it does not treat as critical. The facts have the same shape as
make_check_seeds.py, so check_writer_instructions.md applies unchanged. Severity is never
mentioned here or to the writers.

    python synthetic/make_step_seeds.py --count 500 --seed 211 --prefix t --output data/fda_synthetic/steps/seeds.json
"""
import argparse, json, random
from pathlib import Path
from make_check_seeds import AFTERWARDS, EXTENT, PROCESSES, VALUES
from make_seeds import pick

STERILE = "sterile injectable or ophthalmic product"
NAMED = [
    # step, document it is recorded on, sterile products only
    ("weighing of a component", "weighing and dispensing table", False),
    ("addition of a component to the batch", "executed batch production record", False),
    ("an in-process test that has a stated limit", "analytical record of in-process or release tests", False),
    ("a process parameter that has a stated limit", "process parameter sheet", False),
    ("fill volume or fill weight adjustment", "executed batch production record", False),
    ("line clearance before the operation", "executed batch production record", False),
    ("yield calculation", "executed batch production record", False),
    ("issue, printing check or reconciliation of the labels that go on the product", "executed batch production record", False),
    ("a release test in the laboratory", "analytical record of in-process or release tests", False),
    ("approval of the master record", "approval block of a master or executed record", False),
    ("quality unit review and approval of the executed record", "approval block of a master or executed record", False),
    ("a sterilisation cycle", "executed batch production record", True),
    ("sterile filtration and the filter integrity test", "executed batch production record", True),
    ("depyrogenation of containers", "executed batch production record", True),
    ("aseptic filling", "executed batch production record", True),
]
OTHER = [
    ("cleaning of a room or surface where product is in closed containers", "equipment cleaning and use log"),
    ("an item on a review checklist", "review checklist"),
    ("the signature block of a deviation form", "executed batch production record"),
    ("transfer of closed containers between rooms", "executed batch production record"),
    ("a trolley, tray or status tag entry", "executed batch production record"),
    ("storage of retained samples", "sample register"),
    ("a test done for stability or trending only", "analytical record of in-process or release tests"),
    ("packing into shipper cases", "executed batch production record"),
]
STEP_KIND = [("named", 55), ("other", 25), ("numbered", 20)]
CHECKS = [
    ("signatures", "performer, verifier, review and approval fields of each executed step and each approval block",
     ["performer signature missing", "verifier signature missing", "one person signed as both performer and verifier", "approval or review block blank", "entries made under a login shared by several people", "signature present with no date"], 68),
    ("record consistent with itself", "entries, signatures, dates and results against the rest of the same package",
     ["entries recorded for work that other entries in the package show was not done", "signed by a person the package shows was not present", "entries of different signers written in one hand", "identical results repeated across samples or time points", "a value changed to fall inside its limit with the first entry or its raw data removed",
      "entries dated as made at the time although the package shows they were written later", "a result recorded before the step or test took place", "a review signed before the results it covers existed", "a test present in the instrument log with no reported result and no explanation",
      "a copied value that differs from the attached raw data"], 32),
]
FORMS = [(1, 60), (2, 40)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--prefix", default="t")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    seeds = []
    for index in range(args.count):
        process, establishments, _ = pick(rng, [(row, row[2]) for row in PROCESSES])
        name, compares, forms, _ = pick(rng, [(check, check[3]) for check in CHECKS])
        kind = pick(rng, STEP_KIND)
        if kind == "named":
            step, document, _ = rng.choice([row for row in NAMED if process == STERILE or not row[2]])
        else:
            step, document = rng.choice(OTHER)
        facts = {
            "process": process,
            "documents": [document],
            "checks": [{"check": name, "compares": compares, "defect_forms": rng.sample(forms, pick(rng, FORMS))}],
            "extent": pick(rng, EXTENT),
            "values": pick(rng, VALUES),
            "step": "identify steps only by operation, step, table or page number" if kind == "numbered" else f"name what the step is: {step}",
            "afterwards": pick(rng, AFTERWARDS),
        }
        seeds.append({"seed_id": f"{args.prefix}{index:04d}", "establishment_type": rng.choice(establishments), "facts": facts})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seeds, indent=1) + "\n", encoding="utf-8")
    print(f"{len(seeds)} seeds in {args.output}")


if __name__ == "__main__":
    main()
