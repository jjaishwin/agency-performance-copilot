# Databricks notebook source
# MAGIC %md
# MAGIC # 10 · Sales performance + monitoring dashboard (AI/BI), created as code
# MAGIC
# MAGIC **Page 1 · Sales performance** (for sales leaders): share vs fair share by region, contract attainment by account manager, the accounts most at risk with talking points, and Red agencies with ready-to-send summaries. All share and attainment numbers come from the metric views, so they match Genie.
# MAGIC
# MAGIC **Page 2 · Monitoring** answers "can we trust this?" for the people who own it:
# MAGIC - **AI quality:** Genie benchmark accuracy per run and spec version (from notebook 09), latest failures.
# MAGIC - **Data quality:** data-quality check failures from the latest pipeline run (notebook 03's `silver.dq_log`).
# MAGIC - **Business health:** agency scorecard status and account risk counts (from notebook 07).
# MAGIC
# MAGIC If you haven't run notebook 09 yet, the Genie widgets are left out and added automatically the next time you run this after 09.
# MAGIC
# MAGIC Created through the Lakeview (AI/BI dashboards) API and published, so it's reproducible and lives in Git as `dashboards/monitoring.lvdash.json`. Re-running updates it in place.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
dbutils.widgets.text("warehouse_id", "", "SQL warehouse ID (blank = first available)")
CATALOG = dbutils.widgets.get("catalog")
GOLD, SILVER = f"{CATALOG}.gold", f"{CATALOG}.silver"

# COMMAND ----------

import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client
warehouse_id = dbutils.widgets.get("warehouse_id").strip() or next(iter(w.warehouses.list())).id
TITLE = "Agency Performance Copilot"

# COMMAND ----------

# MAGIC %md ## Datasets (one SQL query each)

# COMMAND ----------

HAS_GENIE_RUNS = spark.catalog.tableExists(f"{GOLD}.genie_benchmark_runs")
print("Genie benchmark runs found:" , HAS_GENIE_RUNS)

sales_datasets = {
    "region_gap": f"""
        SELECT region,
               MEASURE(passenger_share) AS passenger_share,
               MEASURE(fair_share_qsi)  AS fair_share,
               ROUND(MEASURE(share_vs_qsi_pts), 1) AS gap_pts
        FROM {GOLD}.mv_account_performance
        WHERE month >= DATE'2026-01-01'
        GROUP BY region""",
    "am_attainment": f"""
        SELECT account_manager, ROUND(MEASURE(contract_attainment) * 100, 1) AS attainment_pct
        FROM {GOLD}.mv_account_performance
        WHERE month >= DATE'2026-01-01' AND segment = 'Managed'
        GROUP BY account_manager""",
    "accounts_at_risk": f"""
        SELECT account_name, account_manager, region,
               ROUND(contract_attainment * 100, 1) AS attainment_pct,
               ROUND(share_gap_pts, 1) AS share_gap_pts, risk_status, talking_points
        FROM {GOLD}.account_scorecard
        ORDER BY contract_attainment
        LIMIT 15""",
    "red_agencies": f"""
        SELECT agency_name, agency_tier, vs_target_pts, summary
        FROM {GOLD}.agency_scorecard
        WHERE status = 'Red'
        ORDER BY vs_target_pts
        LIMIT 15""",
    "kpis": f"""
        SELECT (SELECT COUNT(*) FROM {GOLD}.account_scorecard WHERE contract_attainment < 1) AS accounts_below_target,
               (SELECT COUNT(*) FROM {GOLD}.agency_scorecard WHERE status = 'Red') AS red_agencies,
               (SELECT ROUND(MEASURE(share_vs_qsi_pts), 1) FROM {GOLD}.mv_account_performance
                WHERE month >= DATE'2026-01-01') AS share_vs_fair_share_pts""",
}

