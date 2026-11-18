# Microsoft layer: Power BI, Power Automate, Copilot Studio, Fabric

> **Which guide to follow:** the architecture diagram shows the **Azure path** in [`AZURE_BUILD_GUIDE.md`](../AZURE_BUILD_GUIDE.md): Fabric mirrors Azure Databricks with no copy, and Power Automate and Copilot Studio use the native Azure Databricks connector. **This guide is the fallback** for Databricks Free Edition (not Azure). Fabric then loads a copy of the gold tables (`fabric/01_load_gold_to_lakehouse.ipynb`), and the flows query the semantic model. If you use this path, say so: it's a copy, not a mirror.

Databricks is the governed foundation. This layer is how account managers and sales leaders actually use it, in the Microsoft tools they already work in.

| Piece | What account managers get | Time | Account needed |
|---|---|---|---|
| **A. Power BI report** | Agency scorecard, share vs QSI, contract risk, deal what-if | 2–3 h | Power BI Desktop (free, Windows) |
| **B. Power Automate flow** | Monthly agency scorecard posted to Teams or email | 1–2 h | Microsoft 365 + Power Automate Premium (trial) |
| **C. Copilot Studio agent** | "Prep me for my call with Acme" in Teams | 2 h | Copilot Studio (trial) |
| **D. Fabric + Direct Lake + TMDL** | Same report on Direct Lake, model versioned in Git | 2 h | Fabric trial |

**About accounts:** Copilot Studio, Power Automate Premium and Fabric trials usually require a work or school email. One option is a Microsoft 365 Business trial on your Webcattus Labs domain. If you can't get a trial, build A, and document B–D as designed with the exact configuration below. That's still a strong answer: "Here's the flow and the agent design; I didn't have a tenant to publish to."

---

## Path for a Mac with a Microsoft 365 trial: everything in the browser

Power BI Desktop is Windows-only, so on a Mac everything runs in **Fabric in the browser**. This is the path the project uses. Every Microsoft piece reads **one certified semantic model**, so the report, the flow and the Teams agent all use the same measures.

```
GitHub data/gold/*.parquet ─► Fabric Lakehouse (Delta) ─► Direct Lake semantic model (measures.dax)
                                                           ├─► Power BI report (4 pages)
                                                           ├─► Power Automate: monthly scorecard → Teams   (Power BI connector, DAX query)
                                                           └─► Copilot Studio agent in Teams               (agent flow, DAX query)
Fabric workspace ─► Git integration ─► GitHub /fabric/workspace (semantic model as TMDL, report as PBIR)
```

**F1. Fabric trial and workspace.** Go to app.fabric.microsoft.com, open **Account manager → Start trial**, and create a workspace `Agency Performance Copilot` on the trial capacity.

**F2. Lakehouse.** New item → **Lakehouse** → `copilot_lakehouse`. Then **Import → Notebook** → `fabric/01_load_gold_to_lakehouse.ipynb`. Attach the Lakehouse, set `GITHUB_RAW` to your repo, and **Run all**. You should see 69 at-risk accounts in the last cell.

**F3. Semantic model.** From the Lakehouse: **New semantic model** → `Agency Performance Model` → select all 10 tables. In the model view:
- Relationships (many-to-one, single direction):
  - `account_market_month[account_id]` → `dim_account[account_id]`
  - `account_market_month[market_id]` → `dim_market[market_id]`
- Leave `target_points` **disconnected**. It's the what-if slicer.
- **New measure** for each measure in `microsoft/powerbi/measures.dax`, put in `account_market_month`. Set percentage format on the share, attainment and NDC measures.
- **Check:** a table of `account_name` with **Contract Attainment**, filtered to Managed and 2026, matches `account_scorecard[contract_attainment]` to 4 decimal places. I checked this on the exported data.

**F4. Report.** From the model: **Create report** → build the four pages in A5. On **Deal What-If**, use a slicer on `target_points[target_points]` with the **Scenario Attainment** and **Scenario Passenger Gap** cards. Save as `Agency Performance Scorecards`.

**F5. Git integration (TMDL in Git).** Workspace settings → **Git integration** → GitHub → your repo, branch `main`, folder `fabric/workspace` → **Commit**. The semantic model lands in GitHub as **TMDL** and the report as **PBIR**. That's real "model as code" with no Power BI Desktop.

**F6. Power Automate: monthly scorecard to Teams (standard connectors only).** Scheduled cloud flow, Recurrence monthly on day 3, 8:00 Central.
- **Power BI → Run a query against a dataset**: workspace `Agency Performance Copilot`, dataset `Agency Performance Model`, query:
  ```DAX
  EVALUATE
  SELECTCOLUMNS (
      FILTER ( agency_scorecard, agency_scorecard[status] <> "Green" ),
      "Agency", agency_scorecard[agency_name],
      "Tier", agency_scorecard[agency_tier],
      "Status", agency_scorecard[status],
      "Summary", agency_scorecard[summary]
  )
  ORDER BY [Status] DESC, [Agency]
  ```
