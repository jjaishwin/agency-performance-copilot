"""Build genie/agent_spec.json from GENIE_AGENT_SETUP.md.

The markdown guide is the single source of truth for instructions, SQL expressions,
example queries and benchmarks. This script turns it into the `serialized_space` JSON
that the Genie Agents Management API accepts, so the agent can be created, versioned
and deployed as code (notebook 09).

Run:  python genie/build_agent_spec.py
"""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
MD = (HERE / "GENIE_AGENT_SETUP.md").read_text()

# Genie IDs: 32 lowercase hex chars, and every list must be sorted by id.
# Prefix (type) + index first, so sorting by id keeps the order in the guide.
PREFIX = {"sample": 0x10, "text": 0x20, "example": 0x30, "filter": 0x40,
          "expression": 0x50, "measure": 0x60, "benchmark": 0x70}


def gid(kind: str, i: int, key: str) -> str:
    return f"{PREFIX[kind]:02x}{i:06x}" + hashlib.md5(key.encode()).hexdigest()[:24]


def section(n: int) -> str:
    m = re.search(rf"\n## {n}\..*?(?=\n## \d+\.|\Z)", MD, re.S)
    return m.group(0)


def sql_lines(sql: str) -> list[str]:
    lines = sql.strip().split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


# 1. Data objects -------------------------------------------------------------------
objects = re.findall(r"\| `(workspace\.gold\.\w+)` \|", section(1))
metric_views = sorted(o for o in objects if ".mv_" in o)
tables = sorted(o for o in objects if ".mv_" not in o)

ENTITY_COLUMNS = {
    "workspace.gold.account_market_month": ["account_manager", "account_name", "market_name", "region", "segment"],
    "workspace.gold.agency_month": ["agency_name", "agency_tier", "parent_tmc_asof"],
    "workspace.gold.aadv_business_compliance": ["account_manager", "account_name", "region"],
    "workspace.gold.mv_account_performance": ["account_manager", "account_name", "market_name", "region", "segment"],
    "workspace.gold.mv_agency_performance": ["agency_name", "agency_tier", "parent_tmc"],
}
DESCRIPTIONS = {
    "workspace.gold.account_market_month": "One row per account, market and month. AA and all-carrier passengers and revenue, QSI fair share, contract target share. Synthetic.",
    "workspace.gold.agency_month": "One row per travel agency and month. AA and total revenue, NDC bookings, incentive cost, parent company at the time. Synthetic.",
    "workspace.gold.aadv_business_compliance": "SMB accounts by month: AA bookings and how many were missing the AAdvantage Business ID. Synthetic.",
    "workspace.gold.mv_account_performance": "Certified account metrics. Use MEASURE() for passenger_share, fair_share_qsi, share_vs_qsi_pts, contract_attainment, revenue_share, premium_mix.",
    "workspace.gold.mv_agency_performance": "Certified agency metrics. Use MEASURE() for revenue_share, ndc_share, incentive_cost, revenue_per_incentive_dollar.",
}


def source(identifier: str) -> dict:
    d = {"identifier": identifier}
    if identifier in DESCRIPTIONS:
        d["description"] = [DESCRIPTIONS[identifier]]
    cols = ENTITY_COLUMNS.get(identifier)
    if cols:
        d["column_configs"] = [{"column_name": c, "enable_entity_matching": True, "enable_format_assistance": True}
                               for c in sorted(cols)]
    return d


# 2. Text instructions ---------------------------------------------------------------
text = re.search(r"```\n(.*?)```", section(2), re.S).group(1).strip()

# 3. SQL expressions -----------------------------------------------------------------
s3 = section(3)
measures_block = s3.split("**Filters**")[0]
filters_block = s3.split("**Filters**")[1]
measures, filters = [], []
for i, (name, expr, syn) in enumerate(re.findall(r"\| ([a-z ]+) \| `(.+?)` \| (.+?) \|", measures_block)):
    expr = re.sub(r"\b(aa_pax|total_pax|qsi_share|qsi_eligible|target_share)\b", r"account_market_month.\1", expr)
    measures.append({"id": gid("measure", i, name), "alias": name.replace(" ", "_"), "sql": [expr],
                     "display_name": name, "synonyms": [s.strip() for s in syn.split(",")]})
