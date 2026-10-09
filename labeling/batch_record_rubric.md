# Batch record finding rubric (addendum to the FDA 483 rubric)

Status: draft v0.6. The rules below are proposals pending expert review.

Use this together with `severity_rubric.md` when the text is a finding from the review of one
executed batch record (the production record, its attachments, and the logs and test results it
refers to). The severity definitions, risk categories, and CFR section rule in that file apply
unchanged. The rules below replace R6 and R9, which were written for site-level observations, and
the last sentence of R4 about entries made before or after the fact. R1 to R5, R7, R8 and R10
still apply where they match and no B rule covers the case.

## Severity

Ask: does the record, as described, still show that the step was done and done correctly? If not,
what is the worst credible consequence for a patient who receives this batch, and would a later
control reliably catch it first?

### Label what the text shows

Many findings say only what a field on a page shows: a step number, a page, what is missing. They
do not say what the step does, how often the lapse occurs, whether anyone noticed, or what became
of the batch. Severity rises only on what the text shows.

- **Step.** A critical step is one that directly determines identity, strength, purity or
  sterility: weighing and addition of components, a process parameter or in-process test that has
  a stated limit, fill volume or weight adjustment, sterilisation, sterile filtration,
  depyrogenation, aseptic filling, line clearance, yield calculation, issue, printing check and
  reconciliation of the labels that go on the product, release testing, approval of the master record, and the quality
  unit's review and approval of the executed record. Judge the individual step, not the section it
  sits in. When the text identifies a step only by its number, page or table and does not show
  what it does, treat it as not critical. Review checklists and the signature blocks of deviation
  forms are not critical steps. A laboratory test on the batch or its materials is treated as a
  release test unless the text shows it is for stability, trending or information only.
- **Item.** An item has a bearing on the product when the text shows it is a component, a
  container or closure, a product label, equipment that processes, holds or touches the product
  (a named vessel, mixer, press or filling machine counts; unnamed "equipment" does not), a sample
  for an in-process or
  release test, an instrument or reading that has a stated limit, a room or surface where product
  is exposed, or anything used in the critical zone of a sterile operation. Anything else has no
  bearing on the product, for example shipper cases and other outer packaging, tray and trolley
  tags, a room where product is in closed containers, sample storage, inspection lighting,
  cleaning agents for surfaces that do not touch product, and reference numbers of supporting
  forms. When the text does not show that an item has a bearing, treat it as having none.
- **Count.** Use the count the text gives. "Several" or "multiple" with a few examples and no
  total is not repetition. "Throughout", "on most pages", "all entries", a stated count above
  five, or more than five locations listed is repetition. Count lapses of the same kind together
  and different kinds separately. A run of consecutive rows left the same way counts once.
- **Handling and release.** When the text does not mention a deviation, an investigation, or the
  status of the batch, assume nothing about them.
- **Uncertain reading.** When the text says the reviewer could not tell whether an entry is
  absent or only unreadable in the copy reviewed, label it as the lapse it would be if absent, and
  set `borderline` to true.

### Rules

- **B1 Attribute missing or wrong, step evidenced.** The step or result is recorded and only an
  attribute of the entry is missing, wrong, late or untidy: initials or signature on a
  non-critical step, date, time, page number, units, document number or version, a printed name, an
  unused field left without a strike-through, a result with no working shown, pencil, ditto marks, a correction without initials, date or
  reason where the original entry is still readable, a mislabelled or misfiled attachment that is
  present, a superseded form (unless the text shows its content differs in an instruction or
  limit, which is Major). A date or time that is plainly a slip (a wrong year, a time out of order
  with the step before it) is also here. So is a signature or date added late that carries its
  true date and shows who added it, whether or not it is marked as a late entry. Minor.
- **B2 Evidence missing.** What is missing is the evidence itself: a value or result left blank,
  a checklist question left unanswered,
  an entry that cannot be read, an original entry obscured by overwriting or correction fluid, a
  material lot number, the identity of equipment, a missing page, a required attachment (printout,
  chart, weigh ticket, chromatogram, label specimen), or an attachment that belongs to a different
  lot or batch. Major. When the attachment is missing but the text shows the result is written at
  the step, it is Minor, except for a sterilisation or depyrogenation cycle, a sterile filter
  integrity test, or a release test, where the printout is the primary record and it stays Major.
- **B3 Performer or second-person check.** No signature for who performed, or who verified, a
  critical step is Major, because the check is not evidenced. On a non-critical step it is Minor.
  A signature that is present but was added late falls under B1. Work recorded under a shared
  login is treated the same way as a missing performer signature, and one person signing as both
  performer and checker the same way as a missing check.
- **B4 Value outside its limit.** A recorded process parameter, in-process result, hold time,
  yield, reconciliation, or weighed quantity outside the limit stated in the record is Major,
  whether or not a deviation is referenced (see B10 for when a deviation lowers it). It is
  Critical when the item is a release test for sterility, endotoxin, identity or strength, a
  sterilisation cycle, a sterile filter integrity test, or a critical-zone excursion, its result
  is failing or absent, and the text shows the batch was approved or released anyway (R3, R5).
