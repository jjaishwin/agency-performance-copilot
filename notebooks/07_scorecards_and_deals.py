# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Scorecards and deal scenarios
# MAGIC
# MAGIC Three gold tables that feed the Microsoft layer (Power BI, Power Automate, Copilot Studio) and the Deal Desk app:
# MAGIC
# MAGIC | Table | Grain | Who uses it |
# MAGIC |---|---|---|
# MAGIC | `agency_scorecard` | agency × quarter | Monthly agency scorecard: the "reporting for internal and external use" the Sales BI team produces. Status is Green/Amber/Red against each agency's target share, with a ready-to-send summary sentence. |
# MAGIC | `account_scorecard` | managed account, year to date | Pre-call facts for account managers: attainment, share gap, growth, the markets below fair share, rule-based talking points. Feeds the brief agent and Copilot. |
# MAGIC | `contract_scenarios` | managed account × target level | **Deal modeling:** if the contract were QSI + 0, 5, 10 or 15 points, what would attainment be, and how many passengers and dollars short would the account be? |
# MAGIC
# MAGIC Run after notebook 05 (it re-applies the region row filter to the new tables).

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
dbutils.widgets.text("quarter_start", "2026-07-01", "Scorecard quarter start")
dbutils.widgets.text("ytd_start", "2026-01-01", "Year-to-date start")
CATALOG = dbutils.widgets.get("catalog")
Q_START = dbutils.widgets.get("quarter_start")
YTD_START = dbutils.widgets.get("ytd_start")
GOLD = f"{CATALOG}.gold"

# COMMAND ----------

# MAGIC %md
# MAGIC ### Agency scorecard
# MAGIC Status rules: **Green** = at or above target share; **Amber** = within 5 points below; **Red** = more than 5 points below. Agencies with no target in the legacy workbook show **No target**.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.agency_scorecard AS
WITH cur AS (
  SELECT agency_id, first(agency_name) AS agency_name, first(agency_tier) AS agency_tier,
         first(parent_tmc_asof) AS parent_tmc,
         SUM(aa_revenue) AS aa_revenue, SUM(total_revenue) AS total_revenue,
         SUM(aa_ndc_bookings) AS ndc_bookings, SUM(aa_bookings) AS aa_bookings,
         SUM(incentive_cost_usd) AS incentive_cost_usd, max(target_aa_share) AS target_share
  FROM {GOLD}.agency_month
  WHERE month BETWEEN DATE'{Q_START}' AND add_months(DATE'{Q_START}', 2)
  GROUP BY agency_id
),
prev AS (
  SELECT agency_id, SUM(aa_revenue) / SUM(total_revenue) AS prev_revenue_share
  FROM {GOLD}.agency_month
  WHERE month BETWEEN add_months(DATE'{Q_START}', -3) AND add_months(DATE'{Q_START}', -1)
  GROUP BY agency_id
),
calc AS (
  SELECT c.*, DATE'{Q_START}' AS quarter_start,
         c.aa_revenue / c.total_revenue AS revenue_share,
         p.prev_revenue_share,
         (c.aa_revenue / c.total_revenue - p.prev_revenue_share) * 100 AS share_change_pts,
         c.ndc_bookings / c.aa_bookings AS ndc_share,
         c.aa_revenue / c.incentive_cost_usd AS revenue_per_incentive_dollar,
         (c.aa_revenue / c.total_revenue - c.target_share) * 100 AS vs_target_pts
  FROM cur c LEFT JOIN prev p ON c.agency_id = p.agency_id
)
SELECT agency_id, agency_name, agency_tier, parent_tmc, quarter_start,
       CAST(aa_revenue AS DECIMAL(14,2)) AS aa_revenue,
       ROUND(revenue_share, 4) AS revenue_share,
       ROUND(prev_revenue_share, 4) AS prev_revenue_share,
       ROUND(share_change_pts, 1) AS share_change_pts,
       ROUND(target_share, 4) AS target_share,
       ROUND(vs_target_pts, 1) AS vs_target_pts,
       ROUND(ndc_share, 4) AS ndc_share,
       CAST(incentive_cost_usd AS DECIMAL(14,2)) AS incentive_cost_usd,
       ROUND(revenue_per_incentive_dollar, 1) AS revenue_per_incentive_dollar,
       CASE WHEN target_share IS NULL THEN 'No target'
            WHEN revenue_share >= target_share THEN 'Green'
            WHEN revenue_share >= target_share - 0.05 THEN 'Amber'
            ELSE 'Red' END AS status,
       concat(
         agency_name, ': AA revenue share ', format_number(revenue_share * 100, 1), '%',
         CASE WHEN share_change_pts IS NULL THEN ''
              ELSE concat(' (', CASE WHEN share_change_pts >= 0 THEN '+' ELSE '' END,
                          format_number(share_change_pts, 1), ' pts vs last quarter)') END,
         CASE WHEN target_share IS NULL THEN '; no target on file'
              ELSE concat('; target ', format_number(target_share * 100, 0), '% (',
                          CASE WHEN vs_target_pts >= 0 THEN '+' ELSE '' END, format_number(vs_target_pts, 1), ' pts)') END,
         '; NDC ', format_number(ndc_share * 100, 0), '% of AA bookings',
         CASE WHEN incentive_cost_usd IS NULL THEN '; incentive rate TBD.'
              ELSE concat('; incentives $', format_number(incentive_cost_usd, 0), ' returned $',
                          format_number(revenue_per_incentive_dollar, 1), ' per $1.') END
       ) AS summary
