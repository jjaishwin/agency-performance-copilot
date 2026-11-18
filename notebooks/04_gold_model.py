# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Gold: business-ready tables
# MAGIC
# MAGIC **Gold is for meaning.** These are the tables the Genie Agent, dashboards and any future agent read.
# MAGIC
# MAGIC | Table | Grain | Used for |
# MAGIC |---|---|---|
# MAGIC | `dim_account` | one row per account | names, segment, region, account manager |
# MAGIC | `dim_market` | one row per market | origin, destination |
# MAGIC | `dim_agency_history` / `dim_agency_current` | SCD2 / current | agency attributes, as-of joins |
# MAGIC | `fact_booking` | one row per ticket | detail, drill-down, PII masking demo |
# MAGIC | `account_market_month` | account × market × month | **share, fair share (QSI), contract attainment** |
# MAGIC | `agency_month` | agency × month | **agency revenue share, NDC share, incentive cost** |
# MAGIC | `aadv_business_compliance` | SMB account × month | **missing AAdvantage Business IDs** |
# MAGIC
# MAGIC Two modelling rules are enforced here, so every consumer inherits them:
# MAGIC - Agency attributes are joined **as of the travel date** (SCD2), so history doesn't change when an agency is re-parented.
# MAGIC - `qsi_eligible` marks markets where AA's fair share is below 5%; "QSI + X" contract targets exclude them because they distort the goal.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
SILVER, GOLD = f"{CATALOG}.silver", f"{CATALOG}.gold"

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.dim_account AS
SELECT a.account_id, a.account_name, a.segment, a.region, a.am_id,
       m.am_name AS account_manager, m.am_email AS account_manager_email, a.aadv_business_id
FROM {SILVER}.accounts a
LEFT JOIN {SILVER}.account_managers m ON a.am_id = m.am_id
""")

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.dim_market AS
SELECT market_id, origin, destination, concat(origin, '-', destination) AS market_name,
       region, nonstop_flag, international_flag
FROM {SILVER}.markets
""")

spark.sql(f"CREATE OR REPLACE TABLE {GOLD}.dim_agency_history AS SELECT * FROM {SILVER}.dim_agency")
spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.dim_agency_current AS
SELECT agency_id, arc_number, agency_name, tier, region, parent_tmc
FROM {GOLD}.dim_agency_history WHERE is_current
""")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.fact_booking AS
SELECT b.ticket_id, b.booking_date, b.travel_date,
       CAST(date_trunc('MONTH', b.travel_date) AS DATE) AS month,
       b.account_id, a.account_name, a.segment, a.region, a.account_manager,
       b.agency_id, ag.agency_name, ag.tier AS agency_tier, ag.parent_tmc AS parent_tmc_asof,
       b.market_id, mk.market_name,
       b.carrier, b.cabin, b.channel, b.pax, b.revenue_usd, b.aadv_business_id, b.pnr
FROM {SILVER}.bookings b
JOIN {GOLD}.dim_account a ON b.account_id = a.account_id
JOIN {GOLD}.dim_market mk ON b.market_id = mk.market_id
LEFT JOIN {GOLD}.dim_agency_history ag
  ON b.agency_id = ag.agency_id
 AND b.travel_date >= ag.effective_from
 AND b.travel_date <= coalesce(ag.effective_to, DATE'9999-12-31')
""")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.account_market_month AS
WITH agg AS (
  SELECT account_id, market_id, month,
         SUM(CASE WHEN carrier = 'AA' THEN pax ELSE 0 END)                         AS aa_pax,
         SUM(pax)                                                                  AS total_pax,
         SUM(CASE WHEN carrier = 'AA' THEN revenue_usd ELSE 0 END)                 AS aa_revenue,
         SUM(revenue_usd)                                                          AS total_revenue,
         SUM(CASE WHEN carrier = 'AA' AND cabin = 'Premium' THEN revenue_usd ELSE 0 END) AS aa_premium_revenue
  FROM {GOLD}.fact_booking
  GROUP BY account_id, market_id, month
)
SELECT g.month, g.account_id, a.account_name, a.segment, a.region, a.account_manager, a.account_manager_email,
       g.market_id, m.market_name,
       g.aa_pax, g.total_pax, g.aa_revenue, g.total_revenue, g.aa_premium_revenue,
       q.qsi_share,
       q.qsi_share >= 0.05 AS qsi_eligible,
       c.share_target_vs_qsi_pts,
       CASE WHEN c.account_id IS NULL THEN NULL
            ELSE LEAST(q.qsi_share + c.share_target_vs_qsi_pts / 100.0, 0.95) END AS target_share
FROM agg g
JOIN {GOLD}.dim_account a ON g.account_id = a.account_id
JOIN {GOLD}.dim_market m ON g.market_id = m.market_id
JOIN {SILVER}.qsi_market_month q ON g.market_id = q.market_id AND g.month = q.month AND q.carrier = 'AA'
LEFT JOIN {SILVER}.contracts c ON g.account_id = c.account_id
""")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.agency_month AS
WITH agg AS (
  SELECT agency_id, month,
         first(agency_name) AS agency_name, first(agency_tier) AS agency_tier,
         first(parent_tmc_asof) AS parent_tmc_asof,
         SUM(CASE WHEN carrier = 'AA' THEN revenue_usd ELSE 0 END) AS aa_revenue,
         SUM(revenue_usd)                                          AS total_revenue,
         SUM(CASE WHEN carrier = 'AA' THEN pax ELSE 0 END)         AS aa_pax,
         SUM(pax)                                                  AS total_pax,
         SUM(CASE WHEN carrier = 'AA' AND channel = 'NDC' THEN 1 ELSE 0 END) AS aa_ndc_bookings,
         SUM(CASE WHEN carrier = 'AA' THEN 1 ELSE 0 END)           AS aa_bookings
  FROM {GOLD}.fact_booking
  GROUP BY agency_id, month
)
SELECT g.*, t.target_aa_share, t.incentive_rate,
       CAST(g.aa_revenue * t.incentive_rate AS DECIMAL(14,2)) AS incentive_cost_usd
FROM agg g
LEFT JOIN {SILVER}.agency_incentive_targets t ON g.agency_id = t.agency_id
""")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD}.aadv_business_compliance AS
SELECT month, account_id, account_name, region, account_manager,
       COUNT(*)                                                    AS aa_bookings,
       SUM(CASE WHEN aadv_business_id IS NULL THEN 1 ELSE 0 END)   AS missing_id_bookings
FROM {GOLD}.fact_booking
WHERE segment = 'SMB' AND carrier = 'AA'
GROUP BY month, account_id, account_name, region, account_manager
""")

# COMMAND ----------

for t in ["dim_account", "dim_market", "dim_agency_history", "fact_booking",
          "account_market_month", "agency_month", "aadv_business_compliance"]:
    print(f"{t:28s} {spark.table(f'{GOLD}.{t}').count():>10,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Sanity check: overall share vs. fair share by region
# MAGIC Weighted by passengers, never a simple average of percentages.

# COMMAND ----------

display(spark.sql(f"""
SELECT region,
       ROUND(SUM(aa_pax) / SUM(total_pax), 3)                    AS passenger_share,
       ROUND(SUM(qsi_share * total_pax) / SUM(total_pax), 3)     AS fair_share_qsi,
       ROUND((SUM(aa_pax) - SUM(qsi_share * total_pax)) / SUM(total_pax) * 100, 1) AS share_vs_qsi_pts
FROM {GOLD}.account_market_month
GROUP BY region ORDER BY region
"""))
