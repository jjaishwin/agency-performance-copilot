# Databricks notebook source
# MAGIC %md
# MAGIC # 08 · Pre-call brief agent with MLflow tracing and evaluation
# MAGIC
# MAGIC **What it does:** for a managed account, the agent pulls *certified* facts from `account_scorecard` and `contract_scenarios`, then asks an LLM to write a short pre-call brief for the account manager.
# MAGIC
# MAGIC **Why it's built this way:**
# MAGIC - **Grounded:** the LLM never queries data or does math. It only writes from facts the pipeline already certified.
# MAGIC - **Traced:** every call is logged with MLflow Tracing (inputs, prompt, output, latency, tokens).
# MAGIC - **Evaluated before release:** a code scorer checks that every key number in the brief matches the facts exactly; LLM judges check grounding and tone. The results become the release gate.
# MAGIC
# MAGIC **Requirements:** serverless compute with access to a Databricks-hosted Foundation Model endpoint. If none is available in your workspace, the notebook falls back to a template brief so the evaluation still runs. Say so if that happens.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.1" "databricks-sdk>=0.40" openai --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
GOLD = f"{CATALOG}.gold"

import json
import mlflow
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
ME = spark.sql("SELECT current_user() AS u").first()["u"]
mlflow.set_experiment(f"/Users/{ME}/agency-performance-copilot-briefs")

# Pick a Databricks-hosted chat model if one is available
endpoint_names = [e.name for e in w.serving_endpoints.list()]
preferred_keywords = ["claude", "llama", "gpt-oss", "qwen", "gemma"]
candidates = [n for n in endpoint_names if n.startswith("databricks-") and any(k in n for k in preferred_keywords)]
MODEL = candidates[0] if candidates else None
print("Available endpoints:", endpoint_names)
print("Using model:", MODEL or "none (template fallback)")

client = w.serving_endpoints.get_open_ai_client() if MODEL else None
if MODEL:
    mlflow.openai.autolog()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Tool: get certified facts for one account
# MAGIC The facts are pre-formatted strings, so the brief can quote them exactly and the code scorer can check them exactly.

# COMMAND ----------

@mlflow.trace(span_type="TOOL")
def get_account_facts(account_name: str) -> dict:
    safe = account_name.replace("'", "\\'")
    row = spark.sql(f"SELECT * FROM {GOLD}.account_scorecard WHERE account_name = '{safe}'").first()
    if row is None:
        return {"error": f"No managed account named {account_name}"}
    current = spark.sql(f"""
        SELECT projected_attainment, passenger_gap, revenue_gap_usd
        FROM {GOLD}.contract_scenarios
        WHERE account_id = '{row['account_id']}' AND is_current_contract
    """).first()
    growth = row["revenue_growth_pct"]
    return {
        "account_name": row["account_name"],
        "account_manager": row["account_manager"],
        "region": row["region"],
        "contract": f"QSI + {row['contract_pts']} points",
        "contract_attainment": f"{float(row['contract_attainment']) * 100:.1f}%",
        "risk_status": row["risk_status"],
        "passenger_share": f"{float(row['passenger_share']) * 100:.1f}%",
        "fair_share": f"{float(row['fair_share']) * 100:.1f}%",
        "share_gap_pts": f"{float(row['share_gap_pts']):+.1f} pts",
        "aa_revenue_ytd": f"${float(row['aa_revenue_ytd']):,.0f}",
        "revenue_growth": "n/a" if growth is None else f"{float(growth):+.1f}%",
        "markets_below_fair_share": row["markets_below_fair_share"],
        "passengers_short_of_target": None if current is None else int(current["passenger_gap"]),
        "revenue_short_of_target": None if current is None else f"${float(current['revenue_gap_usd']):,.0f}",
        "talking_points_seed": row["talking_points"],
    }

# COMMAND ----------

# MAGIC %md
# MAGIC ### The agent: write the brief from the facts only

# COMMAND ----------

SYSTEM_PROMPT = """You write pre-call briefs for an airline's corporate account managers (the carrier is AA in this synthetic data).
Rules:
- Use ONLY the facts provided in JSON. Never invent or recalculate numbers.
- Quote numbers exactly as written in the facts (for example "87.3%" or "$1,234,567").
- Under 160 words. Three short sections with these headings: Where we stand, Watch-outs, Talking points.
- Talking points are 2 or 3 concrete, polite suggestions for the call.
- Internal use only. Do not include traveler-level details."""


