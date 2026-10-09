# Writing sparse batch record findings

You write the notes a reviewer makes while paging through an executed pharmaceutical batch record.
The reviewer sees only the pages. A note says what a field or page shows. It does not say what
happened in the plant, why, whether anyone noticed, or what became of the batch.

You are given a file of seeds. Each seed holds the facts of one finding. For each seed, write that
one finding in three wordings.

## The facts

- `lapses` is what the page shows. One finding may hold two or three lapses; then put them in the
  same finding, joined the way a reviewer would ("and", "or", "also").
- `record_area` is the part of the record. If a lapse cannot occur there, move it to a part where
  it can, and change nothing else.
- `location` tells you how to point at the place. When it says to use only a step number, page,
  table or section title, the reader must not be able to tell what the step does.
- `count` tells you how many, and how precisely to say it. Follow it exactly: when it says to give
  no total, give none.
- `numbers` tells you whether measured values and limits may appear. Page, step and field
  references are always fine.
- `certainty`: when it says the reviewer could not tell, say that in the finding.

## Three wordings of the same finding

- `short`: one sentence, 10 to 35 words.
- `expected_actual`: the same statement, then a part beginning `Expected:` (what that field or page
  is supposed to contain, in general terms) and a part beginning `Actual:` (what it shows). 35 to
  70 words in total.
- `narrative`: past-tense prose, as an investigator would write it in a report. 30 to 70 words.

All three carry the same facts and nothing more. The longer wordings may restate the documentation
requirement for that field. They must not add what the step is (when the seed hides it), a count,
a value, a limit, a cause, a consequence, or anything about deviations, investigations, review,
approval or release of the batch.

Use the whole of each range: some findings near the bottom, some near the top.

## Rules

- Do not grade the finding. No words such as minor, major, critical, serious, significant, severe,
  concern, risk, or violation, and nothing about consequences for patients or product quality.
- No company names and no brand names. A product or batch number may appear in some findings and
  be left out of others.
- Vary how sentences open and how places are referred to. Do not reuse one sentence frame.
- Write every finding yourself, one at a time. Do not generate the text with a script or template.
- Do not use em dashes or en dashes.

## Output

Write one JSON file: a list with one object per seed, in seed order.

```json
{
  "seed_id": "n0000",
  "establishment_type": "copied from the seed",
  "facts_used": {"the seed's facts, with record_area changed if you had to move it": "..."},
  "wordings": {"short": "...", "expected_actual": "...", "narrative": "..."}
}
```

After writing the file, load it with Python to confirm it parses and has one object per seed.
