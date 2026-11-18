# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Governance: secure, trusted, auditable
# MAGIC
# MAGIC Everything here lives in **Unity Catalog**, so every consumer (Genie, dashboards, apps, a future agent) inherits it automatically. Security sits in the data, not in a prompt.
# MAGIC
# MAGIC 1. **Comments** on tables and columns, in business language. Genie reads these to understand the data.
# MAGIC 2. **Tags** marking certified tables and PII columns.
# MAGIC 3. A **row filter**: an account manager only sees rows for their region.
# MAGIC 4. A **column mask**: the booking reference (PNR) is hidden unless you're on the PII-reader list.
# MAGIC 5. **Grants**: readers get `SELECT` on gold only.
# MAGIC 6. **Lineage**: viewed in Catalog Explorer, no code needed.
# MAGIC
# MAGIC Run this **after** notebook 04. If you re-run 04 later, re-run this notebook too, because recreating a table removes its filters and masks.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
GOLD = f"{CATALOG}.gold"
ME = spark.sql("SELECT current_user() AS u").first()["u"]
print("You are:", ME)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1 · Comments in business language

# COMMAND ----------

table_comments = {
    "account_market_month": "Certified. One row per account, market and month. Source of passenger share, revenue share, fair share (QSI) and contract attainment.",
    "agency_month": "Certified. One row per agency and month. Agency revenue share, NDC share and incentive cost. Agency attributes are as of the travel month.",
    "aadv_business_compliance": "Certified. SMB accounts by month: AA bookings and how many are missing the AAdvantage Business ID.",
    "fact_booking": "One row per ticket after deduplication and quality checks. PNR is masked.",
    "dim_account": "Corporate (Managed) and small-business (SMB) accounts with their region and account manager.",
}
def sql_str(s):
    """Escape a Python string for use inside a single-quoted SQL literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


for t, c in table_comments.items():
    spark.sql(f"COMMENT ON TABLE {GOLD}.{t} IS '{sql_str(c)}'")

column_comments = {
    "account_market_month": {
        "aa_pax": "Passengers flown on the home carrier (AA).",
        "total_pax": "Passengers flown on all carriers in this account-market-month.",
        "aa_revenue": "AA ticket revenue in USD.",
        "total_revenue": "Ticket revenue in USD across all carriers.",
        "qsi_share": "AA fair share for this market and month from the Quality of Service Index (0 to 1).",
        "qsi_eligible": "True when AA's fair share is at least 5%. Contract targets only count eligible markets.",
        "target_share": "Contracted AA share target = QSI + the contract's points, capped at 95%. Null for SMB accounts.",
        "segment": "Managed = corporate account with a contract; SMB = small business in AAdvantage Business.",
    },
    "agency_month": {
        "aa_revenue": "AA ticket revenue sold through this agency in USD.",
        "total_revenue": "Ticket revenue sold through this agency across all carriers in USD.",
        "aa_ndc_bookings": "AA bookings this agency made through NDC.",
        "incentive_cost_usd": "AA revenue multiplied by the agency's incentive rate.",
        "parent_tmc_asof": "Parent travel management company at the time of travel (history preserved).",
    },
}
for t, cols in column_comments.items():
    for col, c in cols.items():
        spark.sql(f"ALTER TABLE {GOLD}.{t} ALTER COLUMN {col} COMMENT '{sql_str(c)}'")
print("Comments applied")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2 · Tags

# COMMAND ----------

try:
    for t in ["account_market_month", "agency_month", "aadv_business_compliance"]:
        spark.sql(f"ALTER TABLE {GOLD}.{t} SET TAGS ('certified' = 'true', 'domain' = 'global_sales')")
    spark.sql(f"ALTER TABLE {GOLD}.fact_booking ALTER COLUMN pnr SET TAGS ('pii' = 'true')")
    print("Tags applied")
except Exception as e:
    print("Tags skipped (your workspace may restrict tags):", str(e)[:200])

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3 · Row filter: account managers see only their region
# MAGIC The function checks a mapping table of user → region. `ALL` sees everything. You start with `ALL`.

# COMMAND ----------

spark.sql(f"CREATE OR REPLACE TABLE {GOLD}.am_region_access (user_email STRING, region STRING)")
spark.sql(f"INSERT INTO {GOLD}.am_region_access VALUES ('{ME}', 'ALL')")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {GOLD}.rf_region(region_value STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: a user sees a row when mapped to its region or to ALL in am_region_access.'
RETURN EXISTS (
  SELECT 1 FROM {GOLD}.am_region_access a
  WHERE a.user_email = current_user() AND (a.region = 'ALL' OR a.region = region_value)
)""")

