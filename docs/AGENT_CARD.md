# Agent card: Agency Performance Copilot (Genie Agent)

| Field | Value |
|---|---|
| **Purpose** | Answer account managers' questions about share, fair share (QSI), contract attainment, agency performance, NDC adoption, incentive cost and AAdvantage Business compliance |
| **Intended users** | Account managers and sales leaders (internal) |
| **Not for** | Anything sent to customers or agencies; contract or pricing decisions without human review; traveler-level lookups |
| **Risk tier** | Low: internal questions on aggregated data |
| **Data** | `gold.mv_account_performance`, `gold.mv_agency_performance`, `gold.account_market_month`, `gold.agency_month`, `gold.aadv_business_compliance` (synthetic) |
| **Freshness** | Monthly; latest month 2026-10 |
| **Certified metrics** | See `METRIC_DICTIONARY.md` |
| **Access model** | Runs as the asking user. Unity Catalog row filter by region; PNR masked; PNR excluded from the agent's tables |
| **Evaluation** | 15 benchmark questions with verified SQL. Release bar: ≥ 90% (14/15) and no wrong numbers on the attainment questions (B2–B4, B14) |
| **Latest score** | [X]/15 on [date] |
| **Known limitations** | [Fill in from benchmark failures you couldn't fully fix, for example multi-period comparisons or ambiguous "share"] |
| **Monitoring** | Genie Monitoring tab reviewed weekly; new question types added as benchmarks |
| **Owner** | Jayant Jaishwin Shanmugam Kavitha |
| **Version** | 1.0 |
| **Next review** | [date + 30 days] |

## Change log

| Date | Change | Benchmark before → after |
|---|---|---|
| [date] | Initial release | – → [X]/15 |

---

# Agent card: Pre-call brief agent (notebook 08)

| Field | Value |
|---|---|
| **Purpose** | Draft a short pre-call brief for an account manager: where the account stands, watch-outs, 2–3 talking points |
| **Intended users** | Account managers (internal), via Copilot Studio in Teams and the Deal Desk app |
| **Not for** | Sending to customers; contract or pricing decisions without human review |
| **Risk tier** | Low–medium: internal, but generated text could state a wrong number. Briefs are labelled "AI-drafted, review before use" |
| **Design** | One tool (`get_account_facts`) returns pre-computed, formatted facts from `gold.account_scorecard`. The LLM writes from those facts only and does no arithmetic |
| **Model** | First available `databricks-*` chat endpoint; template fallback if none |
| **Tracing** | MLflow 3: every tool call and LLM call traced (`@mlflow.trace`, OpenAI autolog) |
| **Evaluation** | 20 accounts (8 At risk, 6 Watch, 6 On track). Code scorers: key numbers exact, under word limit. LLM judges: grounded in facts, professional tone |
| **Release bar** | Key numbers exact = 100%; under word limit ≥ 95%; judges ≥ 90% |
| **Latest score** | [X] / [Y] / [Z] on [date] |
| **Owner** | Jayant Jaishwin Shanmugam Kavitha |
| **Version** | 1.0 |
