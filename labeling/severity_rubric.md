# FDA 483 labelling rubric (drug GMP, 21 CFR 210/211)

Status: draft v2.1. The boundary rules R1 to R10 are proposals pending expert review.

Label each observation from its own text. Do not assume contamination, harm, or intent that the
text does not report. Redactions such as `(b)(4)` are normal and carry no meaning.

## Scope

This rubric covers manufacturing, compounding, packaging, testing, and holding of human or
veterinary drugs. Mark an observation out of scope when it concerns something else, for example a
bioanalytical or clinical study site, a medical device, food, blood, or tissue. Still give your
best labels for an out-of-scope observation.

## Severity

Ask: if this failure went uncorrected, what is the worst credible consequence for a patient, and
would a later control reliably catch it first?

| Severity | Definition |
|---|---|
| Critical | A credible, direct path to patient harm from distributed product, with no later control that would reliably catch it. Or the data used to release product cannot be trusted. |
| Major | A required GMP control is absent or failing, so assurance of quality is weakened, but harm would need a further failure or a later control would likely catch it. |
| Minor | An isolated or administrative lapse. The control exists and works overall. No plausible effect on product. |

### Boundary rules

Find the rule that matches the finding. If none matches, use the definitions above. When several
findings or rules apply, take the most severe result. Only R7 and R9 lower a result.

- **R1 Critical zone (sterile products).** A lapse that exposes sterile product, containers,
  closures, or product-contact surfaces in the ISO 5 (Grade A) zone to a contamination source is
  Critical, even with no contaminated batch reported. Examples: non-sterile gowns, gloves, wipes,
  or tools; exposed skin or hair; undisinfected materials; blocked first air; visible residue or
  damaged surfaces inside ISO 5. Sterile production with no qualified ISO 5 environment at all is
  also Critical. The same lapse in ISO 7, ISO 8, or support areas is Major. A weak environmental
  monitoring programme, with no exposure observed, is Major.
- **R2 Sterility assurance validation.** For product distributed as sterile, validation of
  sterilization, depyrogenation, sterile filtration, or the aseptic process (media fill, aseptic
  process validation under any name) that is absent, failed, or does not represent the real
  process is Critical. Not representative means, for example, far fewer units or a much shorter
  run than production, a different container or hood, or no growth promotion. A limited gap in an
  otherwise representative validation is Major. Other missing validation (non-sterile
  manufacturing process, cleaning, analytical methods other than sterility or endotoxin) is Major.
- **R3 Release without evidence.** Product released or distributed with no test, or an invalid
  test, for sterility, endotoxin, identity, or strength is Critical. So is release of a batch
  with a known failing result. Missing tests for other attributes, or missing component or
  in-process tests where finished-product testing still covers the attribute, is Major.
- **R4 Data integrity.** Evidence that results were falsified, deleted, backdated, selectively
  reported, or retested into compliance is Critical. Missing safeguards (no audit trail, shared
  logins, uncontrolled access, unverified changes) with no evidence of manipulation is Major. An
  entry made before or after the fact for a step that was actually performed is Major.
- **R5 Investigations.** No investigation of a confirmed failing result (out of specification,
  sterility, endotoxin) or of confirmed contamination is Critical, unless the text states the
  affected product was rejected or not distributed. So is failing to extend such an investigation
  to other affected batches. Inadequate investigation of other deviations or complaints is Major.
  Late or thinly documented closure of an otherwise sound investigation is Minor.
- **R6 Records and procedures.** A required record or written procedure that does not exist at
  all is Major. A record that exists is also Major when what it omits removes traceability or the
  evidence that a required step or test was done: component lot numbers, test results, who
  performed or checked a step. It is Minor when the step is evidenced and only an attribute is
  missing or late, such as a signature, date, time, or page number.
- **R7 Product context.** For contamination-related findings at a non-sterile producer (oral,
  topical, OTC), go one level below what R1 would give, unless the text reports actual
  contamination or objectionable organisms, which is Critical. Inadequate segregation or
  containment of beta-lactams, cytotoxics, or other sensitizing or hazardous drugs from other
  products is Critical at any producer, with or without detected cross-contamination.
- **R8 Multi-part observations.** When an observation lists several findings, label by the most
  severe one.
- **R9 Isolated versus systemic.** A single isolated instance of a control that otherwise works
  may go from Major to Minor. Nothing goes below Critical on this ground.
- **R10 Label content.** A wrong label, or a label missing what a user needs to use the product
  safely (identity, strength, route, lot, expiry or beyond-use date, storage conditions), is Major,
  and Critical when it creates a mix-up risk between products or strengths. A label missing only
  regulatory or administrative content (a required statement, compounding date, ingredient list,
  phone number, NDC) is Minor.

## Risk category

Pick one. Choose the failure mechanism the observation cites, not its downstream consequence.

| Tier | Category | Anchor | Covers |
|---|---|---|---|
| 1 | contamination and mix-ups | 211.113, 211.42(c) | Aseptic technique and material transfer, cross-contamination, mix-ups, sterilization and aseptic process validation |
| 1 | quality control failure | 211.160, 211.165, 211.167 | Release and laboratory testing, specifications, test method validation |
| 2 | critical process parameter deviation | 211.100(a), 211.110 | Process design and validation, in-process controls and limits |
| 2 | process not followed | 211.22, 211.100(b) | Written procedure exists but was not followed; quality unit not exercising its duties; no more specific category applies |
| 3 | personnel hygiene | 211.28 | Gowning, attire, personal cleanliness, health conditions |
| 3 | equipment and environment hygiene | 211.67, 211.56, 211.42 | Cleaning and disinfection, cleaning validation, facility condition, environmental monitoring programme, equipment maintenance |
| 4 | document control and traceability | 211.180 to 211.194 | Missing or incomplete paper records, batch records, logs |
| 4 | inadequate investigation and capa | 211.192, 211.198 | Investigations of failures, deviations, and complaints; corrective action |
| additional | labeling and packaging | 211.122 to 211.137 | Label control, packaging operations, expiry dating on labels |
| additional | stability and storage | 211.166, 211.142 | Stability programme, storage conditions, beyond-use dates |
| additional | supplier and raw material quality | 211.80 to 211.94 | Component and container testing, supplier qualification |
| additional | electronic data integrity | Part 11, 211.68 | Computerized systems, audit trails, access control, electronic records |

Tie-breaks:
- Behaviour during aseptic work (touch contamination, unsanitized gloves, movement, material
  transfer) is `contamination and mix-ups`. What a person wears is `personnel hygiene`.
- A validation failure goes to the category of the process that lacks validation.
- A missing or inadequate procedure goes to the category of its subject. Use
  `process not followed` only when nothing more specific fits.
- For multi-part observations, use the category of the most severe part.

## CFR section

Give the single most specific 21 CFR section the finding falls under, at section level
(for example `211.113`), without paragraph letters.
