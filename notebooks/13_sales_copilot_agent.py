# Databricks notebook source
# MAGIC %md
# MAGIC # 13 · Sales Copilot: one agent, five tools, routing measured
# MAGIC
# MAGIC An account manager shouldn't have to know which tool answers which question. This agent reads the question, **decides which tool to call**, calls it, and answers from what the tools returned. It's the supervisor pattern behind Agent Bricks, built in code so it runs on Databricks Free Edition.
# MAGIC
# MAGIC | Tool | What it answers | Built in |
# MAGIC |---|---|---|
# MAGIC | `ask_genie` | Open questions across accounts, markets, agencies (writes SQL) | Notebook 09 |
# MAGIC | `account_snapshot` | One account's attainment, share gap, weak markets, talking points | Notebook 11 (UC function) |
# MAGIC | `contract_what_if` | One account at QSI + 0/5/10/15: attainment, passenger and revenue gap | Notebook 11 (UC function) |
# MAGIC | `agency_status` | One agency's Green/Amber/Red status and summary | Notebook 11 (UC function) |
# MAGIC | `search_program_docs` | Program rules: what happens when a target is missed, how attainment is defined | Notebook 11 (documents) |
# MAGIC
# MAGIC **Guardrails:** the model never computes business numbers; every number comes from a tool. Tools run as the person running the notebook, so Unity Catalog row filters apply. Every step is traced in MLflow.
# MAGIC
# MAGIC **Measured like everything else:** 12 questions with the tool each *should* use (`gold.supervisor_routing_eval`, notebook 11). The notebook reports routing accuracy and logs it to MLflow.
# MAGIC
# MAGIC **Run first:** notebooks 09 (Genie Agent) and 11 (documents, functions, routing set).

# COMMAND ----------

# MAGIC %pip install -U mlflow openai --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
GOLD = f"{CATALOG}.gold"

import json
import re
import time

import mlflow
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client
ME = spark.sql("SELECT current_user() AS u").first()["u"]
mlflow.set_experiment(f"/Users/{ME}/agency-performance-copilot-agent")

endpoints = [e.name for e in w.serving_endpoints.list()]
MODEL = "databricks-gpt-oss-120b" if "databricks-gpt-oss-120b" in endpoints else next(
    (n for n in endpoints if n.startswith("databricks-") and any(k in n for k in ["claude", "llama", "gpt-oss", "qwen"])), None)
assert MODEL, f"No Databricks-hosted chat model found. Endpoints: {endpoints}"
client = w.serving_endpoints.get_open_ai_client()
mlflow.openai.autolog()

SPACE_ID = spark.sql(f"SELECT space_id FROM {GOLD}.genie_agent_registry ORDER BY deployed_at DESC LIMIT 1").first()["space_id"]
print("Model:", MODEL, "· Genie Agent:", SPACE_ID)

# COMMAND ----------

# MAGIC %md ## 1 · The tools

# COMMAND ----------

def rows(df, limit=20):
    out = [r.asDict() for r in df.limit(limit).collect()]
    return [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in out]


@mlflow.trace(span_type="TOOL")
def account_snapshot(account: str) -> dict:
    r = rows(spark.sql(f"SELECT * FROM {GOLD}.account_snapshot(:a)", args={"a": account}))
    return {"rows": r} if r else {"error": f"No managed account named '{account}' that you can see."}


@mlflow.trace(span_type="TOOL")
def contract_what_if(account: str, points: int) -> dict:
    r = rows(spark.sql(f"SELECT * FROM {GOLD}.contract_what_if(:a, :p)", args={"a": account, "p": int(points)}))
    return {"rows": r} if r else {"error": f"No scenario for '{account}' at QSI + {points}. Points must be 0, 5, 10 or 15."}


@mlflow.trace(span_type="TOOL")
def agency_status(agency: str) -> dict:
    r = rows(spark.sql(f"SELECT * FROM {GOLD}.agency_status(:a)", args={"a": agency}))
    return {"rows": r} if r else {"error": f"No agency named '{agency}' in the latest scorecard."}


