# Databricks notebook source
# MAGIC %md
# MAGIC # 09 · Genie Agent as code, with a benchmark release gate
# MAGIC
# MAGIC **What this does**
# MAGIC 1. Reads `genie/agent_spec.json`, which `genie/build_agent_spec.py` builds from `GENIE_AGENT_SETUP.md`: data objects, instructions, SQL expressions, example queries, entity matching and 15 benchmarks.
# MAGIC 2. Creates the Genie Agent, or updates it if one with the same title exists, through the Genie Agents Management API.
# MAGIC 3. Asks Genie all 15 benchmark questions through the Conversation API, runs each ground-truth SQL itself, and compares the results.
# MAGIC 4. Logs every run to `gold.genie_benchmark_runs` and **fails the run if accuracy is below the gate** (default 90%). In CI, a failing gate blocks the release.
# MAGIC
# MAGIC **Run this from a Git folder** (Workspace → Create → Git folder → your GitHub repo URL), so `../genie/agent_spec.json` resolves. Run notebooks 01–07 first.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
dbutils.widgets.text("warehouse_id", "", "SQL warehouse ID (blank = first available)")
dbutils.widgets.dropdown("mode", "deploy_and_test", ["deploy_and_test", "deploy", "test"], "Mode")
dbutils.widgets.text("min_pass_rate", "0.9", "Release gate: minimum pass rate")
dbutils.widgets.text("pause_seconds", "12", "Pause between questions (API throughput)")
dbutils.widgets.text("spec_path", "../genie/agent_spec.json", "Spec path")

CATALOG = dbutils.widgets.get("catalog")
GOLD = f"{CATALOG}.gold"
MODE = dbutils.widgets.get("mode")
MIN_PASS = float(dbutils.widgets.get("min_pass_rate"))
PAUSE = float(dbutils.widgets.get("pause_seconds"))

# COMMAND ----------

import hashlib, json, math, re, time, uuid
from datetime import datetime, timezone

import pandas as pd
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client

with open(dbutils.widgets.get("spec_path")) as f:
    raw = f.read()

# Point the spec at this catalog, and give benchmark 15 a real account.
raw = raw.replace("workspace.gold.", f"{GOLD}.")
account_x = spark.sql(f"""
    SELECT account_name FROM {GOLD}.account_market_month
    WHERE segment = 'Managed' AND month >= DATE'2026-01-01'
    GROUP BY account_name ORDER BY SUM(total_pax) DESC LIMIT 1""").first()[0]
raw = raw.replace("{{ACCOUNT_X}}", account_x.replace("'", "''"))
spec = json.loads(raw)
space = spec["serialized_space"]
labels = spec["meta"]["benchmark_labels"]
spec_version = hashlib.sha256(json.dumps(space, sort_keys=True).encode()).hexdigest()[:12]
print(f"Spec version {spec_version} · benchmark 15 account: {account_x}")

warehouse_id = dbutils.widgets.get("warehouse_id").strip()
if not warehouse_id:
    warehouse_id = next(iter(w.warehouses.list())).id
print("Warehouse:", warehouse_id)

# COMMAND ----------

# MAGIC %md ## 1 · Create or update the agent

# COMMAND ----------

def find_space(title: str):
    token = None
    while True:
        resp = api.do("GET", "/api/2.0/genie/spaces", query={"page_size": 100, **({"page_token": token} if token else {})})
        for s in resp.get("spaces", []):
            if s.get("title") == title:
                return s["space_id"]
        token = resp.get("next_page_token")
        if not token:
            return None


def deploy(space_json: dict) -> str:
    body = {"title": spec["meta"]["title"], "description": spec["meta"]["description"],
            "warehouse_id": warehouse_id, "serialized_space": json.dumps(space_json)}
    existing = find_space(spec["meta"]["title"])
    if existing:
        api.do("PATCH", f"/api/2.0/genie/spaces/{existing}", body=body)
        print("Updated agent", existing)
        return existing
    me = w.current_user.me().user_name
    created = api.do("POST", "/api/2.0/genie/spaces", body={**body, "parent_path": f"/Workspace/Users/{me}"})
    print("Created agent", created["space_id"])
    return created["space_id"]


