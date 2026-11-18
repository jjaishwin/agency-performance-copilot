# Databricks notebook source
# MAGIC %md
# MAGIC # 11 · Agent Bricks: everything the Supervisor Agent needs
# MAGIC
# MAGIC **Azure Databricks Premium only.** Agent Bricks isn't available on Free Edition.
# MAGIC
# MAGIC The Supervisor Agent ("Sales Copilot") routes each question to the right specialist:
# MAGIC
# MAGIC | Subagent / tool | Type | Answers |
# MAGIC |---|---|---|
# MAGIC | Agency Performance Copilot | Genie Agent (notebook 09) | Open questions on share, fair share, attainment, agencies, NDC |
# MAGIC | Program Rules Assistant | Knowledge Assistant over the documents this notebook writes | "What happens when an agency misses its target?", "How is QSI defined?" |
# MAGIC | `account_snapshot` | Unity Catalog function | One account's pre-call facts and talking points |
# MAGIC | `contract_what_if` | Unity Catalog function | Attainment and gap if the contract were QSI + N points |
# MAGIC | `agency_status` | Unity Catalog function | One agency's scorecard status and summary |
# MAGIC
# MAGIC This notebook creates the documents, the three functions and a routing evaluation set. You create the Knowledge Assistant and the Supervisor in the UI (steps in `AZURE_BUILD_GUIDE.md`, Part 4).
# MAGIC
# MAGIC Functions run with the **caller's** permissions, so the Unity Catalog region row filter applies to every answer the supervisor gives.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
GOLD = f"{CATALOG}.gold"

# COMMAND ----------

# MAGIC %md ## 1 · Program documents for the Knowledge Assistant (synthetic)

# COMMAND ----------

DOCS = {
"01_corporate_contract_program.md": """# Corporate Contract Program Guide (SYNTHETIC DEMO DOCUMENT)

This document is invented for a portfolio project. It is not any airline's actual policy.

## Purpose
Managed corporate accounts receive negotiated fares in exchange for a share commitment. The commitment is expressed relative to fair share (QSI): for example, "QSI + 5 points" means the account commits to fly American at 5 percentage points above its fair share in eligible markets.

## Eligible markets
A market is eligible for the share commitment only when American's QSI share in that market is at least 5%. Markets below 5% are excluded, because a small absolute miss there would swing attainment.

## Measuring attainment
Contract attainment = actual American passengers in eligible markets / target passengers in eligible markets, where target passengers = (QSI share + commitment points, capped at 95%) x total passengers, computed market by market and month by month, then summed.

- On track: attainment of 100% or more.
- Watch: 90% to 100%.
- At risk: below 90%. The account manager prepares a recovery plan within 30 days.

## Renewal
Before renewal, the account manager models the next commitment at QSI + 0, 5, 10 and 15 points and compares projected attainment and the passenger gap. A commitment the account cannot reach is not offered, because missing it erodes trust in the program.
""",
"02_agency_incentive_program.md": """# Agency Incentive Program FY2026 (SYNTHETIC DEMO DOCUMENT)

This document is invented for a portfolio project. It is not any airline's actual policy.

## How incentives work
Each participating travel agency has a revenue share target and an incentive rate. Incentive cost = American revenue booked by the agency x incentive rate.

## Scorecard status (quarterly)
- Green: revenue share at or above target.
- Amber: within 5 percentage points below target.
- Red: more than 5 points below target.

## What happens when an agency misses its target
1. First Red quarter: the account manager reviews the agency's share trend, NDC adoption and top markets, and agrees an action plan with the agency.
2. Second consecutive Red quarter: the incentive rate is reviewed for the next program year.
3. Agencies with no target are reported as "No target" and are not scored.

## Return on incentive
Revenue per incentive dollar = American revenue / incentive cost. Leadership reviews tiers where this falls quarter over quarter.

## NDC
NDC share = American bookings made through NDC / all American bookings by the agency. Higher NDC adoption is a program goal.
""",
"03_aadvantage_business_crediting.md": """# AAdvantage Business Crediting Rules (SYNTHETIC DEMO DOCUMENT)

This document is invented for a portfolio project. It is not any airline's actual policy.

## Who it applies to
Small and medium-sized business (SMB) accounts enrolled in AAdvantage Business.

## Crediting
A booking earns business credit only when the AAdvantage Business ID is present on the reservation. Bookings without the ID earn no business credit and cannot be fixed after travel in this demo program.

## Compliance metric
Missing-ID rate = SMB American bookings without the business ID / all SMB American bookings. The sales team targets a missing-ID rate below 5%.

## Action
Accounts above 10% missing-ID rate for two consecutive months are contacted by their account manager with booking-tool setup instructions.
""",
"04_metric_definitions.md": """# Sales Metric Definitions (SYNTHETIC DEMO DOCUMENT)

- Passenger share: American passengers / all-carrier passengers. Always a ratio of sums, never an average of percentages.
- Revenue share: American revenue / all-carrier revenue.
- Fair share (QSI): the share American would be expected to win from its schedule quality, weighted by passengers: sum(QSI share x total passengers) / sum(total passengers).
- Share gap: passenger share minus fair share, in percentage points.
- Contract attainment: see the Corporate Contract Program Guide.
- Premium mix: American premium-cabin revenue / American revenue.
- Year to date: from January 1 through the latest complete month in the data.
""",
}

spark.sql(f"CREATE VOLUME IF NOT EXISTS {GOLD}.program_docs COMMENT 'Synthetic program documents for the Program Rules Assistant (Agent Bricks Knowledge Assistant).'")
base = f"/Volumes/{CATALOG}/gold/program_docs"
for name, text in DOCS.items():
    dbutils.fs.put(f"{base}/{name}", text, overwrite=True)
