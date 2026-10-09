# Labelling batch record findings

You label findings from the review of executed pharmaceutical batch records. Read both rubric
files in full before you start, and follow them exactly (paths from the repository root):

- labeling/severity_rubric.md
- labeling/batch_record_rubric.md

The second file is the one written for this kind of finding. Where it has a rule (the B rules),
use it, and follow its section "Label what the text shows" and its order of applying the rules. The first file gives the severity definitions, the risk categories, and rules R1 to R5, R7, R8
and R10.

You are given a file with a list of rows: `id`, `establishment_type`, `full_details`. Label every
row from its own text only. Do not assume anything the text does not say. Decide each row yourself,
one at a time. Do not use a script, keyword matching, or any other file to choose labels.

## Output

Write one JSON file: a list with one object per row, same ids, same order.

```json
{
  "id": "copied from the row",
  "severity": "Minor | Major | Critical",
  "risk_category": "one of the twelve categories in severity_rubric.md, lower case",
  "cfr_section": "one section such as 211.188, no paragraph letters",
  "rule": "the rule that decided severity, for example B3, or 'definition' when none matched",
  "borderline": true,
  "in_scope": true,
  "reason": "one sentence"
}
```

Set `borderline` to true when a second careful reader, following the same rules, could reasonably
give a different severity. Do not set it merely because the finding gives little detail: the
rubric says what to do then.

After writing the file, load it with Python to confirm it parses, has one object per input row, and
uses only the allowed severity and category values. Reply with one line: the number of rows
labelled and the output path.
