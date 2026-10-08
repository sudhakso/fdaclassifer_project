# FDA 483 classifier: where we stand (2026-10-07)

The model handed over this morning was broken: every weight was NaN, so it gave the same answer for
every observation. That is fixed. We then relabelled the data with a written rubric and retrained.

The best models now get severity right about 85% of the time and risk category about 86%, and they
match FDA's own CFR citation about 70% of the time, on firms never seen in training. The baseline
trained on today's UI labels scored 38% on that FDA check.

Almost all of the gain came from better labels. Longer training, a bigger model, and extra input
each added one or two points on top.

## What each run is

Every run predicts the same three things for one observation: severity, risk category, and CFR
section. Scope is drug GMP (21 CFR 210/211) only. Each run changes one thing from an earlier run.

| Run | In one line | What it changed, and from which run | Why we ran it |
|---|---|---|---|
| **A** | Baseline on today's labels | The starting point. Labels are the flash-lite ones the UI uses now. Model is DeBERTa-v3-base, trained 4 epochs with the repo's default settings. | To have a reference, and to prove the NaN fix works on the GPU. |
| **B** | New labels | Same as A, but trained on the Opus 5.5 labels made with the rubric. | To measure what relabelling alone is worth. |
| **B3** | New labels, trained longer | Same labels as B. Trains up to 8 epochs and keeps the best one, judged on a set of held-out firms. Small warmup at the start. The inspection-wide summary is left out of the input. | To see if B stopped too early. |
| **D** | Bigger model | Same as B3, but the encoder is ModernBERT-large (about twice the size) instead of DeBERTa-v3-base. | To see if model size is what limits the score. ModernBERT-large is also the encoder Laya is built on, but this run is not Laya. |
| **E** | Extra input | Same as B3, but the model also reads the topics the UI already has for each observation (for example "lack of sop practice"). | Tejas's suggestion: use the existing categories. |

## Test-set scores

1,662 observations from firms held out of training, the same for every run. The first three rows
are the fairest, because the reference does not favour any run's own labels.

| Label | Scored against | A | B | B3 | D | E |
|---|---|---|---|---|---|---|
| CFR section | FDA's own citation (427 rows) | 37.9% | 67.7% | 70.0% | 69.8% | **70.7%** |
| Severity | Rows where all three labellers agree (977) | 81.8% | 86.7% | 89.2% | 90.4% | **90.6%** |
| Severity | Gemini pro (not used to train any run) | 69.8% | 69.6% | 71.7% | 71.1% | **72.0%** |
| Severity | Opus labels | 66.4% | 81.5% | 83.4% | **85.7%** | 84.8% |
| Risk category | Opus labels | 66.4% | 85.1% | 84.3% | 85.7% | **85.9%** |
| CFR section | Opus labels | 43.0% | 74.4% | 76.2% | **79.1%** | 78.3% |

How to read it:
- Always guessing the most common answer would score 62% on severity, 26% on category, 18% on CFR.
- Two runs with identical settings differ by about one point. So B3, D and E are close to a tie,
  with D and E perhaps one to two points ahead of B3.

## What moved the score

| Change | Runs compared | Effect |
|---|---|---|
| Better labels | A to B | Large. CFR against FDA rose from 38% to 68%. Severity on undisputed rows rose 5 points. |
| Training longer, keeping the best epoch | B to B3 | About 2 points. |
| Bigger model | B3 to D | 1 to 2 points on our labels, nothing on the FDA check. |
| Topics as extra input | B3 to E | 1 to 2 points on our labels, under 1 on the FDA check. |
| Removing the inspection summary | A to A-nosummary | None. |

## The Minor class

Minor is 3% of the test set (54 observations). Every model finds fewer than half.

| Run | Minor found (of 54) | Right when it predicts Minor |
|---|---|---|
| B3 | 23 | 38% |
| D | 22 | 49% |
| E | 27 | 42% |

## Label quality

| Labeller | CFR section matches FDA's citation (3,165 rows) | Same severity when the same text is labelled twice |
|---|---|---|
| Opus 5.5 with the rubric | 74.4% | 96.4% |
| Gemini pro | 65.0% | not measured |
| Flash-lite | 52.6% | 89.2% |

The two consistency figures come from different samples (Opus was tested on harder rows), so read
them as indicative.

## What is still weak

- **Minor.** Too few examples (393 in all) for any model here to learn it well.
- **Severity has no human ground truth.** FDA does not grade observations. The evidence for the new
  severity labels is consistency and agreement on undisputed rows, not a human reference.
- **The rubric has not been reviewed by an expert.** `labeling/severity_rubric.md` is one page with
  ten boundary rules. One of them (a missing record is Major, not Minor) roughly halves the number
  of Minor labels compared with flash-lite.
- **The models are near what these labels allow.** A bigger model and extra input both landed within
  a point or two of B3. Further gains are more likely to come from the labels than from the model.
- **GPU supply.** The GPU nodes were shut down five times today, each time on the hour or half hour.
  The trainer now resumes from checkpoints, which is the only reason the long runs finished.

## Which model to use

- **B3** is the simplest: the small model, text only.
- **D** has the best severity and CFR scores against our labels, at about twice the model size.
- **E** is the small model and scores as well as D, but it needs the topic-extraction step to run first.

The three are close enough that the choice can be made on cost and simplicity.

## Where things are

| What | Location |
|---|---|
| Model A | `gs://fdaclassifier/registry/a-flash-1007-1150/` |
| Model B | `gs://fdaclassifier/registry/b-opus-1007-1331/` |
| Model B3 | `gs://fdaclassifier/registry/b3-opus-long-1007-1322/` |
| Model D | `gs://fdaclassifier/registry/d-modernbert-large-1007-1420/` |
| Model E | `gs://fdaclassifier/registry/e-topics-1007-1439/` |
| Relabelled data and rubric | `gs://fdaclassifier/dataset/v2/relabel/` |
| Training and test files per run | `gs://fdaclassifier/dataset/v2/` |
| Rubric | `labeling/severity_rubric.md` |
| Scoring script | `scripts/score_predictions.py` |

Code changes are uncommitted on `main`.