print("Wrote", len(DOCS), "documents to", base)

# COMMAND ----------

# MAGIC %md ## 2 · Unity Catalog functions the supervisor can call

# COMMAND ----------

FUNCTIONS = {
"account_snapshot": f"""
CREATE OR REPLACE FUNCTION {GOLD}.account_snapshot(account STRING COMMENT 'Managed account name, for example Davis Inc')
RETURNS TABLE (account_name STRING, region STRING, account_manager STRING, risk_status STRING,
               contract_attainment DOUBLE, passenger_share DOUBLE, fair_share DOUBLE, share_gap_pts DOUBLE,
               current_contract_pts INT, markets_below_fair_share STRING, talking_points STRING)
COMMENT 'Pre-call snapshot for one managed account, year to date: contract attainment, risk status, share versus fair share (QSI), the markets where American is below fair share, and talking points. Use for "prep me for my call with <account>" or "how is <account> doing".'
RETURN
  SELECT account_name, region, account_manager, risk_status,
         CAST(contract_attainment AS DOUBLE), CAST(passenger_share AS DOUBLE), CAST(fair_share AS DOUBLE),
         CAST(share_gap_pts AS DOUBLE), CAST(contract_pts AS INT), markets_below_fair_share, talking_points
  FROM {GOLD}.account_scorecard
  WHERE lower(account_name) = lower(trim(account))""",
"contract_what_if": f"""
CREATE OR REPLACE FUNCTION {GOLD}.contract_what_if(account STRING COMMENT 'Managed account name',
                                                  points INT COMMENT 'Commitment above fair share: 0, 5, 10 or 15')
RETURNS TABLE (account_name STRING, scenario_pts INT, is_current_contract BOOLEAN, target_share DOUBLE,
               projected_attainment DOUBLE, passenger_gap DOUBLE, revenue_gap_usd DOUBLE)
COMMENT 'Deal modelling: projected contract attainment, passenger gap and revenue gap if the account committed to QSI + points. Use for "what if we offer <account> QSI + 10".'
RETURN
  SELECT account_name, CAST(scenario_pts AS INT), is_current_contract, CAST(target_share AS DOUBLE),
         CAST(projected_attainment AS DOUBLE), CAST(passenger_gap AS DOUBLE), CAST(revenue_gap_usd AS DOUBLE)
  FROM {GOLD}.contract_scenarios
  WHERE lower(account_name) = lower(trim(account)) AND scenario_pts = points""",
"agency_status": f"""
CREATE OR REPLACE FUNCTION {GOLD}.agency_status(agency STRING COMMENT 'Travel agency name')
RETURNS TABLE (agency_name STRING, agency_tier STRING, status STRING, revenue_share DOUBLE,
               share_change_pts DOUBLE, vs_target_pts DOUBLE, ndc_share DOUBLE, summary STRING)
COMMENT 'Latest-quarter scorecard for one travel agency: Green/Amber/Red status, revenue share versus last quarter and versus target, NDC share, and a one-sentence summary.'
RETURN
  SELECT agency_name, agency_tier, status, CAST(revenue_share AS DOUBLE), CAST(share_change_pts AS DOUBLE),
         CAST(vs_target_pts AS DOUBLE), CAST(ndc_share AS DOUBLE), summary
  FROM {GOLD}.agency_scorecard
  WHERE lower(agency_name) = lower(trim(agency))""",
}
for name, ddl in FUNCTIONS.items():
    spark.sql(ddl)
    print("Created function", f"{GOLD}.{name}")

# Smoke test with real names.
acct = spark.sql(f"SELECT account_name FROM {GOLD}.account_scorecard WHERE risk_status = 'At risk' ORDER BY contract_attainment LIMIT 1").first()[0]
agency = spark.sql(f"SELECT agency_name FROM {GOLD}.agency_scorecard WHERE status = 'Red' LIMIT 1").first()[0]
display(spark.sql(f"SELECT * FROM {GOLD}.account_snapshot('{acct}')"))
display(spark.sql(f"SELECT * FROM {GOLD}.contract_what_if('{acct}', 5)"))
display(spark.sql(f"SELECT * FROM {GOLD}.agency_status('{agency.replace(chr(39), chr(39)*2)}')"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Routing evaluation set
# MAGIC
# MAGIC Questions with the subagent or tool the supervisor **should** pick. After building the supervisor, ask each question in its test pane (or add them as examples in its **Improve quality** tab) and record whether it routed correctly. Same idea as the Genie benchmarks, one level up.

# COMMAND ----------

ROUTING = [
    ("Which managed accounts are at risk this year?", "Genie Agent"),
    ("What is our share versus fair share by region in Q3 2026?", "Genie Agent"),
    ("Which agencies have the highest NDC adoption?", "Genie Agent"),
    (f"Prep me for my call with {acct}.", "account_snapshot"),
    (f"How is {acct} tracking against its contract?", "account_snapshot"),
    (f"What if we offered {acct} QSI plus 10 at renewal?", "contract_what_if"),
    (f"Would {acct} hit a QSI plus 5 commitment?", "contract_what_if"),
    (f"How is {agency} doing this quarter?", "agency_status"),
    ("What happens when an agency misses its incentive target?", "Knowledge Assistant"),
    ("How is contract attainment calculated?", "Knowledge Assistant"),
    ("Why don't SMB bookings without the business ID earn credit?", "Knowledge Assistant"),
    (f"{acct} is at risk. What does the program say I should do, and what are its weakest markets?", "account_snapshot + Knowledge Assistant"),
]
spark.createDataFrame(ROUTING, "question STRING, expected_route STRING") \
     .write.mode("overwrite").saveAsTable(f"{GOLD}.supervisor_routing_eval")
display(spark.table(f"{GOLD}.supervisor_routing_eval"))