if MODE in ("deploy_and_test", "deploy"):
    try:
        space_id = deploy(space)
    except Exception as e:
        # Some workspaces don't accept column settings on metric views yet. Retry without them, and say so.
        print("Deploy failed:", str(e)[:500])
        print("Retrying without column settings on metric views...")
        for mv in space["data_sources"].get("metric_views", []):
            mv.pop("column_configs", None)
        space_id = deploy(space)

    spark.sql(f"CREATE TABLE IF NOT EXISTS {GOLD}.genie_agent_registry "
              "(space_id STRING, title STRING, spec_version STRING, deployed_at TIMESTAMP) USING DELTA")
    spark.createDataFrame(
        [(space_id, spec["meta"]["title"], spec_version, datetime.now(timezone.utc))],
        "space_id STRING, title STRING, spec_version STRING, deployed_at TIMESTAMP",
    ).write.mode("append").saveAsTable(f"{GOLD}.genie_agent_registry")
else:
    space_id = find_space(spec["meta"]["title"])
    assert space_id, "No agent with this title. Run with mode = deploy first."

host = w.config.host.rstrip("/")
print(f"Open it: {host}/genie/rooms/{space_id}")

# COMMAND ----------

# MAGIC %md ## 2 · Ask Genie every benchmark question

# COMMAND ----------

DONE = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}


def ask(question: str, timeout_s: int = 300) -> dict:
    """Start a fresh conversation (no context reuse) and poll with backoff until Genie finishes."""
    t0 = time.time()
    start = api.do("POST", f"/api/2.0/genie/spaces/{space_id}/start-conversation", body={"content": question})
    conv, msg = start["conversation_id"], start["message_id"]
    delay = 1.0
    while True:
        m = api.do("GET", f"/api/2.0/genie/spaces/{space_id}/conversations/{conv}/messages/{msg}")
        if m.get("status") in DONE or time.time() - t0 > timeout_s:
            break
        time.sleep(delay)
        delay = min(delay * 1.5, 10)
    out = {"status": m.get("status", "TIMEOUT"), "latency_s": round(time.time() - t0, 1),
           "sql": None, "columns": None, "rows": None, "text": None,
           "error": (m.get("error") or {}).get("error")}
    for a in m.get("attachments", []) or []:
        if a.get("text"):
            out["text"] = a["text"].get("content")
        if a.get("query"):
            out["sql"] = a["query"].get("query")
            r = api.do("GET", f"/api/2.0/genie/spaces/{space_id}/conversations/{conv}/messages/{msg}"
                              f"/attachments/{a['attachment_id']}/query-result")
            sr = r.get("statement_response", {})
            out["columns"] = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            out["rows"] = (sr.get("result") or {}).get("data_array") or []
    return out

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Compare results
# MAGIC
# MAGIC Genie may name or order columns differently, or add extra columns. So a benchmark **passes** when the row count matches and **every ground-truth column has a matching column in Genie's result** (same values, ignoring order, numbers to 4 significant figures). A ratio returned as a percentage (×100) counts as a match but is flagged, because the instructions ask for consistent units. Open any failure in the Genie UI and check by hand: this check is strict on purpose.

# COMMAND ----------

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def norm(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v)
    if DATE_RE.match(s):
        return s[:10]
    try:
        x = float(s)
        return 0.0 if x == 0 else float(f"{x:.4g}")
    except ValueError:
        return s.strip().lower()


def col_values(rows, i, scale=1.0):
    vals = []
    for r in rows:
        v = norm(r[i])
        if isinstance(v, float) and scale != 1.0:
            v = float(f"{v * scale:.4g}")
        vals.append(v)
    return sorted(vals, key=lambda x: (x is None, str(type(x)), x if x is not None else 0))


