# Databricks notebook source
# MAGIC %md
# MAGIC # 12 · Fabric share: the tables Fabric mirrors
# MAGIC
# MAGIC Microsoft Fabric's **Mirrored Azure Databricks Catalog** reads Unity Catalog tables in place (no copy into Fabric), but it **doesn't support tables with row filters or column masks**. Five gold tables carry the region row filter from notebook 05, so Fabric can't mirror them directly.
# MAGIC
# MAGIC The pattern: publish a `fabric_share` schema with **exactly the tables the Power BI model needs**, without the filter, and **re-apply region security in OneLake** on the same Entra groups. This is the governance trade-off to explain: the security rule now lives in two places, so it needs an owner and a parity test.
# MAGIC
# MAGIC - Mirror **only** `fabric_share`, never `gold`.
# MAGIC - No PNR or traveler-level data goes to Fabric (`fact_booking` is excluded), and contact and loyalty identifiers (account manager emails, AAdvantage Business IDs) are dropped.
# MAGIC - Table names match `data/gold/` and `microsoft/powerbi/measures.dax`, so the same semantic model works.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
GOLD, SHARE = f"{CATALOG}.gold", f"{CATALOG}.fabric_share"

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SHARE} COMMENT 'Tables mirrored into Microsoft Fabric. No row filters (unsupported by mirroring); region security is re-applied with OneLake security. No traveler-level data.'")

TABLES = ["account_market_month", "agency_month", "agency_scorecard", "account_scorecard", "contract_scenarios",
          "account_briefs", "dim_account", "dim_market", "aadv_business_compliance"]

# The CTAS runs as the job owner, who is in am_region_access as ALL, so the copies hold every region.
who = spark.sql("SELECT current_user()").first()[0]
access = spark.sql(f"SELECT region FROM {GOLD}.am_region_access WHERE user_email = '{who}'").collect()
assert any(r.region == "ALL" for r in access), (
    f"{who} needs region ALL in {GOLD}.am_region_access, or the copies will be missing regions.")

# Contact and loyalty identifiers stay in Databricks; Fabric gets only what the report needs.
EXCLUDE = ["account_manager_email", "aadv_business_id", "pnr"]

for t in TABLES:
    try:
        src_df = spark.table(f"{GOLD}.{t}")
        dropped = [c for c in EXCLUDE if c in src_df.columns]
        (src_df.drop(*dropped).write.mode("overwrite").option("overwriteSchema", "true")
               .saveAsTable(f"{SHARE}.{t}"))
        if dropped:
            print(f"  {t}: dropped {', '.join(dropped)}")
        src, dst = src_df.count(), spark.table(f"{SHARE}.{t}").count()
        assert src == dst, f"{t}: {src} vs {dst}"
        print(f"{t:<26} {dst:>8,} rows")
    except Exception as e:
        if "account_briefs" in t:
            print("account_briefs not found (run notebook 08 first); skipped")
        else:
            raise

spark.sql(f"CREATE OR REPLACE TABLE {SHARE}.target_points AS SELECT explode(array(0, 5, 10, 15, 20)) AS target_points")
spark.sql(f"COMMENT ON TABLE {SHARE}.target_points IS 'Disconnected what-if slicer for the Power BI Deal What-If page.'")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parity test for OneLake security
# MAGIC
# MAGIC After you define OneLake security roles in Fabric (one per region, `WHERE region = '<Region>'`), compare row counts per region here and in Fabric. They must match the Unity Catalog row filter's result for an account manager in that region.

# COMMAND ----------

display(spark.sql(f"""
SELECT region, COUNT(*) AS rows_account_market_month,
       COUNT(DISTINCT account_id) AS accounts
FROM {SHARE}.account_market_month GROUP BY region ORDER BY region"""))