for t in ["account_market_month", "aadv_business_compliance", "fact_booking"]:
    spark.sql(f"ALTER TABLE {GOLD}.{t} SET ROW FILTER {GOLD}.rf_region ON (region)")
print("Row filter applied")

# COMMAND ----------

# MAGIC %md
# MAGIC **Demo it:** restrict yourself to the Northeast, query, then restore `ALL`. This is the screenshot for your README.

# COMMAND ----------

spark.sql(f"UPDATE {GOLD}.am_region_access SET region = 'Northeast' WHERE user_email = '{ME}'")
display(spark.sql(f"SELECT region, COUNT(*) AS rows_visible FROM {GOLD}.account_market_month GROUP BY region"))

# COMMAND ----------

spark.sql(f"UPDATE {GOLD}.am_region_access SET region = 'ALL' WHERE user_email = '{ME}'")
display(spark.sql(f"SELECT region, COUNT(*) AS rows_visible FROM {GOLD}.account_market_month GROUP BY region ORDER BY region"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4 · Column mask: hide the booking reference (PNR)

# COMMAND ----------

spark.sql(f"CREATE OR REPLACE TABLE {GOLD}.pii_readers (user_email STRING)")
spark.sql(f"""
CREATE OR REPLACE FUNCTION {GOLD}.mask_pnr(pnr STRING)
RETURNS STRING
COMMENT 'Column mask: PNR visible only to users listed in pii_readers.'
RETURN CASE WHEN EXISTS (SELECT 1 FROM {GOLD}.pii_readers p WHERE p.user_email = current_user())
            THEN pnr ELSE '******' END
""")
spark.sql(f"ALTER TABLE {GOLD}.fact_booking ALTER COLUMN pnr SET MASK {GOLD}.mask_pnr")
display(spark.sql(f"SELECT ticket_id, account_name, carrier, pnr FROM {GOLD}.fact_booking LIMIT 5"))

# COMMAND ----------

# MAGIC %md
# MAGIC Add yourself as a PII reader and the same query shows real values. Remove yourself again before building the Genie Agent, so Genie never sees PNRs.

# COMMAND ----------

spark.sql(f"INSERT INTO {GOLD}.pii_readers VALUES ('{ME}')")
display(spark.sql(f"SELECT ticket_id, account_name, carrier, pnr FROM {GOLD}.fact_booking LIMIT 5"))
spark.sql(f"DELETE FROM {GOLD}.pii_readers WHERE user_email = '{ME}'")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 5 · Grants: who can read the certified tables
# MAGIC
# MAGIC Readers get `SELECT` on the **gold** schema only, never bronze or silver. The row filter and mask above still apply on top of the grant.
# MAGIC Set `READER_GROUP` to the group your account managers belong to. On Azure, sync an Entra ID group into the workspace; `account users` works for a demo.

# COMMAND ----------

READER_GROUP = "account users"
try:
    spark.sql(f"GRANT USE CATALOG ON CATALOG {CATALOG} TO `{READER_GROUP}`")
    spark.sql(f"GRANT USE SCHEMA, SELECT ON SCHEMA {GOLD} TO `{READER_GROUP}`")
    display(spark.sql(f"SHOW GRANTS ON SCHEMA {GOLD}"))
except Exception as e:
    print("Grant skipped (you may not own the catalog, or the group doesn't exist):", str(e)[:200])

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6 · Lineage
# MAGIC Open **Catalog → your catalog → gold → account_market_month → Lineage**. You'll see it built from `fact_booking`, which came from `silver.bookings`, which came from `bronze.bookings`. Take a screenshot of the lineage graph for your README.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 7 · Verify: prove every control works
# MAGIC One table of PASS / FAIL / SKIP. The row filter and mask are tested by behaviour (switch your access, query, switch back), not just by checking that they're configured. Run it any time; it always restores your access afterwards.

# COMMAND ----------

checks = []

def check(name, fn):
    try:
        status, detail = fn()
    except Exception as e:
        status, detail = "FAIL", str(e)[:180]
    checks.append((name, status, detail))

def regions_visible(table):
    return [r[0] for r in spark.sql(f"SELECT DISTINCT region FROM {GOLD}.{table} ORDER BY region").collect()]

def c_comments():
    n = spark.sql(f"""SELECT COUNT(*) FROM {CATALOG}.information_schema.columns
                      WHERE table_schema = 'gold' AND comment IS NOT NULL AND comment <> ''""").first()[0]
    return ("PASS" if n > 0 else "FAIL"), f"{n} gold columns have business comments"

def c_tags():
    try:
        t = spark.sql(f"""SELECT COUNT(*) FROM {CATALOG}.information_schema.table_tags
                          WHERE schema_name = 'gold' AND tag_name = 'certified'""").first()[0]
        c = spark.sql(f"""SELECT COUNT(*) FROM {CATALOG}.information_schema.column_tags
                          WHERE schema_name = 'gold' AND tag_name = 'pii'""").first()[0]
    except Exception as e:
        return "SKIP", "tag views not available: " + str(e)[:120]
    return ("PASS" if t >= 3 and c >= 1 else "FAIL"), f"{t} certified tables, {c} PII column(s)"

def c_row_filter():
    out = []
    try:
        spark.sql(f"UPDATE {GOLD}.am_region_access SET region = 'Northeast' WHERE user_email = '{ME}'")
        for t in ["account_market_month", "aadv_business_compliance", "fact_booking"]:
            out.append((t, regions_visible(t)))
    finally:
        spark.sql(f"UPDATE {GOLD}.am_region_access SET region = 'ALL' WHERE user_email = '{ME}'")
    restored = regions_visible("account_market_month")
    ok = all(v == ["Northeast"] for _, v in out) and len(restored) == 4
    detail = "; ".join(f"{t}: {v}" for t, v in out) + f" | restored to ALL: {len(restored)} regions"
    return ("PASS" if ok else "FAIL"), detail

def pnr_sample():
    return [r[0] for r in spark.sql(f"SELECT pnr FROM {GOLD}.fact_booking WHERE pnr IS NOT NULL LIMIT 50").collect()]

def c_mask():
    spark.sql(f"DELETE FROM {GOLD}.pii_readers WHERE user_email = '{ME}'")
    masked = pnr_sample()
    try:
        spark.sql(f"INSERT INTO {GOLD}.pii_readers VALUES ('{ME}')")
        clear = pnr_sample()
    finally:
        spark.sql(f"DELETE FROM {GOLD}.pii_readers WHERE user_email = '{ME}'")
    ok = masked and all(v == "******" for v in masked) and any(v != "******" for v in clear)
    return ("PASS" if ok else "FAIL"), f"not a reader: {masked[:2]} | reader: {clear[:2]} | access removed again"

def c_grants():
    rows = spark.sql(f"SHOW GRANTS ON SCHEMA {GOLD}").collect()
    hit = [f"{r[0]}:{r[1]}" for r in rows if r[0] == READER_GROUP]
    return ("PASS" if any("SELECT" in h for h in hit) else "SKIP"), (", ".join(hit) or "no grant to " + READER_GROUP)

def c_no_pii_readers():
    n = spark.table(f"{GOLD}.pii_readers").count()
    return ("PASS" if n == 0 else "FAIL"), f"{n} PII readers (should be 0 before building Genie)"

check("1 Comments", c_comments)
check("2 Tags", c_tags)
check("3 Row filter (3 tables)", c_row_filter)
check("4 Column mask on PNR", c_mask)
check("5 Grants on gold", c_grants)
check("6 Genie-safe: no PII readers", c_no_pii_readers)

display(spark.createDataFrame(checks, "check STRING, status STRING, detail STRING"))