DOCS_DIR = f"/Volumes/{CATALOG}/gold/program_docs"
SECTIONS = []
for f in dbutils.fs.ls(DOCS_DIR):
    text = open(f.path.replace("dbfs:", "")).read()
    title = text.splitlines()[0].lstrip("# ").strip()
    for part in re.split(r"\n(?=## )", text):
        SECTIONS.append({"doc": title, "text": part.strip()})
STOP = set("a an the is are was of to in on for and or what how when why does do our we i my with by be it at this that".split())


def words(s):
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP]


@mlflow.trace(span_type="RETRIEVER")
def search_program_docs(query: str, k: int = 3) -> dict:
    """Keyword retrieval over the synthetic program documents. In production: Vector Search or an Agent Bricks Knowledge Assistant."""
    q = set(words(query))
    scored = sorted(SECTIONS, key=lambda s: -len(q & set(words(s["text"]))))
    return {"passages": [{"doc": s["doc"], "text": s["text"][:1200]} for s in scored[:k]]}


@mlflow.trace(span_type="TOOL")
def ask_genie(question: str) -> dict:
    start = api.do("POST", f"/api/2.0/genie/spaces/{SPACE_ID}/start-conversation", body={"content": question})
    conv, msg = start["conversation_id"], start["message_id"]
    base = f"/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conv}/messages/{msg}"
    delay, t0 = 1.0, time.time()
    while True:
        m = api.do("GET", base)
        if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED") or time.time() - t0 > 180:
            break
        time.sleep(delay)
        delay = min(delay * 1.5, 8)
    out = {"status": m.get("status")}
    for a in m.get("attachments", []) or []:
        if a.get("text"):
            out["text"] = a["text"].get("content")
        if a.get("query"):
            out["sql"] = a["query"].get("query")
            r = api.do("GET", f"{base}/attachments/{a['attachment_id']}/query-result")
            sr = r.get("statement_response", {})
            out["columns"] = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            out["rows"] = ((sr.get("result") or {}).get("data_array") or [])[:20]
    return out


TOOLS = {"ask_genie": ask_genie, "account_snapshot": account_snapshot, "contract_what_if": contract_what_if,
         "agency_status": agency_status, "search_program_docs": search_program_docs}


def spec(name, description, props, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required}}}


TOOL_SPECS = [
    spec("ask_genie", "Answer open analytical questions across many accounts, markets, regions, account managers or agencies "
         "(rankings, counts, trends, comparisons). Writes and runs SQL on certified tables.",
         {"question": {"type": "string", "description": "The question in plain English"}}, ["question"]),
    spec("account_snapshot", "Pre-call facts for ONE named managed account: contract attainment, risk status, share vs fair "
         "share, weakest markets, talking points. Use for 'prep me for <account>' or 'how is <account> doing'.",
         {"account": {"type": "string"}}, ["account"]),
    spec("contract_what_if", "Deal modelling for ONE named account: projected attainment, passenger gap and revenue gap if the "
         "contract were fair share + points (0, 5, 10 or 15).",
         {"account": {"type": "string"}, "points": {"type": "integer", "enum": [0, 5, 10, 15]}}, ["account", "points"]),
    spec("agency_status", "Latest-quarter scorecard for ONE named travel agency: Green/Amber/Red, share vs target, NDC share.",
         {"agency": {"type": "string"}}, ["agency"]),
    spec("search_program_docs", "Program rules and definitions: what happens when targets are missed, how attainment or "
         "fair share is defined, AAdvantage Business crediting, agency incentive rules.",
         {"query": {"type": "string"}}, ["query"]),
]

# COMMAND ----------

# MAGIC %md ## 2 · The agent loop

# COMMAND ----------

SYSTEM = """You are the Sales Copilot for an airline's Global Sales account managers (synthetic demo data; AA is the home carrier).
Pick the right tool for each part of the question:
- ONE named account's status or call prep -> account_snapshot
- ONE named account at a different contract level -> contract_what_if
- ONE named travel agency -> agency_status
- program rules, policies or definitions -> search_program_docs
- anything across many accounts, markets, regions or agencies -> ask_genie
A question can need two tools. Call only the tools you need.
Every number in your answer must come from a tool result, written as the tool gave it. Never calculate new numbers.
If a tool returns an error or nothing, say so plainly. Answer in at most 120 words."""


