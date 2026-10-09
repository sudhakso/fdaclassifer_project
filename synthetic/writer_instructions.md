# Writing synthetic batch record findings

You write findings the way a reviewer of an executed pharmaceutical batch record would note them.
You are given a file of seeds. Each seed holds the facts of one finding. For each seed, write that
one finding in three wordings.

## Step 1: make the facts concrete

Invent the specifics the facts need: the step number and page, the parameter with its recorded
value and its limit (with units), times, equipment tags, lot and batch numbers, how many entries
are affected. Keep them plausible for the product and the part of the record.

- `issue` is what is wrong. Keep it as given.
- `record_area` is where in the record it is. If the issue cannot plausibly occur there, move it to
  a part of the record where it can, and change nothing else.
- `step_kind` tells you what sort of step to choose. Show it through the step itself (for example
  weighing the active ingredient, as against noting a room number). Never use the phrase.
- `extent` is how many times it occurs. State the count.
- `effect`, when present, is what the error does to the figure. State it.
- `handling` and `batch_status`: when the value begins with "say nothing", no wording may mention
  that topic at all. Otherwise every wording must state it.

## Step 2: write three wordings of the same finding

- `short`: one or two sentences, 12 to 35 words. A plain statement of what was found and where.
  Leave out the product name and batch number here if you need the room.
- `expected_actual`: the same statement, followed by a part beginning `Expected:` (what the record
  or procedure requires) and a part beginning `Actual:` (what the record shows). 40 to 80 words in
  total.
- `narrative`: past-tense prose, as an investigator would write it in a report. 40 to 90 words.

Use the whole of each range. Across your findings some should sit near the bottom of a range and
some near the top; do not write them all to one length.

All three wordings must carry the same facts: what is wrong, where, how many times, and the
effect, handling and batch status when the seed gives them. A longer wording may spell out the
requirement. It must not add another problem, a consequence, or an opinion.

## Rules

- Do not grade the finding. No words such as minor, major, critical, serious, significant, severe,
  concern, risk, or violation, and nothing about consequences for patients or product quality.
- No company names and no brand names. Generic drug names and invented batch, lot and equipment
  numbers are fine.
- Vary the products, strengths, numbers, and the way sentences open. Do not reuse one sentence
  frame from finding to finding.
- Write every finding yourself, one at a time. Do not generate the text with a script or template.

## Output

Write one JSON file: a list with one object per seed, in seed order.

```json
{
  "seed_id": "s0000",
  "establishment_type": "copied from the seed",
  "facts_used": {"the seed's facts, with record_area changed if you had to move it": "..."},
  "wordings": {"short": "...", "expected_actual": "...", "narrative": "..."}
}
```

After writing the file, load it with Python to confirm it parses and has one object per seed.
Reply with one line: the number of findings written and the output path.
