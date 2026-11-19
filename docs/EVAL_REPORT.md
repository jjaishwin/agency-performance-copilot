# Evaluation report: Agency Performance Copilot

**Method:** 15 benchmark questions (see `genie/GENIE_AGENT_SETUP.md`, section 6), each with a verified SQL answer. Genie's answer counts as correct when its result matches the verified result. All 15 are re-run after every change.

**Release bar:** ≥ 14/15, and no wrong numbers on the attainment questions (B2, B3, B4, B14).

## Results by run

| Run | Date | Change since last run | Score |
|---|---|---|---|
| 1 | 2026-11-18 | Baseline: agent deployed as code (notebook 09), metric views, 5 example queries, instructions | 9/15 (gate failed) |
| 2 | | Benchmark fixes (B5, B6, B10, B13) and two new definitions in the instructions (B12, B14) | [ ]/15 |

## Failures and root causes (run 1)

Each failure was sorted before anything changed: **benchmark design**, **ambiguous question**, or **real Genie mistake**. Only real mistakes are fixed in the agent; benchmark problems are fixed in the benchmark.

| Benchmark | What Genie did | Root cause | Fix |
|---|---|---|---|
| B5 | Correct markets, with share and fair share, but no gap column | Benchmark design: the question asks *which markets*; the expected answer required an extra column | Expected answer returns the markets only |
| B6 | Correct agencies, Q2 and Q3 shares; "drop" as a positive number | Benchmark design: expected answer used a negative "change" although the question says "drop" | Expected answer reports `share_drop = q2 - q3` |
| B10 | Correct cost and revenue by tier, no ratio | Benchmark design: the question never asks for revenue per incentive dollar | Ratio removed from the expected answer |
| B13 | Returned the single top parent TMC | Benchmark design: "which drove the most" is one TMC; expected answer listed all five | Expected answer `LIMIT 1` |
| B12 | Ranked by percent growth; expected was dollar growth | Ambiguous business definition | Instruction: "grew the most" means USD increase unless percent is asked (percent over-ranks small accounts) |
| B14 | Counted accounts at ≥ 90% for "at or above contract target" | **Real Genie mistake:** confused the 0.90 at-risk line with the 100% target | Instruction: on target means attainment ≥ 1.0; 0.90 only defines "at risk" |

The checker also now accepts a ratio where points were expected (×100), the mirror of the existing percent-vs-ratio rule.

## Advanced SQL tier (tracked, not gating)

Ten questions that need window functions, top-N per group, running totals, gaps and islands, an anti-join, a median and a pivot (see `docs/ADVANCED_SQL.md`). Reported separately by notebook 09 and on the dashboard; they show where Genie's limits are and where an analyst still writes the SQL.

| Run | Date | Spec version | Advanced passed | Notes |
|---|---|---|---|---|
| 1 | | | [ ]/10 | First run of the tier |

---

## Brief agent evaluation (notebook 08)

20 managed accounts (8 At risk, 6 Watch, 6 On track), model `databricks-gpt-oss-120b` on Databricks Free Edition, MLflow 3 GenAI evaluation. Release bar: 100% on the number checks (code), at least 90% on the LLM judges.

| Run | Date | Key numbers exact (code) | No invented numbers (code) | Under word limit (code) | Grounded / Actionable (judge) | Tone (judge) | Change made before this run |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-18 | 100% | (not yet built) | 95% | 30% | 0% | Initial prompt and judges |
| 2 | 2026-11-18 | 100% | 95% | 100% | 100% | 100% | Facts shown to the judge; specific judge rules; grounding moved to a code check; typographic hyphens normalized; 140-word prompt |
| 3 | 2026-11-18 | 100% | 95% (19 scored) | 100% | 90% | 95% | Numbers compared by value, not formatting |
| 4 | 2026-11-18 | 100% | 95% | 100% | 100% | 100% | Retries on model calls; empty output fails the eval; attainment target added as a fact |

### Failures and root causes

| Run | What the evaluation showed | Root cause | Fix |
|---|---|---|---|
| 1 | Tone 0%, grounding 30% | The judges, not the briefs. The grounding judge never saw the facts ("numbers are not part of the provided account facts"). The tone judge penalized the headings and bullets the prompt requires. | Facts passed to the judge; judge rules rewritten to be specific and consistent with the format; number grounding moved to code. |
| 1 | Model wrote `‑3.7%` and `ORD‑SLC` with U+2011 hyphens | Reasoning model typography | Normalize typographic hyphens before display and scoring. |
| 2 | `no_invented_numbers` flagged "110" | Check too literal: "110 %" vs fact "110.0%" is the same value | Compare numbers by value; formatting stays covered by `key_numbers_exact`. |
| 2 | Brief said "below the 90% risk line" | Suspected invented threshold. Traced: the phrase is in our own rule-based talking points (notebook 07), so the model was grounded. | None needed. Removed a prompt example that contradicted our own facts. |
| 3 | One brief was empty; every check errored on it | Model call raised (likely rate limit); no retry | Up to 3 attempts with backoff; empty output counts as a failure; the published table labels any template fallback. |
| 3 | "push attainment toward 100%" flagged | 100% is the real target but wasn't in the facts | Added `attainment_target: 100.0%` to the facts. |
| 4 | "Attainment remains 8.6 pts below target" flagged | The model did arithmetic (100.0 − 91.4). Correct here, but the rule is no recalculation: the next subtraction could be wrong. **The check worked as intended.** | Add the gap as a certified fact (`attainment_gap_pts`) so the model can quote it instead of computing it. Not yet re-run. |

### What I learned

- Read the judge's rationale before trusting a judge's score. Run 1's low scores measured the judge, not the model.
- Anything that can be checked exactly (numbers, length) is checked by code. LLM judges cover what code can't: tone and whether a suggestion is actionable.
- When the model wants a number, give it as a certified fact rather than asking it not to compute. Prompts reduce arithmetic; facts remove the need.

---

## Automated runs (notebook 09)

Every run of notebook 09 (by hand, from the bundle job or from CI) appends 15 rows to `gold.genie_benchmark_runs`: status (PASS / FAIL / NO_SQL / ERROR), detail, Genie's SQL and latency. The monitoring dashboard (notebook 10) charts accuracy per run. Paste the summary of each run that changed something here:

| Date | Spec version | Passed | What changed |
|---|---|---|---|
| [date] | [hash] | [ ]/15 | First automated run |