- **Create HTML table** from `First table rows`.
- **Microsoft Teams → Post message in a chat or channel**: subject "Agency scorecard: agencies below target", body = the HTML table.
- Then **Test → Manually** and screenshot the Teams message.

Because the flow queries the semantic model and not raw tables, the numbers are the certified ones, and no database password or token sits in the flow.

**F7. Copilot Studio: Account Manager Assistant.** Create an agent with the instructions in C1. Then add a tool → **New agent flow** `Get account brief`:
- Input `account_name` (text).
- **Compose** `safe_name` = `replace(triggerBody()?['text'], '"', '""')`. This escapes quotes so a user can't break out of the DAX string.
- **Power BI → Run a query against a dataset**, same dataset:
  ```DAX
  EVALUATE
  VAR n = "@{outputs('safe_name')}"
  RETURN
  SELECTCOLUMNS (
      FILTER ( account_scorecard, account_scorecard[account_name] = n ),
      "attainment", FORMAT ( account_scorecard[contract_attainment], "0.0%" ),
      "risk", account_scorecard[risk_status],
      "share_gap_pts", FORMAT ( account_scorecard[share_gap_pts], "+0.0;-0.0" ),
      "below_fair_share", account_scorecard[markets_below_fair_share],
      "talking_points", account_scorecard[talking_points],
      "brief", LOOKUPVALUE ( account_briefs[brief], account_briefs[account_name], n )
  )
  ```
- **Respond to the agent** with the first row as text (`string(first(body('Run_a_query_against_a_dataset')?['firstTableRows']))`).
- Test it ("Prep me for my call with <an at-risk account>"), then **Channels → Teams → Publish**. Screenshot it answering in Teams.

---

## A. Power BI report

### A1. Connect to Databricks

1. In Databricks: **SQL Warehouses → your warehouse → Connection details.** Copy the **Server hostname** and **HTTP path**.
2. Create a token: **User settings → Developer → Access tokens → Generate new token** (30 days).
3. In Power BI Desktop: **Get data → Databricks** (or **Azure Databricks**). Paste the hostname and HTTP path, choose **Import**, then sign in with **Personal Access Token**.
4. Select from `workspace.gold`: `account_market_month`, `agency_month`, `agency_scorecard`, `account_scorecard`, `contract_scenarios`, `dim_account`, `dim_market`, and `account_briefs` if you ran notebook 08.

If your workspace blocks external connections, export the gold tables to CSV from a notebook (`df.toPandas().to_csv("/Volumes/workspace/bronze/landing/exports/…")`), download them, and import the CSVs instead.

**Mac users:** Power BI Desktop is Windows-only. Use a Windows VM, or build the same pages as a Databricks AI/BI dashboard and say so.

### A2. Model

- **Date table:** Modeling → New table: `Date = CALENDAR(DATE(2024,11,1), DATE(2026,10,31))`, add `Month = STARTOFMONTH('Date'[Date])`, and mark it as a date table.
- **Relationships (single direction, many-to-one):**
  - `account_market_month[month]` → `Date[Date]`
  - `agency_month[month]` → `Date[Date]`
  - `account_market_month[account_id]` → `dim_account[account_id]`
  - `account_market_month[market_id]` → `dim_market[market_id]`
- Hide raw numeric columns from report view once the measures exist, so people use measures, not sums.

### A3. Measures (DAX)

Create a **Measures** table (Enter data → blank) and add these. They match `docs/METRIC_DICTIONARY.md` exactly, so Power BI and Genie agree.

```DAX
Passenger Share =
DIVIDE ( SUM ( account_market_month[aa_pax] ), SUM ( account_market_month[total_pax] ) )

Revenue Share =
DIVIDE ( SUM ( account_market_month[aa_revenue] ), SUM ( account_market_month[total_revenue] ) )

Fair Share (QSI) =
DIVIDE (
    SUMX ( account_market_month, account_market_month[qsi_share] * account_market_month[total_pax] ),
    SUM ( account_market_month[total_pax] )
)

Share Gap (pts) =
( [Passenger Share] - [Fair Share (QSI)] ) * 100

Contract Attainment =
DIVIDE (
    CALCULATE ( SUM ( account_market_month[aa_pax] ), account_market_month[qsi_eligible] = TRUE () ),
    CALCULATE (
        SUMX ( account_market_month, account_market_month[target_share] * account_market_month[total_pax] ),
        account_market_month[qsi_eligible] = TRUE ()
    )
)

At-Risk Accounts =
COUNTROWS (
    FILTER (
        VALUES ( dim_account[account_id] ),
        NOT ISBLANK ( [Contract Attainment] ) && [Contract Attainment] < 0.90
    )
)

Agency Revenue Share =
DIVIDE ( SUM ( agency_month[aa_revenue] ), SUM ( agency_month[total_revenue] ) )

NDC Share =
DIVIDE ( SUM ( agency_month[aa_ndc_bookings] ), SUM ( agency_month[aa_bookings] ) )

Revenue per Incentive $ =
DIVIDE ( SUM ( agency_month[aa_revenue] ), SUM ( agency_month[incentive_cost_usd] ) )
```

