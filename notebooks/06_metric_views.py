# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Metric views: define each metric once
# MAGIC
# MAGIC A **metric view** is a governed semantic layer inside Unity Catalog. Each business metric (passenger share, fair share, contract attainment) is defined **once**, with a description and synonyms. Genie, AI/BI dashboards and SQL users all get the **same number** for the same question.
# MAGIC
# MAGIC Why it matters: without a semantic layer, an LLM writing SQL can join wrong, average percentages, or misread a column, and still return a confident answer. With certified measures, the agent only picks *which* measure and *which* filters; the math is fixed.
# MAGIC
# MAGIC **Requirements:** a SQL warehouse or serverless compute on a recent runtime (Databricks Runtime 17.3+ for YAML 1.1). If you get a version error, change `version: 1.1` to `version: 0.1` and remove the `display_name` and `synonyms` lines.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
GOLD = f"{CATALOG}.gold"

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.mv_account_performance
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Certified account performance metrics for Global Sales: share, fair share (QSI) and contract attainment. Synthetic data."
source: {GOLD}.account_market_month

dimensions:
  - name: month
    expr: month
    comment: "First day of the travel month"
    display_name: "Month"
  - name: region
    expr: region
    display_name: "Region"
    synonyms: ['sales region', 'territory']
  - name: segment
    expr: segment
    comment: "Managed = contracted corporate account; SMB = AAdvantage Business small business"
    display_name: "Segment"
  - name: account_name
    expr: account_name
    display_name: "Account"
    synonyms: ['customer', 'corporate account', 'company']
  - name: account_manager
    expr: account_manager
    display_name: "Account Manager"
    synonyms: ['AM', 'sales rep', 'rep']
  - name: market_name
    expr: market_name
    comment: "Origin-destination market, for example DFW-LAX"
    display_name: "Market"
    synonyms: ['route', 'city pair', 'O&D']
  - name: qsi_eligible
    expr: qsi_eligible
    comment: "True when AA fair share is at least 5 percent"

measures:
  - name: aa_passengers
    expr: SUM(aa_pax)
    display_name: "AA Passengers"
  - name: total_passengers
    expr: SUM(total_pax)
    display_name: "Total Passengers"
  - name: aa_revenue
    expr: SUM(aa_revenue)
    display_name: "AA Revenue (USD)"
    synonyms: ['revenue', 'sales']
  - name: passenger_share
    expr: SUM(aa_pax) / SUM(total_pax)
    comment: "AA passengers divided by all-carrier passengers. The default meaning of share."
    display_name: "Passenger Share"
    synonyms: ['share', 'pax share', 'market share']
  - name: revenue_share
    expr: SUM(aa_revenue) / SUM(total_revenue)
    comment: "AA revenue divided by all-carrier revenue"
    display_name: "Revenue Share"
  - name: fair_share_qsi
    expr: SUM(qsi_share * total_pax) / SUM(total_pax)
    comment: "Passenger-weighted QSI fair share. Never average QSI percentages directly."
    display_name: "Fair Share (QSI)"
    synonyms: ['QSI', 'fair share', 'expected share']
  - name: share_vs_qsi_pts
    expr: (SUM(aa_pax) - SUM(qsi_share * total_pax)) / SUM(total_pax) * 100
    comment: "Passenger share minus fair share, in percentage points. Negative = below fair share."
    display_name: "Share vs QSI (pts)"
    synonyms: ['share gap', 'gap to fair share']
  - name: contract_attainment
    expr: SUM(CASE WHEN qsi_eligible AND target_share IS NOT NULL THEN aa_pax END) / SUM(CASE WHEN qsi_eligible AND target_share IS NOT NULL THEN target_share * total_pax END)
    comment: "Actual share divided by contracted target share, QSI-eligible markets only. Below 0.90 = at risk. Managed accounts only."
    display_name: "Contract Attainment"
    synonyms: ['attainment', 'contract performance', 'on track']
  - name: premium_mix
    expr: SUM(aa_premium_revenue) / SUM(aa_revenue)
    comment: "Share of AA revenue from premium cabins"
    display_name: "Premium Mix"
$$
""")
print("Created", f"{GOLD}.mv_account_performance")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.mv_agency_performance
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Certified agency performance metrics: revenue share, NDC adoption and incentive cost. Synthetic data."
source: {GOLD}.agency_month

dimensions:
  - name: month
    expr: month
    display_name: "Month"
  - name: agency_name
    expr: agency_name
    display_name: "Agency"
    synonyms: ['travel agency', 'TMC', 'OTA']
  - name: agency_tier
    expr: agency_tier
    comment: "TMC, OTA or Leisure"
    display_name: "Agency Tier"
  - name: parent_tmc
    expr: parent_tmc_asof
    comment: "Parent travel management company at the time of travel"
    display_name: "Parent TMC"

measures:
  - name: aa_revenue
    expr: SUM(aa_revenue)
    display_name: "AA Revenue (USD)"
  - name: revenue_share
    expr: SUM(aa_revenue) / SUM(total_revenue)
    comment: "AA share of the air revenue the agency sold"
    display_name: "Agency Revenue Share"
    synonyms: ['share', 'agency share']
  - name: ndc_share
    expr: SUM(aa_ndc_bookings) / SUM(aa_bookings)
    comment: "Share of the agency's AA bookings made through NDC"
    display_name: "NDC Share"
    synonyms: ['NDC adoption']
  - name: incentive_cost
    expr: SUM(incentive_cost_usd)
    display_name: "Incentive Cost (USD)"
    synonyms: ['commission', 'override']
  - name: revenue_per_incentive_dollar
    expr: SUM(aa_revenue) / SUM(incentive_cost_usd)
    comment: "AA revenue generated per dollar of incentive paid"
    display_name: "Revenue per Incentive $"
$$
""")
print("Created", f"{GOLD}.mv_agency_performance")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Query a metric view
# MAGIC Dimensions are ordinary columns; measures are wrapped in `MEASURE()`. The metric is computed correctly at whatever level you group by.

# COMMAND ----------

display(spark.sql(f"""
SELECT region,
       ROUND(MEASURE(passenger_share), 3)  AS passenger_share,
       ROUND(MEASURE(fair_share_qsi), 3)   AS fair_share,
       ROUND(MEASURE(share_vs_qsi_pts), 1) AS gap_pts
FROM {GOLD}.mv_account_performance
WHERE month >= DATE'2026-01-01'
GROUP BY region
ORDER BY gap_pts
"""))

# COMMAND ----------

display(spark.sql(f"""
SELECT account_manager,
       ROUND(MEASURE(contract_attainment), 3) AS attainment
FROM {GOLD}.mv_account_performance
WHERE month >= DATE'2026-01-01' AND segment = 'Managed'
GROUP BY account_manager
ORDER BY attainment
"""))
