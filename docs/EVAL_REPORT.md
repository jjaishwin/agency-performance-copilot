# Evaluation report: Agency Performance Copilot

**Method:** 15 benchmark questions (see `genie/GENIE_AGENT_SETUP.md`, section 6), each with a verified SQL answer. Genie's answer counts as correct when its result matches the verified result. All 15 are re-run after every change.

**Release bar:** ≥ 14/15, and no wrong numbers on the attainment questions (B2, B3, B4, B14).

## Results by run

| Run | Date | Change since last run | Score |
|---|---|---|---|
| 1 | [date] | Baseline: tables + instructions only | [ ]/15 |
| 2 | [date] | [e.g., added SQL expressions for share and attainment] | [ ]/15 |
| 3 | [date] | [e.g., added column comments; entity matching on account_name] | [ ]/15 |

## Failures and root causes

| Benchmark | What Genie did | Root cause | Fix | Fixed in run |
|---|---|---|---|---|
| [B5] | [e.g., averaged qsi_share instead of weighting] | [no SQL expression for fair share] | [added "fair share" SQL expression] | [2] |
| | | | | |

## What I learned

- [One or two sentences: which kind of fix helped most, such as descriptions or SQL expressions rather than more instructions]
- [Anything Genie still can't do reliably, and how you'd handle it in production]

---

## Brief agent evaluation (notebook 08)

| Run | Date | Model | Key numbers exact | Under word limit | Grounded (judge) | Tone (judge) | Change made |
|---|---|---|---|---|---|---|---|
| 1 | [date] | [endpoint] | [ ]% | [ ]% | [ ]% | [ ]% | Initial prompt |
| 2 | | | | | | | |

Notes: if "key numbers exact" is below 100%, open the failing traces in MLflow and check whether the model rounded, reformatted or dropped a number. Fix the prompt or the fact formatting, then re-run all 20.

---

## Automated runs (notebook 09)

Every run of notebook 09 (by hand, from the bundle job or from CI) appends 15 rows to `gold.genie_benchmark_runs`: status (PASS / FAIL / NO_SQL / ERROR), detail, Genie's SQL and latency. The monitoring dashboard (notebook 10) charts accuracy per run. Paste the summary of each run that changed something here:

| Date | Spec version | Passed | What changed |
|---|---|---|---|
| [date] | [hash] | [ ]/15 | First automated run |
