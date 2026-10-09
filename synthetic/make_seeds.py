"""Sample the facts for synthetic batch record findings. Severity is never mentioned here or to the writers.

    python synthetic/make_seeds.py --count 300 --seed 7 --output data/fda_synthetic/trial/seeds.json
"""
import argparse, json, random
from pathlib import Path

COMMON_AREAS = [
    "dispensing and weighing of components", "equipment set-up and line clearance", "in-process controls",
    "yield calculation and reconciliation", "packaging and labelling", "equipment cleaning and use log",
    "quality control results attached to the record", "hold or storage between steps",
    "deviation references in the record", "final review pages of the record",
]
PRODUCTS = [
    # description, establishment types to use for the classifier input, extra record areas
    ("film-coated tablets", ["Drug Manufacturer", "Pharmaceutical Manufacturer", "Human Drug Manufacturer"], ["granulation and drying", "blending", "compression", "coating"]),
    ("hard capsules", ["Drug Manufacturer", "Drug Product Manufacturer"], ["blending", "capsule filling", "polishing and sorting"]),
    ("oral liquid or suspension", ["Drug Manufacturer", "Manufacturer"], ["compounding and mixing", "bulk filtration", "bottle filling"]),
    ("topical cream, gel or ointment", ["Drug Manufacturer", "Manufacturer"], ["phase preparation and mixing", "homogenisation", "tube or jar filling"]),
    ("sterile injectable solution, aseptically filled", ["Sterile Drug Manufacturer", "Producer of Sterile Drug Products"], ["solution compounding", "sterile filtration and filter integrity testing", "aseptic filling", "depyrogenation of containers", "environmental monitoring during filling", "visual inspection"]),
    ("sterile injectable, terminally sterilised", ["Sterile Drug Manufacturer", "Producer of Sterile Drug Products"], ["solution compounding", "filling and sealing", "autoclave cycle", "visual inspection"]),
    ("lyophilised sterile powder for injection", ["Sterile Drug Manufacturer"], ["solution compounding", "sterile filtration and filter integrity testing", "aseptic filling", "lyophilisation cycle", "stoppering and capping"]),
    ("sterile ophthalmic solution", ["Sterile Drug Manufacturer", "Producer of Sterile Drug Products"], ["solution compounding", "sterile filtration and filter integrity testing", "aseptic filling", "environmental monitoring during filling"]),
    ("active pharmaceutical ingredient made by chemical synthesis", ["API Manufacturer"], ["reaction step", "crystallisation and isolation", "drying", "milling and sieving", "solvent charging", "intermediate hold"]),
    ("over-the-counter liquid or semi-solid", ["Drug Manufacturer", "Manufacturer"], ["compounding and mixing", "bottle or tube filling"]),
]
ISSUES = [
    # description, weight, needs "effect" fact, sterile only
    ("performer signature or initials missing for a step", 7, False, False),
    ("second-person verification signature missing for a step", 6, False, False),
    ("date or time of an entry missing", 6, False, False),
    ("entry made after the step was performed", 4, False, False),
    ("correction made without initials, date or reason, original still readable", 6, False, False),
    ("original entry overwritten or obscured so it cannot be read", 3, False, False),
    ("a required value or result field left blank", 5, False, False),
    ("a required attachment (printout, chart, weigh ticket, chromatogram or label specimen) not in the record", 4, False, False),
    ("units of measure missing or an entry hard to read", 3, False, False),
    ("page missing or pages misnumbered", 2, False, False),
    ("superseded version of a form or record page used", 2, False, False),
    ("arithmetic error in a calculation", 5, True, False),
    ("value copied into the record does not match the attached raw data", 4, True, False),
    ("recorded process parameter outside the range stated in the record", 5, False, False),
    ("in-process test result outside its limit", 4, False, False),
    ("hold time or processing time limit exceeded", 3, False, False),
    ("yield or reconciliation figure outside its limits", 4, False, False),
    ("step performed out of the sequence the record requires", 3, False, False),
    ("no entry at all for a step", 3, False, False),
    ("material lot number not recorded or not matching the dispensing record", 4, False, False),
    ("component used past its expiry or retest date, or without released status", 2, False, False),
    ("wrong component, grade or quantity charged", 3, False, False),
    ("equipment identification not recorded", 3, False, False),
    ("equipment used with calibration overdue or cleaning status not verified", 3, False, False),
    ("entries that look pre-recorded, copied, or signed by someone the record shows was not present", 3, False, False),
    ("an out-of-limit event with no deviation report referenced", 3, False, False),
    ("deviation referenced in the record but still open or thinly assessed", 3, False, False),
    ("label count reconciliation does not balance", 2, False, False),
    ("release test result missing or failing in the attached quality control data", 3, False, False),
    ("sampling not done as the record requires", 3, False, False),
    ("a step done only partly or not the way the record instructs", 3, False, False),
    ("a review or check signed before the results it covers were available", 2, False, False),
    ("cleaning agent or disinfectant used past its expiry date", 2, False, False),
    ("electronic record issue (shared login, missing audit trail entry, reprocessed result)", 2, False, False),
    ("environmental monitoring result above its limit during the operation", 2, False, True),
    ("filter integrity test failed or not recorded", 2, False, True),
    ("sterilisation or depyrogenation cycle parameter not met or chart missing", 2, False, True),
]
STEP_KIND = [("a step that directly affects identity, strength, purity or sterility", 45), ("a supporting step with no direct bearing on the product", 55)]
EXTENT = [("one instance", 60), ("two or three instances in the same record", 25), ("repeated across many steps or pages", 15)]
EFFECT = [("the corrected figure is still within its limit", 45), ("the corrected figure is outside its limit", 25), ("the effect cannot be worked out from the record", 30)]
HANDLING = [("say nothing about whether anyone noticed", 55), ("corrected on the record later, no deviation raised", 10), ("a deviation is referenced with an assessment of the effect", 12), ("a deviation is referenced but it is still open", 8), ("the record shows no deviation was raised", 15)]
STATUS = [("say nothing about batch status", 60), ("the batch is still under review, not released", 20), ("the record carries quality unit approval, the batch was released", 20)]


def pick(rng, options):
    return rng.choices([option[0] for option in options], weights=[option[1] for option in options])[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--prefix", default="s")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    seeds = []
    for index in range(args.count):
        product, establishments, areas = rng.choice(PRODUCTS)
        sterile = "sterile" in product
        description, _, needs_effect, _ = rng.choices(
            [issue for issue in ISSUES if sterile or not issue[3]],
            weights=[issue[1] for issue in ISSUES if sterile or not issue[3]],
        )[0]
        facts = {
            "product": product,
            "record_area": rng.choice(COMMON_AREAS + areas * 2),
            "issue": description,
            "step_kind": pick(rng, STEP_KIND),
            "extent": pick(rng, EXTENT),
            "handling": pick(rng, HANDLING),
            "batch_status": pick(rng, STATUS),
        }
        if needs_effect:
            facts["effect"] = pick(rng, EFFECT)
        if "no deviation report referenced" in description:
            facts["handling"] = rng.choice(["say nothing about whether anyone noticed", "the record shows no deviation was raised"])
        if "deviation referenced in the record" in description:
            facts["handling"] = "a deviation is referenced but it is still open"
        if "release test result" in description:
            facts["step_kind"] = STEP_KIND[0][0]
        seeds.append({"seed_id": f"{args.prefix}{index:04d}", "establishment_type": rng.choice(establishments), "facts": facts})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seeds, indent=1) + "\n", encoding="utf-8")
    print(f"{len(seeds)} seeds in {args.output}")


if __name__ == "__main__":
    main()