def compare(gt: pd.DataFrame, genie: dict) -> tuple[str, str]:
    if genie["status"] != "COMPLETED":
        return "ERROR", f"status {genie['status']}: {genie.get('error') or ''}"[:300]
    if genie["rows"] is None:
        return "NO_SQL", (genie.get("text") or "Genie answered without SQL (maybe a clarifying question)")[:300]
    gt_rows = gt.astype(object).values.tolist()
    if len(gt_rows) != len(genie["rows"]):
        return "FAIL", f"row count {len(genie['rows'])} vs expected {len(gt_rows)}"
    used, scaled = set(), False
    for gi, gname in enumerate(gt.columns):
        target = col_values(gt_rows, gi)
        hit = None
        for ci in range(len(genie["columns"])):
            if ci in used:
                continue
            if col_values(genie["rows"], ci) == target:
                hit = ci
                break
            if col_values(genie["rows"], ci, scale=0.01) == target:  # Genie returned a percentage
                hit, scaled = ci, True
                break
            if col_values(genie["rows"], ci, scale=100) == target:  # Genie returned a ratio where points were expected
                hit, scaled = ci, True
                break
        if hit is None:
            return "FAIL", f"no Genie column matches expected column '{gname}'"
        used.add(hit)
    return ("PASS", "match (Genie used % vs ratio scale)") if scaled else ("PASS", "match")

# COMMAND ----------

results = []
if MODE in ("deploy_and_test", "test"):
    questions = space["benchmarks"]["questions"]
    run_id = uuid.uuid4().hex[:12]
    run_ts = datetime.now(timezone.utc)
    for n, q in enumerate(questions):
        question = q["question"][0]
        gt_sql = "".join(q["answer"][0]["content"])
        gt = spark.sql(gt_sql).toPandas()
        try:
            g = ask(question)
            status, detail = compare(gt, g)
        except Exception as e:
            g, status, detail = {"sql": None, "latency_s": None, "rows": None}, "ERROR", str(e)[:300]
        label = labels.get(q["id"], f"B{n + 1}")
        print(f"{label:>4} {status:<6} {g.get('latency_s')}s  {question[:70]}  [{detail[:80]}]")
        results.append({"run_id": run_id, "run_ts": run_ts, "spec_version": spec_version, "space_id": space_id,
                        "benchmark": label, "question": question, "status": status, "detail": detail,
                        "expected_rows": len(gt), "genie_rows": None if g.get("rows") is None else len(g["rows"]),
                        "genie_sql": g.get("sql"), "latency_s": g.get("latency_s")})
        if n < len(questions) - 1:
            time.sleep(PAUSE)

# COMMAND ----------

# MAGIC %md ## 4 · Log the run and apply the release gate

# COMMAND ----------

if results:
    schema = ("run_id STRING, run_ts TIMESTAMP, spec_version STRING, space_id STRING, benchmark STRING, "
              "question STRING, status STRING, detail STRING, expected_rows INT, genie_rows INT, "
              "genie_sql STRING, latency_s DOUBLE")
    cols = [c.split()[0] for c in schema.split(", ")]
    df = spark.createDataFrame([tuple(r[c] for c in cols) for r in results], schema)
    df.write.mode("append").option("mergeSchema", "true").saveAsTable(f"{GOLD}.genie_benchmark_runs")
    spark.sql(f"COMMENT ON TABLE {GOLD}.genie_benchmark_runs IS "
              "'One row per Genie benchmark question per run. Written by notebook 09. Release gate history.'")

    passed = sum(r["status"] == "PASS" for r in results)
    rate = passed / len(results)
    print(f"\nBenchmark accuracy: {passed}/{len(results)} = {rate:.0%} (gate {MIN_PASS:.0%}) · spec {spec_version}")
    display(df.select("benchmark", "status", "detail", "latency_s", "genie_sql"))
    if rate < MIN_PASS:
        raise Exception(f"Release gate failed: {passed}/{len(results)} benchmarks passed, below {MIN_PASS:.0%}. "
                        "Fix the root cause (comments, expressions, instructions), rebuild the spec and re-run.")
    print("Release gate passed.")
