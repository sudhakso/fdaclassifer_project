# Writing findings from a rule-based batch record review

You write the findings an automated review of an executed pharmaceutical batch record package
produces. The review applies one check to one record, or to two documents against each other, and
reports every entry that fails that check in a single finding. A finding states what was checked
and what was seen. It does not say what happened in the plant, why, or what became of the batch,
unless the seed says so.

You are given a file of seeds. Each seed holds the facts of one finding. Write that one finding.

## The facts

- `process` is what is being made. Take your steps, equipment, tests and materials from it, and
  invent plausible specifics: operation numbers, page numbers, table names, sample and request
  numbers, equipment tags, values with units.
- `documents` are the documents the finding involves. Give each an invented file name of the kind
  a scanned package has, and cite it. With two documents, the finding must cite both.
- `checks` is what the review tested. `compares` says what was compared. `defect_forms` are the
  forms the failure takes: every form listed must appear in the finding, and no other defect may.
  With two checks, both go into the same finding.
- `extent` is how many entries fail and how precisely to say it. Follow it exactly: when it says
  to give no total, give none; when it says to name each place, name each.
- `values`: whether recorded values are quoted. When it asks for values malformed as written,
  quote one or two the way a poor scan would render them.
- `step`: whether the reader can tell what the steps are, or sees only their numbers.
- `afterwards`: when it begins "say nothing", the finding must not mention deviations,
  investigations, remarks, review, approval or release at all. Otherwise state what it says.

## What to write

Four fields that together make the finding, and one rewrite:

- `title`: one line, 4 to 12 words.
- `observation`: what was checked and what was seen. Usually one sentence, sometimes two, 14 to 38
  words; most should fall between 18 and 32. It names the documents and the places.
- `expected`: what the record or the instruction requires there. 8 to 25 words.
- `actual`: what the record shows. 5 to 25 words, or, for about one finding in eight, a terse list
  of the failing entries separated by semicolons with no connecting prose.
- `narrative`: the same finding as past-tense prose, as an investigator would write it in a
  report. 35 to 80 words.

All five carry the same facts and nothing more. Use the whole of each range: some near the bottom,
some near the top.

## Rules

- Do not grade the finding. No words such as minor, major, critical, serious, significant, severe,
  concern, risk, or violation, and nothing about consequences for patients or product quality.
- No company names and no brand names. Generic substance names and invented numbers are fine.
- Vary how sentences open, how documents are named and how places are listed. Do not reuse one
  sentence frame from finding to finding.
- Write every finding yourself, one at a time. Do not generate the text with a script or template.
- Do not use em dashes or en dashes.

## Output

Write one JSON file: a list with one object per seed, in seed order.

```json
{
  "seed_id": "c0000",
  "establishment_type": "copied from the seed",
  "facts_used": {"the seed's facts": "..."},
  "wordings": {"title": "...", "observation": "...", "expected": "...", "actual": "...", "narrative": "..."}
}
```

After writing the file, load it with Python to confirm it parses and has one object per seed.
Reply with one line: the number of findings written and the output path.
