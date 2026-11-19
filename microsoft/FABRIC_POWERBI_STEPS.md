# Fabric + Power BI Direct Lake: step by step

**Goal:** the certified gold tables in a OneLake lakehouse, a Direct Lake semantic model with the same metric definitions as the Databricks metric views (built as code, checked for parity, exported as TMDL), and a two-page Power BI report.

**Time box:** 2–3 hours. **Stop rule:** if the Fabric trial won't activate within 20 minutes, use the fallback at the end.

---

## 0 · Account and trial (10–20 min)

Fabric needs a **work or school account** (Microsoft Entra ID), not Gmail. Use the account from your Microsoft 365 trial (for example `you@<tenant>.onmicrosoft.com` or your Webcattus address).

1. Go to `app.fabric.microsoft.com` and sign in with that account.
2. Profile icon (top right) → **Account manager** → **Start trial** (or **Free trial**) → pick a region → **Activate**. This is a 60-day trial capacity.
3. If you see *"Unable to create a free Microsoft Fabric trial capacity"*: create a workspace, then try to create a Lakehouse in it; Fabric sometimes offers the trial from there. Brand-new tenants are sometimes refused. If it still fails, **stop and use the fallback**.

## 1 · Workspace and lakehouse (5 min)

1. **Workspaces → New workspace** → name `agency-copilot` → under **Advanced**, choose the **Trial** license mode → Apply.
2. In the workspace: **New item → Lakehouse** → name `copilot_lakehouse`. **Untick "Lakehouse schemas"** if it's offered (keeps table names simple for the model generator).

## 2 · Run the notebook (15 min)

1. In the workspace: **Import → Notebook → From this computer** → choose `fabric/01_load_gold_to_lakehouse.ipynb` from your project folder (`Documents/agency-performance-copilot`).
2. Open it → left pane **Lakehouses → Add → Existing lakehouse** → `copilot_lakehouse`.
3. **Run all.** What you should see:
   - Section 1: ten tables loaded with row counts, and risk counts (At risk / Watch / On track).
   - Section 2: `Created Agency Performance (Direct Lake) · Direct Lake on OneLake`, then `Added 14 measures and 1 relationship`.
   - Section 3: **two PASS lines** ("largest difference" near 0), then *"Power BI and SQL agree on every number checked."* Central should be the weakest region.
   - Section 4: `Wrote N TMDL files` and the TMDL text of the **Contract Attainment** measure.
4. **Screenshot sections 3 and 4.** That's your proof of parity and TMDL.

If section 2 prints "Direct Lake on OneLake not available here", it fell back to Direct Lake on the SQL endpoint. Still Direct Lake; say which one honestly.

## 3 · The report (20–30 min)

Workspace → open the semantic model **Agency Performance (Direct Lake)** → **Create report → Start from scratch**.

**Page 1 · Sales performance** (filter pane: `account_market_month[month]` on or after 2026-01-01)

| Visual | Fields |
| --- | --- |
| 3 cards | `Share Gap (pts)`, `At-Risk Accounts` (filter segment = Managed), `AA Revenue` |
| Clustered bar | Y: `account_market_month[region]`, X: `Share Gap (pts)` |
| Clustered bar | Y: `account_market_month[account_manager]`, X: `Contract Attainment` (filter segment = Managed), sort ascending |
| Table | `account_scorecard[account_name]`, `risk_status`, `Contract Attainment`, `Share Gap (pts)`; sort by attainment ascending |

**Page 2 · Deal what-if** (page filter: segment = Managed, month on or after 2026-01-01)

| Visual | Fields |
| --- | --- |
| Slicer (single select, buttons) | `target_points[target_points]` |
| Slicer (dropdown) | `account_scorecard[account_name]` |
| 3 cards | `Contract Attainment` (current deal), `Scenario Attainment`, `Scenario Passenger Gap` |
| Table | `account_market_month[market_name]`, `Passenger Share`, `Fair Share (QSI)`, `Scenario Attainment` |

Save as **Agency Performance**. Move the slider from 0 to 15 for Zhang PLC: scenario attainment drops and the passenger gap grows, the same story as the Deal Desk app.

**Check values** (computed from the gold snapshot in pandas, independently of DAX). If a visual disagrees, a filter is missing.

| Where | Expected |
| --- | --- |
| Page 1 cards | Share gap +5.4 pts · At-risk managed accounts 69 · AA revenue $39.0M |
| Region bars | Central 2.4 · West 5.7 · Northeast 6.6 · Southeast 7.2 |
| Account manager bars (lowest) | Allison Hill 85.5% · Gabrielle Davis 92.6% · Angie Henderson 95.5% |
| Table (lowest) | Zhang PLC 27.2% · Turner, Schneider and Johnson 29.4% · Garcia, Martin and Jenkins 42.6% |
| Page 2, Zhang PLC | +0: 35.3% / gap 104 · +5: 32.1% / 120 · +10: 29.5% / 137 · +15: 27.2% / 153 · +20: 25.3% / 169 |

At +15 the scenario equals the current deal (27.2%) because Zhang's contract is fair share + 15. That is a built-in check that the what-if math and the contract math agree.

**Formatting as code.** `fabric/02_polish_report.py` (run as a Fabric notebook) reads the report's PBIR definition through the Fabric REST API, sets 1280×720 pages, the grid layout, titles, column names and red/amber/green rules, saves `Agency Performance (backup)`, then writes the result back with `updateDefinition`. Clicking through the web format panes doesn't scale; a definition edit is reviewable and repeatable.

## 4 · Optional: TMDL in GitHub (15 min)

Workspace settings → **Git integration** → GitHub → connect `jjaishwin/agency-performance-copilot`, folder `fabric/workspace`, branch `main` → Commit. The semantic model is stored as TMDL files; each measure change becomes a reviewable diff.

## What to say

> "The same gold tables feed Fabric. In production that's a mirrored Unity Catalog, no copy; here I loaded the snapshot. I built the Direct Lake model as code, re-implemented the metric views in DAX, and a parity check fails the notebook if any DAX number differs from SQL. The model is exported as TMDL, so measure changes go through Git like everything else."

Be precise: **"Direct Lake on OneLake on a Fabric trial; the data is a snapshot of the gold tables, not a live mirror."** The mirror needs Azure Databricks, which Free Edition isn't.

## Fallback if the Fabric trial won't activate

1. Power BI service (`app.powerbi.com`) with a **Power BI Pro trial** on the same work account.
2. In the Databricks SQL editor run `SELECT * FROM workspace.gold.account_market_month WHERE month >= '2026-01-01'` and download the result as CSV.
3. In Power BI, upload the CSV to **My workspace** (it becomes an import semantic model), open the model in the browser, add the measures from `microsoft/powerbi/measures.dax`, and build page 1. The exact menu names change often; look for "Upload" or "Get data".
4. Say: "Same DAX on an import model; Direct Lake needs Fabric capacity, which my trial tenant couldn't get."

Don't spend more than 45 minutes on the fallback.
