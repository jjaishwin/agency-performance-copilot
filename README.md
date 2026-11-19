# Agency Performance Copilot

**Governed AI and analytics for airline corporate and agency sales, on the Azure Databricks + Microsoft stack: Azure Databricks (Unity Catalog, Genie, Agent Bricks, Apps) as the foundation; Fabric, Power BI, Power Automate and Copilot Studio where account managers work.**

> All data in this project is synthetic and generated for demonstration. Company, agency and person names are invented. Competitor carriers are fictional (`XA`, `XB`). No American Airlines data is used.

## The problem

Corporate and agency sales teams cover more accounts than they have time for. Before a client call or a contract renewal, an account manager needs fast answers they can trust:

- Where are we below fair share for this account?
- Is the account on track for its contract target, and what target should we offer next?
- Which agencies are losing share, and is their incentive paying off?
- Are AAdvantage Business members actually getting credited?

Today those answers come from recurring manual reports and ad-hoc analyst requests.

## What this project does

```
Azure Databricks:
Raw files ─► Bronze ─► Silver ─► Gold ─► Governance ─► Metric views ─┬─► Genie Agent, deployed as code, 15-benchmark release gate
 CSV + Excel  audit    DQ+SCD2   grains   UC security   one definition ├─► Brief agent (LLM tool + MLflow evaluation)
                                                                      ├─► AI/BI dashboard: sales performance + AI and data quality
                                                                      ├─► Deal Desk app (what-if + Ask Genie, per-user security)
                                                                      ├─► Agent Bricks Supervisor (Genie + Knowledge Assistant + UC functions)
                                                                      └─► Fabric mirrored catalog ─► Direct Lake model ─┬─► Power BI report
                                                                                                                ├─► Power Automate → Teams
                                                                                                                └─► Copilot Studio agent in Teams
CI/CD: Declarative Automation Bundle (Lakeflow job 01→12 + app) · GitHub Actions · Genie gate fails the build · Fabric model in Git as TMDL
```

| Layer | What's built | Why it matters |
|---|---|---|
| **Bronze** | Raw CSVs and a legacy Excel workbook landed as-is, with `_source_file` and `_ingested_at` | Full audit trail back to the file |
| **Silver** | Typing, deduplication, data-quality checks, quarantine with reasons, reconciliation, SCD Type 2 agency history, Excel clean-up | Nothing is dropped silently; history survives agency re-parenting |
| **Gold** | Account × market × month, agency × month, AAdvantage Business compliance | One clear grain per table; weighted ratios only |
| **Scorecards and deals** | Quarterly agency scorecard (Green/Amber/Red), YTD account scorecard with risk status and talking points, contract scenarios at QSI + 0/5/10/15 | Replaces recurring manual reports; supports "modeling a good deal" |
| **Governance** | Business-language comments, tags, row filter by region, PNR column mask, lineage | Security in the data, inherited by every tool |
| **Semantic layer** | Unity Catalog metric views: passenger share, fair share (QSI), share gap, contract attainment, NDC share, incentive ROI | Each metric defined once; Genie, Power BI and the app agree |
| **Genie Agent** | Curated instructions, SQL expressions, example queries, entity matching, 15 core benchmarks + 10 advanced-SQL benchmarks | Plain-English answers for account managers, accuracy measured |
| **Genie as code + release gate** | Agent spec built from the guide, deployed with the Genie Management API; benchmarks run through the Conversation API, results logged, run fails below 90% | A Genie change is a reviewed pull request that can't make accuracy worse quietly |
| **Monitoring** | AI/BI dashboard created by API: accuracy per run, latest failures, data-quality failures, scorecard health | One place to answer "can we trust it?" |
| **Agent Bricks** | "Sales Copilot", prototyped as a Supervisor Agent (legacy since Oct 2026; the production path is the Agent Bricks CLI), routing between the Genie Agent, a Knowledge Assistant over program documents, and governed UC functions (account snapshot, contract what-if, agency status); 12-question routing evaluation | Multi-agent system built on the platform American uses, with the user's permissions end to end |
| **Brief agent** | Tool-calling LLM drafts pre-call briefs from governed facts; MLflow 3 tracing and evaluation | Numbers checked by code, tone and grounding by LLM judges |
| **Microsoft layer** | Fabric Mirrored Azure Databricks Catalog (no copy) of a `fabric_share` schema, OneLake security re-applying region access, Direct Lake semantic model (DAX matches the gold tables to 4 decimals), Power BI report with deal what-if, Power Automate monthly scorecard to Teams, Copilot Studio agent in Teams, model in Git as TMDL | Meets account managers in Power BI, Teams and Outlook |
| **Deal Desk app** | Databricks App: contract what-if and Ask Genie; runs as the signed-in user so the row filter applies; per-user caching | The deal-modeling step of the corporate contract lifecycle |
| **CI/CD** | Declarative Automation Bundle, formerly Databricks Asset Bundle (Lakeflow job + app), GitHub Actions: spec freshness, compile, deploy, Genie gate | One-command deploy; quality gates on every change |

![Architecture](docs/img/architecture.png)

## Results

| Measure | Value |
|---|---|
| Bookings processed | ~267,000 |
| Rows quarantined, with reasons | ~2,390 (duplicates, missing account IDs, unknown agencies, non-positive fares) |
| SMB bookings missing the AAdvantage Business ID | ~9% flagged |
| Agencies with SCD2 history | 8 |
| Agency scorecard (latest quarter) | 104 Green · 28 Amber · 68 Red |
| Managed accounts at risk (attainment < 90%) | 69 of 200 |
| Brief agent: key numbers exact / under word limit | **[X]% / [Y]%** on 20 evaluation accounts |
| Genie benchmark accuracy | **9/15 first run → [Y]/15 after root-cause fixes**; advanced SQL tier [ ]/10 (tracked, not gating) |