FROM calc
""")
display(spark.sql(f"SELECT status, COUNT(*) AS agencies FROM {GOLD}.agency_scorecard GROUP BY status ORDER BY status"))
display(spark.sql(f"SELECT summary FROM {GOLD}.agency_scorecard WHERE status = 'Red' LIMIT 3"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Account scorecard (managed accounts, year to date)

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.account_scorecard AS
WITH ytd AS (
  SELECT * FROM {GOLD}.account_market_month
  WHERE segment = 'Managed' AND month >= DATE'{YTD_START}'
),
acct AS (
  SELECT account_id, first(account_name) AS account_name, first(region) AS region,
         first(account_manager) AS account_manager, first(account_manager_email) AS account_manager_email,
         first(share_target_vs_qsi_pts) AS contract_pts,
         SUM(aa_pax) / SUM(total_pax) AS passenger_share,
         SUM(qsi_share * total_pax) / SUM(total_pax) AS fair_share,
         SUM(CASE WHEN qsi_eligible THEN aa_pax END)
           / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END) AS contract_attainment,
         SUM(aa_revenue) AS aa_revenue_ytd,
         SUM(aa_premium_revenue) / SUM(aa_revenue) AS premium_mix
  FROM ytd GROUP BY account_id
),
prior AS (
  SELECT account_id, SUM(aa_revenue) AS aa_revenue_prior
  FROM {GOLD}.account_market_month
  WHERE segment = 'Managed'
    AND month BETWEEN add_months(DATE'{YTD_START}', -12)
                  AND add_months((SELECT max(month) FROM {GOLD}.account_market_month), -12)
  GROUP BY account_id
),
mkt AS (
  SELECT account_id, market_name, SUM(total_pax) AS total_pax,
         (SUM(aa_pax) - SUM(qsi_share * total_pax)) / SUM(total_pax) * 100 AS gap_pts
  FROM ytd GROUP BY account_id, market_name
),
weak AS (
  SELECT account_id,
         concat_ws(', ', slice(transform(array_sort(collect_list(struct(-total_pax AS k, market_name AS m))), x -> x.m), 1, 3)) AS markets_below_fair_share
  FROM mkt WHERE gap_pts < 0 GROUP BY account_id
)
SELECT a.account_id, a.account_name, a.region, a.account_manager, a.account_manager_email, a.contract_pts,
       ROUND(a.passenger_share, 4) AS passenger_share,
       ROUND(a.fair_share, 4) AS fair_share,
       ROUND((a.passenger_share - a.fair_share) * 100, 1) AS share_gap_pts,
       ROUND(a.contract_attainment, 4) AS contract_attainment,
       CAST(a.aa_revenue_ytd AS DECIMAL(14,2)) AS aa_revenue_ytd,
       ROUND((a.aa_revenue_ytd - p.aa_revenue_prior) / p.aa_revenue_prior * 100, 1) AS revenue_growth_pct,
       ROUND(a.premium_mix, 4) AS premium_mix,
       coalesce(w.markets_below_fair_share, 'none') AS markets_below_fair_share,
       CASE WHEN a.contract_attainment < 0.90 THEN 'At risk'
            WHEN a.contract_attainment < 1.00 THEN 'Watch'
            ELSE 'On track' END AS risk_status,
       concat_ws(' ',
         CASE WHEN a.contract_attainment < 0.90
              THEN concat('Attainment is ', format_number(a.contract_attainment * 100, 1), '%, below the 90% risk line: agree a recovery plan before renewal.')
              WHEN a.contract_attainment < 1.00
              THEN concat('Attainment is ', format_number(a.contract_attainment * 100, 1), '%: close to target, confirm upcoming travel.')
              ELSE concat('Attainment is ', format_number(a.contract_attainment * 100, 1), '%: on track, a good moment to discuss growth.') END,
         CASE WHEN w.markets_below_fair_share IS NOT NULL
              THEN concat('Below fair share in ', w.markets_below_fair_share, '.') END,
         CASE WHEN p.aa_revenue_prior IS NOT NULL AND a.aa_revenue_ytd < p.aa_revenue_prior
              THEN 'AA revenue is down year over year.' END
       ) AS talking_points
FROM acct a
LEFT JOIN prior p ON a.account_id = p.account_id
LEFT JOIN weak w ON a.account_id = w.account_id
""")
display(spark.sql(f"SELECT risk_status, COUNT(*) AS accounts FROM {GOLD}.account_scorecard GROUP BY risk_status"))
display(spark.sql(f"SELECT account_name, contract_attainment, markets_below_fair_share, talking_points FROM {GOLD}.account_scorecard ORDER BY contract_attainment LIMIT 3"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Contract scenarios: modelling the deal
# MAGIC For each managed account, using year-to-date traffic in QSI-eligible markets: what attainment would each target level produce, and what gap would the account need to close?
# MAGIC - `target_share` = passenger-weighted fair share + scenario points (capped at 95%)
# MAGIC - `passenger_gap` = passengers AA would need to add to reach the target
# MAGIC - `revenue_gap_usd` = that gap at the account's average AA fare

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.contract_scenarios AS
WITH base AS (
  SELECT account_id, first(account_name) AS account_name, first(region) AS region,
         first(account_manager) AS account_manager,
         first(share_target_vs_qsi_pts) AS current_contract_pts,
         SUM(aa_pax) AS aa_pax, SUM(total_pax) AS total_pax,
         SUM(qsi_share * total_pax) / SUM(total_pax) AS fair_share,
         SUM(aa_revenue) / SUM(aa_pax) AS avg_aa_fare
  FROM {GOLD}.account_market_month
  WHERE segment = 'Managed' AND qsi_eligible AND month >= DATE'{YTD_START}'
  GROUP BY account_id
),
grid AS (
  SELECT b.*, pts AS scenario_pts FROM base b LATERAL VIEW explode(array(0, 5, 10, 15)) s AS pts
)
SELECT account_id, account_name, region, account_manager, current_contract_pts, scenario_pts,
       scenario_pts = current_contract_pts AS is_current_contract,
       ROUND(aa_pax / total_pax, 4) AS passenger_share,
       ROUND(fair_share, 4) AS fair_share,
       ROUND(LEAST(fair_share + scenario_pts / 100.0, 0.95), 4) AS target_share,
       ROUND((aa_pax / total_pax) / LEAST(fair_share + scenario_pts / 100.0, 0.95), 4) AS projected_attainment,
       CAST(GREATEST(LEAST(fair_share + scenario_pts / 100.0, 0.95) * total_pax - aa_pax, 0) AS INT) AS passenger_gap,
       CAST(GREATEST(LEAST(fair_share + scenario_pts / 100.0, 0.95) * total_pax - aa_pax, 0) * avg_aa_fare AS DECIMAL(14,2)) AS revenue_gap_usd
FROM grid
""")
display(spark.sql(f"""
SELECT account_name, current_contract_pts, scenario_pts, projected_attainment, passenger_gap, revenue_gap_usd
FROM {GOLD}.contract_scenarios
WHERE account_id = (SELECT account_id FROM {GOLD}.account_scorecard ORDER BY contract_attainment LIMIT 1)
ORDER BY scenario_pts
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Governance for the new tables

# COMMAND ----------

comments = {
    "agency_scorecard": "Certified. Quarterly agency scorecard with status vs target and a summary sentence for distribution.",
    "account_scorecard": "Certified. Managed accounts year to date: attainment, share gap, growth, weak markets and talking points.",
    "contract_scenarios": "Deal modelling. Projected attainment and gap for each account at QSI + 0, 5, 10 and 15 points.",
}
for t, c in comments.items():
    spark.sql(f"COMMENT ON TABLE {GOLD}.{t} IS '{c}'")

try:
    for t in ["account_scorecard", "contract_scenarios"]:
        spark.sql(f"ALTER TABLE {GOLD}.{t} SET ROW FILTER {GOLD}.rf_region ON (region)")
    print("Row filter applied to account_scorecard and contract_scenarios")
except Exception as e:
    print("Row filter not applied (run notebook 05 first):", str(e)[:150])