for i, (name, expr) in enumerate(re.findall(r"\| ([a-z ]+) \| `(.+?)` \|", filters_block)):
    expr = re.sub(r"\b(segment|month|qsi_eligible)\b", r"account_market_month.\1", expr)
    filters.append({"id": gid("filter", i, name), "sql": [expr], "display_name": name})

# 4. Example SQL queries ---------------------------------------------------------------
examples = []
for i, (q, sql) in enumerate(re.findall(r"\*\*(.+?\?)\*\*\n```sql\n(.*?)```", section(4), re.S)):
    ex = {"id": gid("example", i, q), "question": [q], "sql": sql_lines(sql)}
    if ":account_name" in sql:
        ex["parameters"] = [{"name": "account_name", "type_hint": "STRING",
                             "description": ["Exact managed account name, for example from dim_account"]}]
        ex["usage_guidance"] = ["Use when the user asks where a specific account is below fair share"]
    examples.append(ex)

# 6. Benchmarks ------------------------------------------------------------------------
benchmarks, labels, tiers = [], {}, {}
for i, (num, q, sql) in enumerate(re.findall(r"### ([BA]\d+)\. (.+?)\n```sql\n(.*?)```", section(6), re.S)):
    q = q.replace("[Account X]", "{{ACCOUNT_X}}")
    sql = sql.replace("[Account X]", "{{ACCOUNT_X}}")
    benchmarks.append({"id": gid("benchmark", i, num), "question": [q],
                       "answer": [{"format": "SQL", "content": sql_lines(sql)}]})
    labels[benchmarks[-1]["id"]] = num
    tiers[benchmarks[-1]["id"]] = "core" if num.startswith("B") else "advanced"

sample_questions = [
    "Which managed accounts are at risk this year?",
    "What is our share versus fair share by region this year?",
    "Which agencies have the highest NDC adoption this year?",
]

space = {
    "version": 2,
    "config": {"sample_questions": [{"id": gid("sample", i, q), "question": [q]} for i, q in enumerate(sample_questions)]},
    "data_sources": {"tables": [source(t) for t in tables], "metric_views": [source(m) for m in metric_views]},
    "instructions": {
        "text_instructions": [{"id": gid("text", 0, "main"), "content": [text]}],
        "example_question_sqls": examples,
        "sql_snippets": {"filters": filters, "measures": measures},
    },
    "benchmarks": {"questions": benchmarks},
}

# Validate the rules the API enforces before anyone sends it.
def ids(xs): return [x["id"] for x in xs]
for name, xs in [("sample", space["config"]["sample_questions"]), ("examples", examples), ("filters", filters),
                 ("measures", measures), ("benchmarks", benchmarks)]:
    assert ids(xs) == sorted(ids(xs)), f"{name} not sorted"
    assert all(re.fullmatch(r"[0-9a-f]{32}", x) for x in ids(xs)), f"{name} bad id"
for coll in ("tables", "metric_views"):
    idents = [d["identifier"] for d in space["data_sources"][coll]]
    assert idents == sorted(idents)
all_instr = ids(examples) + ids(filters) + ids(measures) + ids(space["instructions"]["text_instructions"])
assert len(all_instr) == len(set(all_instr))
assert len(tables) + len(metric_views) <= 5
n_core = sum(t == "core" for t in tiers.values())
assert n_core == 15 and len(benchmarks) - n_core == 10 and len(examples) == 5

meta = {
    "title": "Agency Performance Copilot",
    "description": re.search(r"> (Ask about.+)", section(1)).group(1).strip(),
    "benchmark_labels": labels,
    "benchmark_tiers": tiers,  # core = release gate; advanced = tracked, not gating
}
out = {"meta": meta, "serialized_space": space}
(HERE / "agent_spec.json").write_text(json.dumps(out, indent=2) + "\n")
print(f"agent_spec.json: {len(tables)} tables, {len(metric_views)} metric views, {len(examples)} examples, "
      f"{len(measures)} measures, {len(filters)} filters, {n_core} core + {len(benchmarks) - n_core} advanced benchmarks")