- **B5 Calculation and transcription errors.** A figure that is miscalculated, miscopied, or
  recorded differently in two places is Minor when the text shows the right figure is within its
  limit, when the text quotes no limit for it, or when the lot number at the point of use is
  correct and only a summary page is wrong. It is Major when the right figure is outside its limit, when the error
  changes the quantity of a component charged or a potency adjustment, or when the text says the
  effect cannot be worked out.
- **B6 Materials and equipment.** A component, container, closure or product label used past its
  expiry or retest date or not in released status, a lot entered at the point of use that does not
  match the dispensing record, or equipment used with calibration overdue or cleaning status not
  verified, is Major. The wrong material or wrong strength actually going into the batch is
  Critical unless the text shows the batch was rejected or the error was caught before the next
  step. A quantity outside its tolerance is B4.
- **B7 Data credibility.** Entries that appear fabricated are Critical when they concern a
  critical step or a test result, and Major otherwise (R4): recorded for work that the record
  itself shows was not done, signed by someone the record shows was not there, different signers
  in one hand, copied or identical results, or values changed to pass with the raw data altered or
  removed. These are Major: entries dated as if made at the time when the record shows they were
  made later; entries recorded before the step took place; a review signed before the results it
  covers existed; a measured value or test result for a critical step first written in days
  later with no raw data from the time; tests that appear in an instrument log with no reported
  result and no explanation (Critical when the text shows a failing result was left out). A copy
  that differs from correct, attached raw data is B5, not B7, unless the text shows it was
  deliberate.
- **B8 Steps and sampling.** A step with no entry and no other evidence that it was done, or a
  step done partly or not as the record instructs, is Major when it is a critical step and Minor
  otherwise. A step done out of sequence is Minor when all steps are evidenced and the order does
  not affect the outcome; when a check or test was meant to come first and gate the step, or a
  conditional step carries entries although its gating result says it should not have run, treat
  it as a step not done as instructed. Sampling not done as required, including too few units, is
  Major when the sample feeds an in-process or release test and Minor for retention, stability,
  trending or reference samples.
- **B9 No bearing on the product.** When the item concerned has no bearing on the product, the
  result under B2, B4, B5, B6 or B8 is Minor.
- **B10 Already handled.** When the text states that the problem is recorded in a deviation with
  an assessment of its effect, or that the batch was rejected, go one level lower. Nothing goes
  below Minor. A deviation that is referenced but still open, or has no assessment, does not lower
  the result. When the finding is only that a deviation is still open, unsigned or thinly
  assessed, with no other lapse described, it is Minor, or Major when the text shows the batch was
  approved or released with no assessment made.
- **B11 Repetition.** A single instance does not lower a result. Any lapse that is Minor after
  B9, when it is repeated (see Count above) or made by several people, is Major, because the
  practice itself is failing. Count the entries that are deficient. One mistake that carries over
  mechanically (page numbers shifted by one, a unit missing from a column heading) counts once.

Order: find the base result from B1 to B8, taking the most severe when several lapses or rules
apply. Then apply B9, then B11, then B10 last. Only B9 and B10 lower a result.

## Risk category and CFR section

Use the categories in `severity_rubric.md`, chosen by the failure mechanism. A gap in how an entry
is documented (missing signature, date, page, attachment, unreadable or uncorrected entry) is
`document control and traceability`, with the section for the record it sits in: 211.188 for the
production record, 211.194 for a laboratory record, 211.182 for an equipment cleaning and use log,
211.186 for the master record. Other usual choices:

| Finding is about | Category | Usual section |
|---|---|---|
| Component weighing, addition, lot identity, released status | supplier and raw material quality | 211.101 |
| Container, closure or packaging material lot identity or status | supplier and raw material quality | 211.94 |
| Process parameter, in-process result or hold time outside its limit | critical process parameter deviation | 211.110, 211.111 |
| Yield calculation | critical process parameter deviation | 211.103 |
| Step skipped or instruction not followed, sampling not as required | process not followed | 211.100 |
| Deviation not raised, not investigated, still open, or review incomplete | inadequate investigation and capa | 211.192 |
| Release or laboratory result failing or absent | quality control failure | 211.165 |
| Label issue, reconciliation, packaging line clearance, packaging | labeling and packaging | 211.125, 211.130 |
| Line clearance of a manufacturing area or equipment | contamination and mix-ups | 211.42 |
| Equipment cleaning status, calibration | equipment and environment hygiene | 211.67, 211.68 |
| Room temperature, humidity or pressure reading outside its range | equipment and environment hygiene | 211.46 |
| Electronic records, audit trail, access | electronic data integrity | 211.68 |
| Sterilisation, filtration, aseptic steps, excursions where sterile product is exposed | contamination and mix-ups | 211.113 |
| Entries that appear fabricated or misdated | document control and traceability | 211.188 |
