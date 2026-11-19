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
import time
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
        "attainment_target": "100.0%",
        # Certified gap, so the model quotes it instead of computing 100 - attainment itself.
        "attainment_gap_pts": f"{(float(row['contract_attainment']) - 1) * 100:+.1f} pts",
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
- Do not mention thresholds, benchmarks, targets or dates that are not in the facts.
- Quote numbers exactly as written in the facts (for example "87.3%" or "$1,234,567"), every time you mention them.
- At most 140 words. Three short sections with these headings: Where we stand, Watch-outs, Talking points.
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
def draft_brief(account_name: str, facts: dict = None) -> str:
    facts = facts or get_account_facts(account_name)
    if "error" in facts:
        return facts["error"]
    if client is None:
        return template_brief(facts)
    for attempt in range(3):  # retry rate limits and empty answers
        try:
            response = client.chat.completions.create(
                model=MODEL,
                temperature=0.2,
                max_tokens=2000,  # reasoning models (gpt-oss) spend tokens thinking before they write
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": "Facts:\n" + json.dumps(facts, indent=2)}],
            )
            text = message_text(response.choices[0].message.content)
            if text:
                return text
        except Exception as e:
            print(f"Model call failed (attempt {attempt + 1}): {str(e)[:120]}")
        time.sleep(5 * (attempt + 1))
    # No brief rather than a silent template, so the evaluation counts the failure.
    return ""


def normalize(text: str) -> str:
    """Models often write minus signs and market codes with typographic hyphens (U+2011, U+2212),
    so "-3.7%" or "ORD-SLC" stops matching the certified facts. Map them back to a plain hyphen."""
    for ch in ("\u2010", "\u2011", "\u2012", "\u2212"):
        text = text.replace(ch, "-")
    return text.strip()


def message_text(content) -> str:
    """Return only the written answer. Reasoning models on Databricks (gpt-oss, Claude with thinking)
    return content as a list of parts, e.g. [{"type": "reasoning", ...}, {"type": "text", "text": "..."}]."""
    if isinstance(content, str):
        return normalize(content)
    parts = []
    for part in content or []:
        p = part if isinstance(part, dict) else getattr(part, "__dict__", {})
        if p.get("type") == "text":
            parts.append(p.get("text", ""))
    return normalize("\n".join(parts))

# COMMAND ----------

example = spark.sql(f"SELECT account_name FROM {GOLD}.account_scorecard ORDER BY contract_attainment LIMIT 1").first()[0]
print(draft_brief(example))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Evaluation: the release gate
# MAGIC - `key_numbers_exact` (code): the brief contains the exact attainment, passenger share and fair share strings.
# MAGIC - `no_invented_numbers` (code): every number in the brief appears in the certified facts. Catches invented thresholds like "the 90% line".
# MAGIC - `under_word_limit` (code): at most 160 words (the prompt asks for 140, leaving margin).
# MAGIC - `actionable` and `professional_tone` (LLM judges): specific written rules, with the facts visible to the judge.
# MAGIC
# MAGIC Numbers are checked by code, never by an LLM. The first judge version was too vague: it penalized the required headings and couldn't see the facts, so its scores measured the judge, not the brief. Read judge rationales before trusting judge scores.
# MAGIC
# MAGIC Release bar: 100% on the two number checks, at least 90% on the rest.

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
        # The facts go in the inputs so the LLM judge can see what the brief was written from.
        "inputs": {"account_name": name, "facts": f},
        "expectations": {"key_numbers": [f["contract_attainment"], f["passenger_share"], f["fair_share"]]},
    })


@scorer
def key_numbers_exact(outputs, expectations) -> bool:
    outputs = outputs or ""
    return bool(outputs) and all(num in outputs for num in expectations["key_numbers"])


@scorer
def under_word_limit(outputs) -> bool:
    return bool(outputs) and len(outputs.split()) <= 160


import re
from mlflow.entities import Feedback

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> set:
    """Numeric values in the text, so 110 and 110.0 are the same number. Formatting is checked by key_numbers_exact."""
    text = re.sub(r"(?m)^\s*\d+[.)]\s", " ", text)  # ignore list numbering "1. "
    return {round(float(n.replace(",", "")), 4) for n in NUM.findall(text)}


@scorer
def no_invented_numbers(inputs, outputs) -> Feedback:
    """Grounding, checked by code: every number in the brief must appear in the certified facts."""
    if not outputs:
        return Feedback(value=False, rationale="No brief was produced (model call failed).")
    allowed = numbers_in(json.dumps(inputs["facts"]))
    invented = sorted(numbers_in(outputs) - allowed)
    return Feedback(value=not invented,
                    rationale="All numbers come from the facts." if not invented
                    else f"Numbers not in the facts: {', '.join(f'{n:g}' for n in invented)}")


scorers = [key_numbers_exact, no_invented_numbers, under_word_limit]
try:
    scorers += [
        # Judges get specific, testable rules that agree with the required format.
        # Number grounding is checked by code above, so the judge focuses on what code can't check.
        Guidelines(name="actionable", guidelines=[
            "The request contains the account facts. The brief must not contradict them.",
            "The Talking points section has at least two concrete suggestions the account manager could raise on a call, "
            "each tied to something in the facts (a market, a gap, a trend or the contract).",
        ]),
        Guidelines(name="professional_tone", guidelines=[
            "The headings 'Where we stand', 'Watch-outs' and 'Talking points', bullet points and bold numbers are the required "
            "format. Do not penalize them, and do not penalize factual status labels such as 'At risk', 'Watch' or 'On track'.",
            "Fail only if the brief uses exaggerated or salesy language (for example 'amazing', 'huge win', 'crushing it'), "
            "exclamation marks or emojis, or blames or criticizes the customer.",
        ]),
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
rows = []
for n in managed_at_risk:
    text = draft_brief(n)
    rows.append((n, text or template_brief(get_account_facts(n)), (MODEL if text else None) or "template",
                 datetime.now(timezone.utc)))
(spark.createDataFrame(rows, "account_name STRING, brief STRING, model STRING, generated_at TIMESTAMP")
 .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{GOLD}.account_briefs"))
spark.sql(f"COMMENT ON TABLE {GOLD}.account_briefs IS 'AI-drafted pre-call briefs for at-risk and watch accounts. Internal use; review before sharing.'")
print(f"Wrote {len(rows)} briefs to {GOLD}.account_briefs")
