"""The three questions the decision model answers, with the labelling rubric as their criteria.

The text condenses labeling/severity_rubric.md (v2.1) and labeling/batch_record_rubric.md (v0.6).
Every row is asked the same questions, so the model learns to apply these criteria to the text.
"""

SEVERITY_INSTRUCTIONS = """How severe is this finding? Grade it from its own text. Ask what the worst credible consequence for a patient is if the failure went uncorrected, and whether a later control would catch it first. Do not assume harm, intent, handling or batch status that the text does not state. When several lapses appear, grade by the most severe.

Site inspection observations:
- Critical: sterile product, containers or product-contact surfaces exposed to a contamination source in the ISO 5 zone; validation of sterilisation, depyrogenation, sterile filtration or the aseptic process absent, failed or unrepresentative; product released with no valid test for sterility, endotoxin, identity or strength, or with a known failing result; results falsified, deleted, backdated or retested into compliance; no investigation of a confirmed failing result or confirmed contamination; poor segregation of sensitising or hazardous drugs; a label that creates a mix-up between products or strengths.
- Major: the same kinds of lapse outside the critical zone; other missing validation or a limited validation gap; missing tests for other attributes; missing data safeguards with no evidence of manipulation; weak investigation of other deviations or complaints; a required record or procedure that does not exist, or a record that omits the evidence a step or test was done; a wrong label.
- Minor: an isolated or administrative lapse where the control works overall, such as a missing signature, date or page number on an evidenced step, or late closure of a sound investigation. At a non-sterile producer a contamination finding goes one level lower unless actual contamination is reported.

Findings from the review of one executed batch record:
- Only an attribute of an entry is missing, wrong, late or untidy while the step itself is evidenced (initials on a non-critical step, date, time, page number, units, a readable correction without initials, an unused field not struck through, a plain date slip): Minor.
- The evidence itself is missing (a blank value or result, an unreadable or obscured entry, a lot number, equipment identity, a missing page, a required attachment, an attachment for another batch): Major.
- No performer or second-person signature: Major on a critical step, Minor on any other. A critical step directly determines identity, strength, purity or sterility. A step known only by its number is not treated as critical.
- A recorded value outside its stated limit: Major. Critical when a release or sterility-related result is failing or absent and the batch was approved or released anyway.
- A calculation or transcription error: Minor when the right figure is within its limit or no limit is quoted, Major when it is outside its limit or changes a quantity charged.
- Material past expiry or not released, a lot at the point of use that does not match dispensing, equipment overdue for calibration or with cleaning unverified: Major. The wrong material or strength in the batch: Critical.
- Entries that appear fabricated: Critical on a critical step or a test result, Major otherwise. Entries misdated or recorded before the step: Major.
- A step with no evidence that it was done, or not done as instructed: Major for a critical step, Minor otherwise.
Then adjust, in this order. When the item has no bearing on the product, the result is Minor. A Minor lapse that is repeated (throughout, on most pages, in more than five places) or made by several people is Major. When the text says the problem is recorded in a deviation with an assessment, or the batch was rejected, go one level lower."""

SEVERITY = {
    "Minor": "An isolated or administrative lapse. The control exists and works overall. No plausible effect on product.",
    "Major": "A required GMP control is absent or failing, so assurance of quality is weakened, but harm would need a further failure or a later control would likely catch it.",
    "Critical": "A credible, direct path to patient harm from distributed product with no later control that would reliably catch it, or the data used to release product cannot be trusted.",
}

CATEGORY_INSTRUCTIONS = (
    "Which risk category does this finding fall under? Choose the failure mechanism the text cites, not its downstream "
    "consequence. A gap in how an entry is documented (missing signature, date, page, attachment, unreadable or "
    "uncorrected entry) is document control and traceability. A validation failure goes to the category of the process "
    "that lacks validation. Use process not followed only when nothing more specific fits. For several lapses, use the "
    "category of the most severe."
)

