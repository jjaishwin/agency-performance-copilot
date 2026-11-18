# Databricks notebook source
# MAGIC %md
# MAGIC # 10 · Monitoring dashboard (AI/BI), created as code
# MAGIC
# MAGIC One dashboard that answers "can we trust this?" for the people who own it:
# MAGIC - **AI quality:** Genie benchmark accuracy per run and spec version (from notebook 09), latest failures.
# MAGIC - **Data quality:** data-quality check failures from the latest pipeline run (notebook 03's `silver.dq_log`).
# MAGIC - **Business health:** agency scorecard status and account risk counts (from notebook 07).
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
TITLE = "Agency Performance Copilot - Monitoring"

# COMMAND ----------

# MAGIC %md ## Datasets (one SQL query each)

# COMMAND ----------

datasets = {
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
    "dq_log": f"""
        SELECT check_name, failed_rows FROM {SILVER}.dq_log
        WHERE run_at = (SELECT MAX(run_at) FROM {SILVER}.dq_log)""",
    "agency_status": f"SELECT status, COUNT(*) AS agencies FROM {GOLD}.agency_scorecard GROUP BY status",
    "account_risk": f"SELECT risk_status, COUNT(*) AS accounts FROM {GOLD}.account_scorecard GROUP BY risk_status",
}

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


layout = [
    {"widget": {"name": "title", "multilineTextboxSpec": {"lines": [
        "## Agency Performance Copilot: can we trust it?\n",
        "AI quality from the Genie benchmark gate, data quality from the pipeline, business health from the scorecards. Synthetic data."]}},
     "position": {"x": 0, "y": 0, "width": 6, "height": 2}},
    chart("line", "accuracy", "benchmark_runs", "run_ts", "pass_rate", 0, 2, 4, 5,
          "Genie benchmark accuracy per run (gate: 90%)", xtype="temporal"),
    counter("latency", "benchmark_runs", "avg_latency_s", 4, 2, "Avg Genie latency (s)"),
    counter("runs", "benchmark_runs", "total", 4, 5, "Benchmarks per run"),
    table("failures", "latest_failures", ["benchmark", "status", "question", "detail"], 0, 7, 6, 5,
          "Latest run: benchmarks that didn't pass"),
    chart("bar", "dq", "dq_log", "check_name", "failed_rows", 0, 12, 3, 5, "Data-quality check failures (latest pipeline run)"),
    chart("bar", "agencies", "agency_status", "status", "agencies", 3, 12, 3, 5, "Agency scorecard status (latest quarter)"),
    chart("bar", "accounts", "account_risk", "risk_status", "accounts", 0, 17, 3, 5, "Managed account risk (YTD)"),
]

dashboard = {
    "datasets": [{"name": k, "displayName": k.replace("_", " ").title(), "queryLines": [v.strip()]} for k, v in datasets.items()],
    "pages": [{"name": "monitoring", "displayName": "Monitoring", "layout": layout, "pageType": "PAGE_TYPE_CANVAS"}],
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