### A4. Deal what-if (modeling a contract target)

1. **Modeling → New parameter → Numeric range:** name `Target Points`, 0 to 20, increment 5, default 10. This creates a slicer and a `[Target Points Value]` measure.
2. Add:

```DAX
Scenario Target Share =
DIVIDE (
    SUMX (
        FILTER ( account_market_month, account_market_month[qsi_eligible] ),
        MIN ( account_market_month[qsi_share] + [Target Points Value] / 100, 0.95 ) * account_market_month[total_pax]
    ),
    CALCULATE ( SUM ( account_market_month[total_pax] ), account_market_month[qsi_eligible] = TRUE () )
)

Scenario Attainment =
DIVIDE (
    CALCULATE ( SUM ( account_market_month[aa_pax] ), account_market_month[qsi_eligible] = TRUE () ),
    SUMX (
        FILTER ( account_market_month, account_market_month[qsi_eligible] ),
        MIN ( account_market_month[qsi_share] + [Target Points Value] / 100, 0.95 ) * account_market_month[total_pax]
    )
)

Scenario Passenger Gap =
MAX (
    0,
    SUMX (
        FILTER ( account_market_month, account_market_month[qsi_eligible] ),
        MIN ( account_market_month[qsi_share] + [Target Points Value] / 100, 0.95 ) * account_market_month[total_pax]
    ) - CALCULATE ( SUM ( account_market_month[aa_pax] ), account_market_month[qsi_eligible] = TRUE () )
)
```

These compute the target row by row, then aggregate, the same way `contract_scenarios` does. I checked on the exported data: every account matches the table to within 0.0001.

### A5. Pages

| Page | Visuals |
|---|---|
| **1. Agency Scorecard** | Table from `agency_scorecard`: agency, tier, revenue share, change vs last quarter, target, status (conditional formatting: Green/Amber/Red), revenue per incentive $. Slicers: tier, parent TMC |
| **2. Share vs Fair Share** | Matrix region → account with Passenger Share, Fair Share, Share Gap; scatter of accounts (x = Fair Share, y = Passenger Share) with a diagonal reference line |
| **3. Contract Risk** | Cards: At-Risk Accounts, average attainment. Bar: attainment by account manager. Table from `account_scorecard` filtered to "At risk" with talking points |
| **4. Deal What-If** | Account slicer, `Target Points` slicer, cards for Scenario Attainment and Scenario Passenger Gap, line chart of monthly Passenger Share vs Scenario Target Share |
| **5. Brief** (optional) | Table from `account_briefs` |

### A6. Save as a project and get TMDL

**File → Save as → Power BI project (.pbip).** The semantic model is saved as TMDL text files under `*.SemanticModel/definition/`. Open **TMDL view** in Desktop to see and edit measures as code. Commit the `.pbip` folder to the `powerbi/` folder of your GitHub repo.

**Why it matters:** *"The semantic model is versioned as TMDL in Git, so a change to a measure is reviewed like any other code change, and the DAX matches the metric dictionary that Genie uses."*

---

## B. Power Automate: monthly agency scorecard

**Goal:** on the 3rd of each month, post the Red and Amber agencies to a Teams channel (or email each account manager).

### B1. Databricks pieces
- **Warehouse ID:** from the warehouse URL, or Connection details.
- **Token:** a PAT for the demo. In production, use a service principal with OAuth and store secrets in Azure Key Vault.
- **Row filter:** the identity the flow uses must be in `gold.am_region_access`, or it will see no rows. That's governance working as intended, and a good thing to mention.

### B2. Flow steps
1. **Trigger: Recurrence.** Frequency Month, interval 1, on day 3 at 08:00 Central.
2. **HTTP** (Premium). Method `POST`, URI `https://<workspace-host>/api/2.0/sql/statements/`.
   Headers: `Authorization: Bearer <token>`, `Content-Type: application/json`. Body:
   ```json
   {
     "warehouse_id": "<warehouse-id>",
     "statement": "SELECT agency_name, agency_tier, status, summary FROM workspace.gold.agency_scorecard WHERE status IN ('Red', 'Amber') ORDER BY vs_target_pts LIMIT 25",
     "wait_timeout": "30s",
     "disposition": "INLINE",
     "format": "JSON_ARRAY"
   }
   ```