genie_datasets = {
    "benchmark_runs": f"""
        SELECT run_id, MIN(run_ts) AS run_ts, FIRST(spec_version) AS spec_version,
               SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS passed, COUNT(*) AS total,
               SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) / COUNT(*) AS pass_rate,
               AVG(latency_s) AS avg_latency_s
        FROM {GOLD}.genie_benchmark_runs GROUP BY run_id""",
    "latest_failures": f"""
        SELECT benchmark, status, question, detail, latency_s
        FROM {GOLD}.genie_benchmark_runs
        WHERE run_id = (SELECT run_id FROM {GOLD}.genie_benchmark_runs ORDER BY run_ts DESC LIMIT 1)
          AND status <> 'PASS'
        ORDER BY benchmark""",
}

ops_datasets = {
    "dq_log": f"""
        SELECT check_name, failed_rows FROM {SILVER}.dq_log
        WHERE run_at = (SELECT MAX(run_at) FROM {SILVER}.dq_log)""",
    "agency_status": f"SELECT status, COUNT(*) AS agencies FROM {GOLD}.agency_scorecard GROUP BY status",
    "account_risk": f"SELECT risk_status, COUNT(*) AS accounts FROM {GOLD}.account_scorecard GROUP BY risk_status",
}

datasets = {**sales_datasets, **(genie_datasets if HAS_GENIE_RUNS else {}), **ops_datasets}

# COMMAND ----------

# MAGIC %md ## Widgets and layout

# COMMAND ----------

def field(name, expr=None):
    return {"name": name, "expression": expr or f"`{name}`"}


def widget(name, dataset, fields, spec, x, y, wdt, h, title=None):
    spec = dict(spec)
    if title:
        spec["frame"] = {"showTitle": True, "title": title}
    return {"widget": {"name": name,
                       "queries": [{"name": "main_query",
                                    "query": {"datasetName": dataset, "fields": fields, "disaggregated": True}}],
                       "spec": spec},
            "position": {"x": x, "y": y, "width": wdt, "height": h}}


def counter(name, dataset, col, x, y, title):
    return widget(name, dataset, [field(col)],
                  {"version": 2, "widgetType": "counter", "encodings": {"value": {"fieldName": col, "displayName": title}}},
                  x, y, 2, 3, title)


def chart(kind, name, dataset, xcol, ycol, x, y, wdt, h, title, xtype="categorical", color=None):
    enc = {"x": {"fieldName": xcol, "scale": {"type": xtype}, "displayName": xcol},
           "y": {"fieldName": ycol, "scale": {"type": "quantitative"}, "displayName": ycol}}
    fields = [field(xcol), field(ycol)]
    if color:
        enc["color"] = {"fieldName": color, "scale": {"type": "categorical"}, "displayName": color}
        fields.append(field(color))
    return widget(name, dataset, fields, {"version": 3, "widgetType": kind, "encodings": enc}, x, y, wdt, h, title)


def table(name, dataset, cols, x, y, wdt, h, title):
    return widget(name, dataset, [field(c) for c in cols],
                  {"version": 1, "widgetType": "table",
                   "encodings": {"columns": [{"fieldName": c, "displayName": c, "title": c, "visible": True, "order": i}
                                             for i, c in enumerate(cols)]}},
                  x, y, wdt, h, title)


sales_layout = [
    {"widget": {"name": "sales_title", "multilineTextboxSpec": {"lines": [
        "## Sales performance: where to act\n",
        "Every region can beat fair share while individual accounts miss their contract. Shares and attainment come from the certified metric views. Synthetic data, 2026 year to date."]}},
     "position": {"x": 0, "y": 0, "width": 6, "height": 2}},
    counter("kpi_share", "kpis", "share_vs_fair_share_pts", 0, 2, "Share vs fair share (pts)"),
    counter("kpi_accounts", "kpis", "accounts_below_target", 2, 2, "Managed accounts below contract"),
    counter("kpi_agencies", "kpis", "red_agencies", 4, 2, "Red agencies (latest quarter)"),
    chart("bar", "region_gap", "region_gap", "region", "gap_pts", 0, 5, 3, 5, "Share vs fair share by region (pts)"),
    chart("bar", "am_attainment", "am_attainment", "account_manager", "attainment_pct", 3, 5, 3, 5,
          "Contract attainment by account manager (%)"),
    table("at_risk", "accounts_at_risk",
          ["account_name", "account_manager", "region", "attainment_pct", "share_gap_pts", "risk_status", "talking_points"],
          0, 10, 6, 7, "Accounts most at risk, with talking points"),
    table("red_agencies", "red_agencies", ["agency_name", "agency_tier", "vs_target_pts", "summary"],
          0, 17, 6, 6, "Red agencies: ready-to-send summaries"),
]