See [`docs/EVAL_REPORT.md`](docs/EVAL_REPORT.md) for the iteration log.

## Key design decisions

1. **Quarantine, don't drop.** Every failed row is kept with a reason, and counts reconcile exactly: bronze = silver + quarantine.
2. **SCD Type 2 for agencies.** Historical share stays with the parent company the agency had at the time.
3. **Weighted ratios only.** Share is `SUM(aa_pax) / SUM(total_pax)`, never an average of percentages.
4. **Low-QSI exclusion.** Markets where fair share is under 5% are excluded from "QSI + X" contract targets.
5. **Security at the data layer.** Row filters and masks live in Unity Catalog, so Genie, Power BI, the flow, the agent and the app can only see what their identity is allowed to see.
6. **The LLM never does arithmetic.** The brief agent receives pre-computed, formatted facts from a tool, and a code-based scorer checks that every number in the brief matches.
7. **Benchmarks as a release gate.** Any change to tables, instructions or expressions re-runs all 15 core benchmarks; an advanced tier (window functions, gaps and islands, anti-joins, pivots) is tracked separately. See `docs/ADVANCED_SQL.md`.
8. **Microsoft-first delivery.** Databricks is the governed foundation; account managers use the results where they already work.

## How to run it

1. **Azure Databricks Premium** in the same Entra tenant as Fabric and Power Platform: follow [`AZURE_BUILD_GUIDE.md`](AZURE_BUILD_GUIDE.md). Notebooks 01–10 also run on Databricks Free Edition.
2. **Workspace → Create → Git folder** with this repo's URL, then run notebooks 01 → 10 in order, or deploy everything with `databricks bundle deploy --var warehouse_id=<id>` and `databricks bundle run copilot_pipeline`.
3. Learn the Genie Agent by building it by hand with [`genie/GENIE_AGENT_SETUP.md`](genie/GENIE_AGENT_SETUP.md); notebook 09 deploys the same agent as code.
4. Build the Microsoft layer with [`microsoft/MICROSOFT_LAYER_GUIDE.md`](microsoft/MICROSOFT_LAYER_GUIDE.md).
5. Deploy the app with [`app/APP_SETUP.md`](app/APP_SETUP.md).

Full walkthrough: [`AZURE_BUILD_GUIDE.md`](AZURE_BUILD_GUIDE.md). Public demo (no sign-in, snapshot data): [`public_demo/`](public_demo/).

## Repository

```
notebooks/
  01_generate_synthetic_data.py   synthetic sources + planted defects + messy Excel
  02_bronze_ingest.py             raw landing with lineage columns
  03_silver_quality.py            DQ checks, quarantine, DQ log, Excel clean-up, SCD2
  04_gold_model.py                business tables at clear grains
  05_governance.py                comments, tags, row filter, column mask
  06_metric_views.py              certified metrics with MEASURE()
  07_scorecards_and_deals.py      agency + account scorecards, contract scenarios
  08_brief_agent_mlflow.py        LLM brief agent, MLflow tracing + evaluation
  09_genie_agent_as_code.py       deploy Genie via API, run benchmarks, release gate
  10_monitoring_dashboard.py      AI/BI dashboard via API (sales + monitoring pages)
  11_agent_bricks_prep.py         program docs, UC functions, routing eval for the Sales Copilot agent
  12_fabric_share.py              schema Fabric mirrors (no row filters) + OneLake parity check
AZURE_BUILD_GUIDE.md              the full build on Azure Databricks + Fabric + Power Platform
genie/GENIE_AGENT_SETUP.md        agent configuration + 15 core and 10 advanced benchmarks (source of truth)
genie/build_agent_spec.py         builds agent_spec.json (serialized_space) from the guide
dashboards/monitoring.lvdash.json dashboard definition
data/gold/*.parquet               gold tables exported for Fabric
fabric/                           Lakehouse loader notebook; workspace/ is written by Fabric Git integration (TMDL)
microsoft/powerbi/measures.dax    Direct Lake measures
databricks.yml                    Declarative Automation Bundle (formerly Asset Bundle): Lakeflow job + Deal Desk app
.github/workflows/ci.yml          CI/CD
microsoft/MICROSOFT_LAYER_GUIDE.md Power BI (DAX, what-if, TMDL), Power Automate, Copilot Studio, Fabric
app/                              Deal Desk: Databricks App (Streamlit)
docs/AGENT_CARD.md                purpose, data, limits, evaluation, owner (Genie + brief agent)
docs/METRIC_DICTIONARY.md         every certified metric, defined once
docs/EVAL_REPORT.md               benchmark results and iteration log
docs/ADVANCED_SQL.md              advanced SQL patterns: pipeline and Genie advanced tier
docs/BUSINESS_CASE.md             time-saved estimate with stated assumptions
```

## What's next

| Next | Purpose |
|---|---|
| Automated OneLake security parity test | Compare per-region row counts between Unity Catalog and OneLake on every deploy |
| Brief evaluation in CI | Add the MLflow evaluation of notebook 08 to the gate, next to the Genie benchmarks |
| Usage and cost monitoring | Genie and app usage from system tables on the monitoring dashboard |