3. **Select.** From `@body('HTTP')?['result']?['data_array']`, map:
   - `Agency` → `@item()[0]`
   - `Tier` → `@item()[1]`
   - `Status` → `@item()[2]`
   - `Summary` → `@item()[3]`
4. **Create HTML table** from the Select output.
5. **Post message in a chat or channel** (Teams), or **Send an email (V2)** (Outlook). Subject: `Agency scorecard: agencies below target, @{formatDateTime(utcNow(),'MMMM yyyy')}`. Body: one intro line plus the HTML table.
6. **Error handling:** add a parallel branch that runs if HTTP fails or times out, and posts "Scorecard failed: check the warehouse" to the same channel. Silent failures erode trust.

**Stretch:** loop over account managers using `account_manager_email` from `account_scorecard`, and send each one only their at-risk accounts with the `talking_points` column.

**Why it matters:** *"The scorecard used to be a manual monthly report. Now it's a governed query and a scheduled flow, so account managers get it in Teams on the 3rd without an analyst touching it."*

---

## C. Copilot Studio: Account Manager Assistant in Teams

### C1. Create the agent
1. **Copilot Studio → Create → New agent.** Name: `Account Manager Assistant`.
2. **Instructions:**
   ```
   You help airline account managers prepare for client calls. Use only the data returned by your tools; never estimate numbers.
   When asked about an account, call "Get account brief" with the account name, then answer with: where we stand, watch-outs and 2-3 talking points.
   If the account isn't found, ask the user to check the name. Internal use only; synthetic demo data.
   ```

### C2. Add a tool: an agent flow "Get account brief"
1. **Tools → Add a tool → New agent flow.**
2. **Input:** `account_name` (text).
3. **HTTP** (as in B2) with:
   ```json
   {
     "warehouse_id": "<warehouse-id>",
     "statement": "SELECT s.contract_attainment, s.risk_status, s.passenger_share, s.fair_share, s.share_gap_pts, s.markets_below_fair_share, s.talking_points, b.brief FROM workspace.gold.account_scorecard s LEFT JOIN workspace.gold.account_briefs b ON s.account_name = b.account_name WHERE s.account_name = :name",
     "parameters": [{ "name": "name", "value": "@{triggerBody()?['text']}", "type": "STRING" }],
     "wait_timeout": "30s",
     "disposition": "INLINE",
     "format": "JSON_ARRAY"
   }
   ```
   For the `value`, pick the `account_name` input from the dynamic content list. The expression's exact name depends on how you labelled the input. The `:name` parameter prevents SQL injection: never paste user text straight into SQL.
4. **Respond to the agent** with the first row as text: the brief if it exists, otherwise the scorecard fields.

### C3. Test and publish
- Test with: *"Prep me for my call with [an at-risk account name]."*
- **Channels → Microsoft Teams → Publish.** Screenshot the agent answering in Teams.

### C4. With Azure Databricks
If you have an Azure Databricks workspace, add the **Azure Databricks Genie** tool in Copilot Studio instead of (or as well as) the flow, pointing at your Genie Agent. Then the Teams agent can answer open-ended questions with Genie's benchmarked SQL. Databricks Free Edition isn't on Azure, which is why the flow approach is the default here.

**Why it matters:** *"Account managers live in Teams and Outlook, so the front door is Copilot Studio. The agent never touches raw data: it calls a governed query or the Genie Agent, and Unity Catalog security still applies."*

---

## D. Fabric, Direct Lake and TMDL (optional)

1. Start a **Fabric trial** and create a workspace and a **Lakehouse**.
2. Load the gold tables: upload the CSV exports from A1, then **Load to Tables** (Delta in OneLake).
3. **New semantic model** from the Lakehouse tables. This is a **Direct Lake** model: it reads Delta files from OneLake directly, with no import refresh.
4. Rebuild the A3 measures (or paste them in TMDL view) and point the A5 report at this model.
5. Compare the two: Import (A) copies data and needs scheduled refresh; Direct Lake (D) reads OneLake with near-import speed and "framing" refreshes that take seconds.

**In a real American setup:** gold tables would reach Fabric through the **Mirrored Azure Databricks Catalog** (no copy). But mirroring moves data, not grants: Unity Catalog permissions aren't mirrored, so access has to be re-applied in OneLake security on the same Entra ID groups, and tested for parity. Raising that one point shows you understand the governance problem his team has to solve.