monitoring_layout = [
    {"widget": {"name": "title", "multilineTextboxSpec": {"lines": [
        "## Can we trust it?\n",
        "AI quality from the Genie benchmark gate, data quality from the pipeline, business health from the scorecards. Synthetic data."]}},
     "position": {"x": 0, "y": 0, "width": 6, "height": 2}},
]
if HAS_GENIE_RUNS:
    monitoring_layout += [
        chart("line", "accuracy", "benchmark_runs", "run_ts", "pass_rate", 0, 2, 4, 5,
              "Genie benchmark accuracy per run (gate: 90%)", xtype="temporal"),
        counter("latency", "benchmark_runs", "avg_latency_s", 4, 2, "Avg Genie latency (s)"),
        counter("runs", "benchmark_runs", "total", 4, 5, "Benchmarks per run"),
        table("failures", "latest_failures", ["benchmark", "status", "question", "detail"], 0, 7, 6, 5,
              "Latest run: benchmarks that didn't pass"),
    ]
monitoring_layout += [
    chart("bar", "dq", "dq_log", "check_name", "failed_rows", 0, 12, 3, 5, "Data-quality check failures (latest pipeline run)"),
    chart("bar", "agencies", "agency_status", "status", "agencies", 3, 12, 3, 5, "Agency scorecard status (latest quarter)"),
    chart("bar", "accounts", "account_risk", "risk_status", "accounts", 0, 17, 3, 5, "Managed account risk (YTD)"),
]

dashboard = {
    "datasets": [{"name": k, "displayName": k.replace("_", " ").title(), "queryLines": [v.strip()]} for k, v in datasets.items()],
    "pages": [{"name": "sales", "displayName": "Sales performance", "layout": sales_layout, "pageType": "PAGE_TYPE_CANVAS"},
              {"name": "monitoring", "displayName": "Monitoring", "layout": monitoring_layout, "pageType": "PAGE_TYPE_CANVAS"}],
}
serialized = json.dumps(dashboard)

# Check every dataset query runs before sending it.
for k, q in datasets.items():
    spark.sql(q).limit(1).collect()
print("All dataset queries run.")

# Keep the definition in Git next to the code.
try:
    import os
    os.makedirs("../dashboards", exist_ok=True)
    with open("../dashboards/monitoring.lvdash.json", "w") as f:
        json.dump(dashboard, f, indent=2)
    print("Wrote ../dashboards/monitoring.lvdash.json")
except OSError as e:
    print("Couldn't write the JSON file (fine outside a Git folder):", e)

# COMMAND ----------

# MAGIC %md ## Create or update, then publish

# COMMAND ----------

existing = None
for d in api.do("GET", "/api/2.0/lakeview/dashboards", query={"page_size": 100}).get("dashboards", []):
    if d.get("display_name") == TITLE and d.get("lifecycle_state", "ACTIVE") == "ACTIVE":
        existing = d["dashboard_id"]

body = {"display_name": TITLE, "warehouse_id": warehouse_id, "serialized_dashboard": serialized}
if existing:
    api.do("PATCH", f"/api/2.0/lakeview/dashboards/{existing}", body=body)
    dashboard_id = existing
else:
    me = w.current_user.me().user_name
    dashboard_id = api.do("POST", "/api/2.0/lakeview/dashboards", body={**body, "parent_path": f"/Workspace/Users/{me}"})["dashboard_id"]

api.do("POST", f"/api/2.0/lakeview/dashboards/{dashboard_id}/published",
       body={"warehouse_id": warehouse_id, "embed_credentials": False})
print(f"Dashboard: {w.config.host.rstrip('/')}/dashboardsv3/{dashboard_id}/published")
print("If a widget shows an error, open the draft, fix that one widget in the editor, and re-export the JSON to dashboards/.")
