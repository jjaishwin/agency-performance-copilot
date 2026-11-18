# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Bronze: land everything exactly as received
# MAGIC
# MAGIC **Bronze is for audit.** Every source lands as-is, as strings, with two lineage columns added:
# MAGIC - `_source_file`: which file the row came from
# MAGIC - `_ingested_at`: when it was loaded
# MAGIC
# MAGIC Nothing is cleaned or dropped here. If a number is wrong later, you can always trace it back to the exact file and load.
# MAGIC
# MAGIC The legacy Excel workbook is landed raw too, row by row, including its title rows and subtotals. That is the "Excel to lakehouse" modernization step.

# COMMAND ----------

# MAGIC %pip install openpyxl --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
LANDING = f"/Volumes/{CATALOG}/bronze/landing"
BRONZE = f"{CATALOG}.bronze"

# COMMAND ----------

import pandas as pd
from pyspark.sql import functions as F


def ingest_csv(path, table):
    """Read CSVs as all-string columns and add lineage metadata. Overwrite = idempotent re-runs."""
    df = (spark.read
          .option("header", True)
          .option("escape", '"')
          .csv(path)
          .withColumn("_source_file", F.col("_metadata.file_path"))
          .withColumn("_ingested_at", F.current_timestamp()))
    (df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{BRONZE}.{table}"))
    return spark.table(f"{BRONZE}.{table}").count()


counts = {
    "bookings": ingest_csv(f"{LANDING}/bookings/", "bookings"),
    "agencies": ingest_csv(f"{LANDING}/agencies/", "agencies"),
    "accounts": ingest_csv(f"{LANDING}/accounts.csv", "accounts"),
    "account_managers": ingest_csv(f"{LANDING}/account_managers.csv", "account_managers"),
    "contracts": ingest_csv(f"{LANDING}/contracts.csv", "contracts"),
    "markets": ingest_csv(f"{LANDING}/markets.csv", "markets"),
    "qsi_market_month": ingest_csv(f"{LANDING}/qsi_market_month.csv", "qsi_market_month"),
}
counts

# COMMAND ----------

# MAGIC %md
# MAGIC ### The legacy Excel workbook
# MAGIC Spark doesn't need to understand Excel's layout. We land every row raw, keep its original row number, and let the silver layer decide what is data.

# COMMAND ----------

excel_path = f"{LANDING}/legacy/Agency_Incentive_Targets_FY2026.xlsx"
raw = pd.read_excel(excel_path, header=None, dtype=object)
raw.columns = [f"c{i}" for i in range(raw.shape[1])]
for col in raw.columns:
    raw[col] = raw[col].map(lambda v: None if pd.isna(v) else str(v)).astype(object)
raw.insert(0, "_row_number", range(1, len(raw) + 1))

schema = "_row_number LONG, " + ", ".join(f"{c} STRING" for c in raw.columns if c != "_row_number")
rows = [tuple(None if (v is None or (isinstance(v, float) and pd.isna(v))) else v for v in r)
        for r in raw.itertuples(index=False, name=None)]
legacy_df = (spark.createDataFrame(rows, schema)
             .withColumn("_source_file", F.lit(excel_path))
             .withColumn("_ingested_at", F.current_timestamp()))
(legacy_df.write.mode("overwrite").option("overwriteSchema", "true")
 .saveAsTable(f"{BRONZE}.legacy_incentive_targets_raw"))
counts["legacy_incentive_targets_raw"] = spark.table(f"{BRONZE}.legacy_incentive_targets_raw").count()
counts

# COMMAND ----------

display(spark.table(f"{BRONZE}.legacy_incentive_targets_raw").orderBy("_row_number").limit(10))
