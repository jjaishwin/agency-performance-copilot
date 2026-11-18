# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Silver: correct, conformed, checked
# MAGIC
# MAGIC **Silver is for correctness.** This notebook:
# MAGIC 1. Casts every column to its real type.
# MAGIC 2. **Deduplicates** tickets (keeps the latest load of each `ticket_id`).
# MAGIC 3. Runs **data-quality checks** and moves failing rows to a **quarantine table** with a reason. Bad rows are kept for audit, never silently dropped.
# MAGIC 4. Writes every check result to a **DQ log** so quality is measurable over time.
# MAGIC 5. Cleans the **legacy Excel** workbook and matches it to agencies by ARC number.
# MAGIC 6. Builds the agency dimension as **SCD Type 2**, so history survives when an agency changes parent company.
# MAGIC
# MAGIC In production, steps 2–4 map to Lakeflow Declarative Pipelines *expectations*; here they are plain PySpark so every step is visible.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
BRONZE, SILVER = f"{CATALOG}.bronze", f"{CATALOG}.silver"

# COMMAND ----------

import uuid
from pyspark.sql import Window
from pyspark.sql import functions as F

RUN_ID = str(uuid.uuid4())
dq_results = []


def log_check(table, check, failed_rows, total_rows):
    dq_results.append((RUN_ID, table, check, int(failed_rows), int(total_rows)))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Bookings: type, deduplicate, check, quarantine

# COMMAND ----------

b = spark.table(f"{BRONZE}.bookings")
total_bronze = b.count()

typed = b.select(
    "ticket_id",
    F.to_date("booking_date").alias("booking_date"),
    F.to_date("travel_date").alias("travel_date"),
    "account_id", "agency_id", "market_id", "carrier", "cabin", "channel",
    F.col("pax").cast("int").alias("pax"),
    F.col("revenue_usd").cast("decimal(12,2)").alias("revenue_usd"),
    "aadv_business_id", "pnr", "_source_file", "_ingested_at",
)

w = Window.partitionBy("ticket_id").orderBy(F.col("_ingested_at").desc(), F.col("_source_file").desc())
ranked = typed.withColumn("_rn", F.row_number().over(w))
duplicates = ranked.filter("_rn > 1").drop("_rn").withColumn("_dq_reason", F.lit("duplicate_ticket_id"))
deduped = ranked.filter("_rn = 1").drop("_rn")

known_agencies = spark.table(f"{BRONZE}.agencies").select("agency_id").distinct().withColumn("_agency_known", F.lit(True))
checked = (deduped.join(known_agencies, "agency_id", "left")
           .withColumn("_dq_reason",
                       F.when(F.col("account_id").isNull(), "missing_account_id")
                        .when(F.col("_agency_known").isNull(), "unknown_agency_id")
                        .when(F.col("revenue_usd") <= 0, "non_positive_revenue"))
           .drop("_agency_known"))

good = checked.filter("_dq_reason IS NULL").drop("_dq_reason")
bad = checked.filter("_dq_reason IS NOT NULL").unionByName(duplicates)

good.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.bookings")
bad.withColumn("_quarantined_at", F.current_timestamp()) \
   .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.bookings_quarantine")

silver_count = spark.table(f"{SILVER}.bookings").count()
quarantine = spark.table(f"{SILVER}.bookings_quarantine")
for row in quarantine.groupBy("_dq_reason").count().collect():
    log_check("bookings", row["_dq_reason"], row["count"], total_bronze)

