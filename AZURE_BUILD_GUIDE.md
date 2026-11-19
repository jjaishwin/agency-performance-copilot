# Azure build guide

This guide builds the project on the Azure Databricks + Microsoft stack: **Azure Databricks** (Delta Lake, Unity Catalog, Genie, Agent Bricks, Apps) as the data and AI platform, and **Microsoft Fabric, Power BI, Power Platform and Copilot Studio** where business users work.

```
                    ONE Microsoft Entra tenant (your Microsoft 365 trial)
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ Azure subscription ─► Azure Databricks Premium (East US 2)                                  │
│   notebooks 01–10: medallion · Unity Catalog · metric views · scorecards · Genie as code    │
│   11: Agent Bricks — Sales Copilot agent: Genie + UC functions + program docs (prototype)  │
│   12: fabric_share schema ─────────────► Fabric: Mirrored Azure Databricks Catalog          │
│                                                 ─► Direct Lake model ─► Power BI report     │
│                                                 ─► Git integration (TMDL in GitHub)         │
│   SQL warehouse ◄── Power Automate (Azure Databricks connector, Entra sign-in) ─► Teams     │
│   Genie Agent   ◄── Copilot Studio (Azure Databricks Genie tool over MCP) ─► Teams          │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Why one tenant matters:** when Azure Databricks, Fabric and Power Platform share an Entra tenant, every connection uses normal Entra sign-in (OAuth): no tokens, and mirroring and Copilot Studio work without service principals. Mixing tenants is the most common reason these integrations fail.

---

## What it costs and how long it takes

| Item | Cost | Your time |
|---|---|---|
| Microsoft 365 Business Standard trial | Free for 1 month (turn off recurring billing) | 15 min |
| Azure subscription | Pay-as-you-go is **required** (see Part 1). The new-account credit covers this project | 20 min |
| Azure Databricks **Trial (Premium – 14 days free DBUs)** | Databricks usage free for 14 days; you pay only small Azure costs (storage, networking) | 20 min |
| Fabric trial capacity | Free | 5 min |
| Power Apps Developer Plan / Power Automate and Copilot Studio trials | Free | 15 min |
| **Total** | Likely tens of dollars over two weeks if you stop compute when idle. **Set a budget alert at $25** | ~2 h setup before the notebooks |

**Cleanup when done:** delete the Azure resource group (removes the workspace and storage), cancel the M365 trial, and remove the payment method if you want.

---

## Part 0 · One identity

1. Finish the **Microsoft 365 Business Standard trial**. Your admin sign-in will look like `jay@<yourtenant>.onmicrosoft.com`.
2. Use **this account for everything below**: Azure portal, Databricks, Fabric, Power Automate, Copilot Studio. Don't use your Gmail; a personal account becomes a guest in the tenant, and guest accounts break Fabric mirroring.

## Part 1 · Azure subscription and Databricks workspace

1. Go to **portal.azure.com** and sign in with the tenant admin account. Start an Azure subscription in this tenant.
2. **Upgrade to pay-as-you-go.** Azure Databricks can't run on a Free Trial subscription: the 4-core limit blocks clusters. Upgrading keeps any remaining credit.
3. **Cost Management → Budgets → Add:** monthly budget $25, alert at 50% and 100%, to your email.
4. **Create a resource → Azure Databricks.**
   - Resource group `rg-agency-copilot`, name `adb-agency-copilot`.
   - **Region: East US 2.** Agent Bricks is available in centralus, eastus, eastus2, northcentralus, southcentralus, westus and westus2. Before you create the workspace, check that your region is on Fabric's supported-regions list for Azure Databricks mirroring.
   - **Pricing tier: Trial (Premium – 14-Days Free DBUs).**
   - Review + Create. Takes about 5 minutes.
5. **Launch workspace.** New workspaces have Unity Catalog and serverless enabled. Check that **SQL Warehouses** shows a serverless **Starter Warehouse**, and set its auto-stop to 10 minutes.
6. **Find your catalog name:** `SELECT current_catalog()`. New Azure workspaces usually create a catalog named after the workspace. Use that value in every notebook's **Catalog** widget, or in `--var catalog=` for the bundle.
7. **Turn on previews:** profile menu → **Previews**. Enable:
   - **Mosaic AI Agent Bricks Preview**
   - **Production monitoring for MLflow** (Supervisor tracing)
   - **Managed MCP Servers** (Copilot Studio's Genie tool)
   - Anything labeled **On-behalf-of-user authorization** for Apps, if listed.
8. **Serverless usage policy:** Settings → Compute → **Serverless usage policies** → create one with a small nonzero budget. The Supervisor Agent requires it.

**If quota or a preview blocks you:** request a vCPU quota increase (Subscriptions → Usage + quotas), or fall back to Free Edition for Parts 2–3.

## Part 2 · The pipeline (Azure Databricks)

1. **Workspace → Create → Git folder** with your GitHub repo URL.
2. Run notebooks **01 → 08** with your catalog name, then **12**. Or deploy everything at once:
   ```bash
   databricks auth login --host https://adb-<id>.<n>.azuredatabricks.net   # Entra sign-in in the browser
   databricks bundle deploy --var catalog=<catalog> --var warehouse_id=<id>
   databricks bundle run copilot_pipeline --var catalog=<catalog> --var warehouse_id=<id>
   ```
3. In notebook 05, add your own email to `gold.am_region_access` with `ALL`. Then add a second test user in the tenant (Microsoft 365 admin → Users) with `Northeast` only. That second user is how you demo the row filter, Genie and the app as a regional account manager.

## Part 3 · Genie Agent

1. Build it by hand once with `genie/GENIE_AGENT_SETUP.md`, so you know every setting.
2. Then run **notebook 09** to deploy the same agent as code and run the 15-benchmark gate, and **notebook 10** for the AI/BI dashboard (sales performance + monitoring).
3. **Share** the agent with your Northeast test user ("Can run"), and check their answers only cover Northeast.

## Part 4 · Agent Bricks: Knowledge Assistant and Supervisor Agent

> **Status, November 2026:** Databricks moved **Supervisor Agent and Knowledge Assistant to "legacy"** in its October 2026 release notes. They still work, which makes them the fastest way to prototype the multi-agent design below. For new production agents, Databricks recommends **Genie Agents** (no code) or the **Agent Bricks CLI** (code, deployed on Databricks Apps). This project prototypes with Supervisor Agent because it's the fastest path; the production version would be an Agent Bricks CLI agent using the same Genie Agent and UC functions as tools. Check that your region supports these features before you start.

Run **notebook 11** first. It writes 4 synthetic program documents to the volume `gold.program_docs`, creates the UC functions `account_snapshot`, `contract_what_if` and `agency_status`, and saves a 12-question routing evaluation set.

**4a. Knowledge Assistant: "Program Rules Assistant"**
1. **Agents → Knowledge Assistant → Build.**
2. Name `Program Rules Assistant`. Description: *"Answers questions about the corporate contract program, agency incentive rules, AAdvantage Business crediting and metric definitions. Synthetic demo documents."*
3. Knowledge source: **UC volume** `<catalog>.gold.program_docs`. Description: *"Program guides and metric definitions."*
4. Instructions: *"Answer only from the documents. Quote the rule and name the document. If the documents don't cover it, say so."*
5. **Create agent**, wait for it to finish building, then test: *"What happens when an agency misses its target two quarters in a row?"*

**4b. Supervisor Agent: "Sales Copilot"**
1. **Agents → Supervisor Agent → Build.**
2. Name `Sales Copilot`. Description: *"Helps airline account managers prepare for client and agency conversations. Synthetic demo data."*
3. Add subagents and tools. The **descriptions decide the routing**, so be specific:

| Add | Name | Description |
|---|---|---|
| Genie Agent | `Agency Performance Copilot` | Open analytical questions across accounts, markets, regions and agencies: passenger share, fair share (QSI), contract attainment, revenue, NDC, incentives, trends |
| Agent endpoint | `Program Rules Assistant` (from 4a) | Program rules and definitions: contract commitments, incentive rules, AAdvantage Business crediting, how metrics are defined |
| UC function | `<catalog>.gold.account_snapshot` | One named managed account: pre-call facts, risk status, weakest markets, talking points |
| UC function | `<catalog>.gold.contract_what_if` | One named account at a proposed commitment of QSI + 0, 5, 10 or 15: projected attainment and gap |
| UC function | `<catalog>.gold.agency_status` | One named travel agency's latest scorecard |

4. Instructions:
   ```
   You help account managers prepare for conversations. Use the tools for every number; never estimate.
   For a named account, use account_snapshot; for "what if we offer QSI + N", use contract_what_if.
   For rules or definitions, use Program Rules Assistant. For anything across many accounts, markets or agencies, use the Genie agent.
   When a question needs both data and rules, call both and combine them. Answer in under 150 words with the numbers first.
   ```
5. **Create agent**. Then ask each question in `gold.supervisor_routing_eval` in the test pane, and record the route it took and whether it was right. Note the score in `docs/EVAL_REPORT.md`.
6. Give your Northeast test user access to the supervisor **and** to each subagent: the Genie Agent, `CAN QUERY` on the Knowledge Assistant endpoint, `EXECUTE` on the functions. Check that they only get Northeast answers.

**Design note:** *"The supervisor doesn't do the math. Genie answers analytical questions on certified metrics, governed functions answer account-specific questions, and the Knowledge Assistant answers rules from documents. Each runs with the user's permissions, so the row filter applies end to end. I evaluate routing the same way I benchmark Genie."*

## Part 5 · Fabric: mirroring, Direct Lake, OneLake security, Git

1. **app.fabric.microsoft.com** → Account manager → **Start trial**. Create workspace `Agency Performance Copilot` on the trial capacity.
2. **New item → Mirrored Azure Databricks Catalog** → create the connection. It's **one shared credential** for every query from Fabric: your Entra account is fine for the demo, and a service principal is the production choice → choose your catalog → select **only the `fabric_share` schema**.
   - Mirroring can't read tables with row filters or column masks. That's why notebook 12 publishes `fabric_share` without them.
   - If Fabric can't reach the workspace storage, check the item's error message. The Azure storage account that holds the catalog must be reachable from Fabric. Grant access to the Fabric workspace identity, or use the connection's guided fix.
3. **OneLake security:** on the mirrored item, create roles per region, for example `Northeast` with `SELECT * FROM account_market_month WHERE region = 'Northeast'` and the same on the other region tables. Add the Northeast test user. Then compare row counts with notebook 12's parity cell. This re-applies the Unity Catalog rule. The trade-off: the rule now lives in two places, so it needs an owner and a parity test.
4. **New semantic model** in **Direct Lake on OneLake** mode (it honors OneLake security and never falls back to DirectQuery), named `Agency Performance Model`, with all tables. Relationships and measures as in `microsoft/MICROSOFT_LAYER_GUIDE.md` F3. Paste the measures from `microsoft/powerbi/measures.dax`. The table names are identical.
5. **Report**: the four pages from F4, including the `target_points` what-if.
6. **Git integration** → GitHub → `fabric/workspace`. The model is committed as **TMDL**, the report as **PBIR**.

## Part 6 · Power Automate: monthly scorecard to Teams (Azure Databricks connector)

1. Activate a **Power Automate Premium** trial (or the free **Power Apps Developer Plan**). The Azure Databricks connector is premium.
2. Create the connection in **Power Automate → Connections → New → Azure Databricks**:
   - Server hostname and HTTP path of the SQL warehouse.
   - **OAuth / Microsoft Entra ID**, since you're in the same tenant.
3. Scheduled cloud flow, Recurrence monthly on day 3:
   - **Azure Databricks → Execute a SQL Statement:** warehouse ID, statement `SELECT agency_name, agency_tier, status, summary FROM <catalog>.gold.agency_scorecard WHERE status IN ('Red','Amber') ORDER BY vs_target_pts LIMIT 25`, wait timeout `30s`.
   - **Select** from the result's `data_array` → **Create HTML table** → **Teams: Post message in a chat or channel**.
4. Because the connection uses your Entra identity, **Unity Catalog permissions apply to the flow**, with no token stored.

## Part 7 · Copilot Studio in Teams with the Genie tool

1. **copilotstudio.microsoft.com** → start a trial → **Create blank agent** `Account Manager Assistant`.
2. Instructions:
   ```
   You help airline account managers prepare for client calls. Use the Agency Performance Copilot tool for any data question and never estimate numbers.
   When the tool says it's still processing, wait for the full answer; do not stop after a few seconds.
   ```
   The last line matters: it stops the agent repeating "still processing" while Genie runs.
3. **Tools → + Add a tool →** search "Azure Databricks" → **Azure Databricks Genie** → your connection → **Add and configure**. Pick **Agency Performance Copilot** as the Genie Agent. Name the tool clearly.
4. Test with: *"Which accounts in the Northeast are at risk?"*. Then **Channels → Teams → Publish**. Screenshot it answering in Teams.
5. Optional: add the Supervisor Agent too, through its MCP endpoint (Agents → your supervisor → **Connect** shows the URL). Then Teams users get Genie, the program rules and the what-if tools in one agent.

## Part 8 · Deal Desk app and CI/CD

- `databricks bundle deploy` already created the **deal-desk** app with `sql` and `genie` user scopes. Start it with `databricks bundle run deal_desk`. Open it as yourself and as the Northeast user, and compare.
- In GitHub: CI signs in with **GitHub OIDC** (no stored token). Create a Databricks service principal with a federation policy trusting your repo (see the header of `.github/workflows/ci.yml`), then set repo variables `DATABRICKS_ENABLED=true`, `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` and `DATABRICKS_WAREHOUSE_ID`. Push a change to `GENIE_AGENT_SETUP.md` and watch the benchmark gate run.
- Databricks now also has a **Genie benchmark eval-runs API (Beta)** and bundle support for Genie Agents. Notebook 09's own comparison works today; switching the gate to the native eval-runs API is a good "next step" to mention.

---