def text_of(content) -> str:
    """gpt-oss and other reasoning models return content as parts; keep only the written answer."""
    if isinstance(content, str):
        return content.strip()
    parts = [p if isinstance(p, dict) else getattr(p, "__dict__", {}) for p in (content or [])]
    return "\n".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


@mlflow.trace(span_type="AGENT")
def copilot(question: str, max_steps: int = 4) -> dict:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    used = []
    for _ in range(max_steps):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOL_SPECS,
                                              tool_choice="auto", temperature=0, max_tokens=2000)
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        if not calls:
            return {"answer": text_of(msg.content), "tools": used}
        messages.append({"role": "assistant", "content": text_of(msg.content) or None,
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                        for c in calls]})
        for c in calls:
            name = c.function.name
            try:
                args = json.loads(c.function.arguments or "{}")
                result = TOOLS[name](**args) if name in TOOLS else {"error": f"unknown tool {name}"}
            except Exception as e:
                result = {"error": str(e)[:300]}
            used.append(name)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, default=str)[:6000]})
    return {"answer": "I couldn't finish within the step limit.", "tools": used}

# COMMAND ----------

acct = spark.sql(f"SELECT account_name FROM {GOLD}.account_scorecard WHERE risk_status = 'At risk' ORDER BY contract_attainment LIMIT 1").first()[0]
demo = copilot(f"{acct} is at risk. What does the program say I should do, and what are its weakest markets?")
print("Tools used:", demo["tools"])
print(demo["answer"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Routing evaluation
# MAGIC
# MAGIC For each question, did the agent call exactly the tools it should? **Exact** = the same set of tools; **covered** = it called at least the right ones (maybe an extra). Logged to MLflow and to `gold.agent_routing_runs`.

# COMMAND ----------

ROUTE_TO_TOOL = {"Genie Agent": "ask_genie", "Knowledge Assistant": "search_program_docs", "account_snapshot": "account_snapshot",
                 "contract_what_if": "contract_what_if", "agency_status": "agency_status"}
cases = spark.table(f"{GOLD}.supervisor_routing_eval").collect()

results = []
with mlflow.start_run(run_name="routing-eval") as run:
    for c in cases:
        expected = {ROUTE_TO_TOOL[p.strip()] for p in c.expected_route.split("+")}
        t0 = time.time()
        try:
            out = copilot(c.question)
        except Exception as e:
            out = {"answer": f"ERROR: {str(e)[:200]}", "tools": []}
        called = set(out["tools"])
        results.append((c.question, ", ".join(sorted(expected)), ", ".join(sorted(called)),
                        called == expected, expected <= called, round(time.time() - t0, 1), out["answer"][:500]))
        time.sleep(2)
    exact = sum(r[3] for r in results) / len(results)
    covered = sum(r[4] for r in results) / len(results)
    mlflow.log_metrics({"routing_exact": exact, "routing_covered": covered})
    mlflow.log_param("model", MODEL)

df = spark.createDataFrame(results, "question STRING, expected STRING, called STRING, exact BOOLEAN, covered BOOLEAN, "
                                    "latency_s DOUBLE, answer STRING") \
          .selectExpr("current_timestamp() AS run_ts", f"'{run.info.run_id}' AS mlflow_run_id", "*")
df.write.mode("append").option("mergeSchema", "true").saveAsTable(f"{GOLD}.agent_routing_runs")
print(f"Routing: exact {exact:.0%} · covered {covered:.0%} ({len(results)} questions) · model {MODEL}")
display(df.select("question", "expected", "called", "exact", "covered", "latency_s"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## What this shows, and what's next
# MAGIC
# MAGIC - **The pattern:** a supervisor that routes to Genie, governed SQL functions and documents, with every number coming from a tool. That's what an Agent Bricks Supervisor Agent does as a managed service on Azure Databricks Premium.
# MAGIC - **Measured:** routing accuracy, like the Genie benchmarks one level up. A wrong route is a wrong answer even if every tool is correct.
# MAGIC - **Next for production:** package the loop as an MLflow `ResponsesAgent`, serve it, and add it to the Deal Desk app; or build it as an Agent Bricks Supervisor with the same tools and this routing set as its evaluation.