CATEGORIES = {
    "contamination and mix-ups": "Aseptic technique and material transfer, cross-contamination, mix-ups, line clearance of a manufacturing area, sterilisation and aseptic process validation.",
    "quality control failure": "Release and laboratory testing, specifications, test method validation, a release or laboratory result failing or absent.",
    "critical process parameter deviation": "Process design and validation, in-process controls and limits, a parameter, in-process result, hold time or yield outside its limit.",
    "process not followed": "A written procedure exists but was not followed, a step skipped, sampling not as required, the quality unit not exercising its duties.",
    "personnel hygiene": "Gowning, attire, personal cleanliness, health conditions.",
    "equipment and environment hygiene": "Cleaning and disinfection, cleaning validation, facility condition, environmental monitoring programme, equipment maintenance and calibration.",
    "document control and traceability": "Missing or incomplete paper records, batch records and logs; entries that appear fabricated or misdated.",
    "inadequate investigation and capa": "Investigations of failures, deviations and complaints; a deviation not raised, still open or thinly assessed; corrective action.",
    "labeling and packaging": "Label control, label issue and reconciliation, packaging operations and line clearance, expiry dating on labels.",
    "stability and storage": "Stability programme, storage conditions, beyond-use dates.",
    "supplier and raw material quality": "Component and container testing, supplier qualification, component weighing, addition, lot identity and released status.",
    "electronic data integrity": "Computerised systems, audit trails, access control, electronic records.",
}

CFR_INSTRUCTIONS = "Which single section of 21 CFR is the most specific one this finding falls under?"

CFR_TITLES = {
    "211.22": "Responsibilities of the quality control unit",
    "211.25": "Personnel qualifications and training",
    "211.28": "Personnel responsibilities, clothing and hygiene",
    "211.42": "Design and construction of buildings; separation of operations to prevent contamination and mix-ups",
    "211.46": "Ventilation, air filtration, air heating and cooling",
    "211.56": "Sanitation of buildings",
    "211.58": "Maintenance of buildings",
    "211.63": "Equipment design, size and location",
    "211.65": "Equipment construction and product-contact surfaces",
    "211.67": "Equipment cleaning and maintenance",
    "211.68": "Automatic, mechanical and electronic equipment; calibration; computer systems",
    "211.80": "General requirements for handling components, containers and closures",
    "211.84": "Testing and approval or rejection of components, containers and closures",
    "211.87": "Retesting of approved components, containers and closures",
    "211.94": "Drug product containers and closures",
    "211.100": "Written production and process control procedures; deviations from them",
    "211.101": "Charge-in of components: weighing, measuring, addition and its verification",
    "211.103": "Calculation of yield",
    "211.110": "Sampling and testing of in-process materials and drug products",
    "211.111": "Time limitations on production",
    "211.113": "Control of microbiological contamination; aseptic and sterilisation process validation",
    "211.115": "Reprocessing",
    "211.122": "Examination and usage criteria for labeling and packaging materials",
    "211.125": "Labeling issuance and reconciliation",
    "211.130": "Packaging and labeling operations",
    "211.134": "Drug product inspection after packaging and labeling",
    "211.137": "Expiration dating",
    "211.142": "Warehousing procedures",
    "211.160": "General requirements for laboratory controls; specifications and sampling plans",
    "211.165": "Testing and release for distribution",
    "211.166": "Stability testing",
    "211.167": "Special testing requirements: sterility, pyrogens, ophthalmic, controlled release",
    "211.170": "Reserve samples",
    "211.180": "General requirements for records and reports; annual review",
    "211.182": "Equipment cleaning and use log",
    "211.186": "Master production and control records",
    "211.188": "Batch production and control records",
    "211.192": "Production record review and investigation of discrepancies",
    "211.194": "Laboratory records",
    "211.198": "Complaint files",
    "314.81": "Postmarketing reports, including field alert reports",
}


def questions(cfr_classes: list[str]) -> dict:
    """The decision request for one finding. CFR options are the classes the arm was built with, plus other."""
    cfr = {section: CFR_TITLES[section] for section in cfr_classes}
    cfr["other"] = "Any other section."
    return {
        "severity": {"type": "choice", "instructions": SEVERITY_INSTRUCTIONS, "criteria": SEVERITY},
        "primary_risk_tier": {"type": "choice", "instructions": CATEGORY_INSTRUCTIONS, "criteria": CATEGORIES},
        "cfr_reference": {"type": "choice", "instructions": CFR_INSTRUCTIONS, "criteria": cfr},
    }