# Reconciliation: every bronze row is either in silver or in quarantine
assert silver_count + quarantine.count() == total_bronze, "Row counts do not reconcile"
print(f"bronze={total_bronze:,}  silver={silver_count:,}  quarantined={quarantine.count():,}")
display(quarantine.groupBy("_dq_reason").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ### AAdvantage Business: flag bookings missing the business ID
# MAGIC These rows are valid tickets, so they stay in silver. They are *flagged*, because a missing ID means the small business doesn't get credit for the trip.

# COMMAND ----------

accounts = spark.table(f"{BRONZE}.accounts")
smb_aa = (spark.table(f"{SILVER}.bookings")
          .join(accounts.select("account_id", "segment"), "account_id")
          .filter("segment = 'SMB' AND carrier = 'AA'"))
missing_ids = smb_aa.filter("aadv_business_id IS NULL").count()
log_check("bookings", "smb_missing_aadv_business_id", missing_ids, smb_aa.count())
print(f"SMB AA bookings missing the business ID: {missing_ids:,} of {smb_aa.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Reference tables: type and write

# COMMAND ----------

spark.table(f"{BRONZE}.accounts").select(
    "account_id", "account_name", "segment", "region", "am_id", "aadv_business_id"
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.accounts")

spark.table(f"{BRONZE}.account_managers").select(
    "am_id", "am_name", "am_email", "region"
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.account_managers")

spark.table(f"{BRONZE}.contracts").select(
    "contract_id", "account_id",
    F.to_date("start_date").alias("start_date"), F.to_date("end_date").alias("end_date"),
    F.col("discount_pct").cast("decimal(5,2)").alias("discount_pct"),
    F.col("share_target_vs_qsi_pts").cast("int").alias("share_target_vs_qsi_pts"),
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.contracts")

spark.table(f"{BRONZE}.markets").select(
    "market_id", "origin", "destination", "region",
    (F.lower("nonstop_flag") == "true").alias("nonstop_flag"),
    (F.lower("international_flag") == "true").alias("international_flag"),
    F.col("base_fare_usd").cast("decimal(10,2)").alias("base_fare_usd"),
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.markets")

spark.table(f"{BRONZE}.qsi_market_month").select(
    "market_id", F.to_date("month").alias("month"), "carrier",
    F.col("qsi_share").cast("decimal(6,4)").alias("qsi_share"),
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{SILVER}.qsi_market_month")

# Check: QSI shares in each market-month should sum to about 1
qsi_bad = (spark.table(f"{SILVER}.qsi_market_month").groupBy("market_id", "month")
           .agg(F.sum("qsi_share").alias("s")).filter(F.abs(F.col("s") - 1) > 0.01).count())
log_check("qsi_market_month", "shares_do_not_sum_to_one", qsi_bad, spark.table(f"{SILVER}.qsi_market_month").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ### Legacy Excel: from a hand-maintained workbook to a clean table
# MAGIC Problems this fixes: title rows, a header row in the middle of the data, subtotal rows, blank rows, ARC numbers typed three different ways, percentages stored as both text ("38%") and numbers (0.38), and "TBD" placeholders.

# COMMAND ----------

raw = spark.table(f"{BRONZE}.legacy_incentive_targets_raw")
data_rows = raw.filter(F.col("c2").isin("TMC", "OTA", "Leisure"))


def parse_pct(col):
    c = F.trim(F.col(col))
    return (F.when(c.isNull() | (F.upper(c) == "TBD"), F.lit(None))
             .when(c.endswith("%"), F.regexp_replace(c, "%", "").cast("double") / 100)
             .otherwise(c.cast("double")))


targets = data_rows.select(
    F.col("_row_number").alias("source_row"),
    F.trim("c0").alias("agency_name_in_file"),
    F.regexp_replace("c1", "[^0-9]", "").alias("arc_number"),
    F.col("c2").alias("tier"),
    parse_pct("c3").alias("target_aa_share"),
    parse_pct("c4").alias("incentive_rate"),
    (F.upper(F.trim("c4")) == "TBD").alias("incentive_rate_missing"),
    F.col("c5").alias("notes"),
)

agency_arcs = spark.table(f"{BRONZE}.agencies").select("agency_id", "arc_number").distinct()
matched = targets.join(agency_arcs, "arc_number", "left")
unmatched = matched.filter("agency_id IS NULL").count()
log_check("agency_incentive_targets", "arc_not_matched_to_agency", unmatched, matched.count())
log_check("agency_incentive_targets", "incentive_rate_tbd", matched.filter("incentive_rate_missing").count(), matched.count())

matched.filter("agency_id IS NOT NULL").write.mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"{SILVER}.agency_incentive_targets")
print(f"Excel rows kept: {matched.count() - unmatched} · unmatched ARCs: {unmatched}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Agency dimension as SCD Type 2
# MAGIC Each snapshot is merged in date order. When an agency's parent company, name or tier changes, the old row is closed (`effective_to`, `is_current = false`) and a new row is opened. Historical share reports keep the parent company that was true at the time.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {SILVER}.dim_agency (
  agency_id STRING, arc_number STRING, agency_name STRING, tier STRING, region STRING,
  parent_tmc STRING, effective_from DATE, effective_to DATE, is_current BOOLEAN
)""")

agency_snapshots = spark.table(f"{BRONZE}.agencies").withColumn("snapshot_date", F.to_date("snapshot_date"))
snapshot_dates = sorted(r["snapshot_date"] for r in agency_snapshots.select("snapshot_date").distinct().collect())

for snap in snapshot_dates:
    (agency_snapshots.filter(F.col("snapshot_date") == F.lit(snap))
     .select("agency_id", "arc_number", "agency_name", "tier", "region", "parent_tmc", "snapshot_date")
     .createOrReplaceTempView("staged_agencies"))
    spark.sql(f"""
    MERGE INTO {SILVER}.dim_agency t
    USING (
      SELECT s.agency_id AS merge_key, s.* FROM staged_agencies s
      UNION ALL
      SELECT NULL AS merge_key, s.* FROM staged_agencies s
      JOIN {SILVER}.dim_agency d ON s.agency_id = d.agency_id AND d.is_current
      WHERE NOT (s.parent_tmc <=> d.parent_tmc AND s.agency_name <=> d.agency_name AND s.tier <=> d.tier)
    ) src
    ON t.agency_id = src.merge_key AND t.is_current
    WHEN MATCHED AND NOT (t.parent_tmc <=> src.parent_tmc AND t.agency_name <=> src.agency_name AND t.tier <=> src.tier)
      THEN UPDATE SET is_current = false, effective_to = date_sub(src.snapshot_date, 1)
    WHEN NOT MATCHED THEN INSERT
      (agency_id, arc_number, agency_name, tier, region, parent_tmc, effective_from, effective_to, is_current)
      VALUES (src.agency_id, src.arc_number, src.agency_name, src.tier, src.region, src.parent_tmc,
              src.snapshot_date, NULL, true)
    """)

history = spark.table(f"{SILVER}.dim_agency")
changed = history.groupBy("agency_id").count().filter("count > 1").count()
print(f"dim_agency rows: {history.count()} · agencies with history: {changed}")
display(history.join(history.groupBy("agency_id").count().filter("count > 1"), "agency_id")
        .orderBy("agency_id", "effective_from"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Write the DQ log

# COMMAND ----------

dq_df = (spark.createDataFrame(dq_results, "run_id STRING, table_name STRING, check_name STRING, failed_rows BIGINT, total_rows BIGINT")
         .withColumn("failed_pct", F.round(F.col("failed_rows") / F.col("total_rows") * 100, 3))
         .withColumn("run_at", F.current_timestamp()))
dq_df.write.mode("append").option("mergeSchema", "true").saveAsTable(f"{SILVER}.dq_log")
display(dq_df)