def template_brief(f: dict) -> str:
    return (f"Where we stand: {f['account_name']} is at {f['contract_attainment']} contract attainment "
            f"({f['risk_status']}) on a {f['contract']} contract. Passenger share is {f['passenger_share']} "
            f"versus fair share of {f['fair_share']} ({f['share_gap_pts']}). AA revenue year to date is "
            f"{f['aa_revenue_ytd']} ({f['revenue_growth']} vs last year).\n"
            f"Watch-outs: below fair share in {f['markets_below_fair_share']}; "
            f"{f['passengers_short_of_target']} passengers ({f['revenue_short_of_target']}) short of target.\n"
            f"Talking points: {f['talking_points_seed']}")


@mlflow.trace(span_type="AGENT")
def draft_brief(account_name: str) -> str:
    facts = get_account_facts(account_name)
    if "error" in facts:
        return facts["error"]
    if client is None:
        return template_brief(facts)
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        max_tokens=400,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": "Facts:\n" + json.dumps(facts, indent=2)}],
    )
    return response.choices[0].message.content

# COMMAND ----------

example = spark.sql(f"SELECT account_name FROM {GOLD}.account_scorecard ORDER BY contract_attainment LIMIT 1").first()[0]
print(draft_brief(example))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Evaluation: the release gate
# MAGIC - `key_numbers_exact` (code): the brief must contain the exact attainment, passenger share and fair share strings. Numbers are checked by code, never by an LLM.
# MAGIC - `under_word_limit` (code): at most 160 words.
# MAGIC - `grounded_and_actionable` and `professional_tone` (LLM judges): written guidelines, judged per brief.
# MAGIC
# MAGIC Release bar: 100% on `key_numbers_exact`, at least 90% on the rest.

# COMMAND ----------

from mlflow.genai.scorers import Guidelines, scorer

eval_accounts = [r["account_name"] for r in spark.sql(f"""
    (SELECT account_name FROM {GOLD}.account_scorecard WHERE risk_status = 'At risk' ORDER BY account_id LIMIT 8)
    UNION ALL
    (SELECT account_name FROM {GOLD}.account_scorecard WHERE risk_status = 'Watch' ORDER BY account_id LIMIT 6)
    UNION ALL
    (SELECT account_name FROM {GOLD}.account_scorecard WHERE risk_status = 'On track' ORDER BY account_id LIMIT 6)
""").collect()]

eval_data = []
for name in eval_accounts:
    f = get_account_facts(name)
    eval_data.append({
        "inputs": {"account_name": name},
        "expectations": {"key_numbers": [f["contract_attainment"], f["passenger_share"], f["fair_share"]]},
    })


@scorer
def key_numbers_exact(outputs, expectations) -> bool:
    return all(num in outputs for num in expectations["key_numbers"])


@scorer
def under_word_limit(outputs) -> bool:
    return len(outputs.split()) <= 160


scorers = [key_numbers_exact, under_word_limit]
try:
    scorers += [
        Guidelines(name="grounded_and_actionable", guidelines=[
            "The brief must not state any number that is not in the account facts.",
            "The brief must include at least two concrete talking points for the account manager.",
        ]),
        Guidelines(name="professional_tone", guidelines="The brief is concise, professional and free of hype."),
    ]
except Exception as e:
    print("LLM judges unavailable; running code scorers only:", str(e)[:150])

results = mlflow.genai.evaluate(data=eval_data, predict_fn=draft_brief, scorers=scorers)
results.metrics

# COMMAND ----------

# MAGIC %md
# MAGIC Open **Experiments → agency-performance-copilot-briefs** to see every trace and the per-brief scores. Record the metrics in `docs/EVAL_REPORT.md`. If `key_numbers_exact` is below 100%, look at the failing traces: usually the model reformatted a number. Tighten the prompt, re-run, and log the change.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Publish briefs for Copilot, Power BI and the Deal Desk app

# COMMAND ----------

from datetime import datetime, timezone

managed_at_risk = [r["account_name"] for r in spark.sql(
    f"SELECT account_name FROM {GOLD}.account_scorecard WHERE risk_status <> 'On track' ORDER BY contract_attainment LIMIT 30").collect()]
rows = [(n, draft_brief(n), MODEL or "template", datetime.now(timezone.utc)) for n in managed_at_risk]
(spark.createDataFrame(rows, "account_name STRING, brief STRING, model STRING, generated_at TIMESTAMP")
 .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{GOLD}.account_briefs"))
spark.sql(f"COMMENT ON TABLE {GOLD}.account_briefs IS 'AI-drafted pre-call briefs for at-risk and watch accounts. Internal use; review before sharing.'")
print(f"Wrote {len(rows)} briefs to {GOLD}.account_briefs")
