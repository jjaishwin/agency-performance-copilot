# Databricks notebook source
# MAGIC %md
# MAGIC # 14 · Lakeflow job, created from code
# MAGIC
# MAGIC Runs the whole project as one **Lakeflow job** (formerly Workflows): each notebook is a task, tasks wait for the ones they depend on, independent tasks run in parallel, and the dashboard refreshes even when the Genie release gate fails, so the failure is visible.
# MAGIC
# MAGIC The same job is defined in `databricks.yml` for the bundle CLI. This notebook creates it with the Databricks SDK instead, so it works from the browser on Databricks Free Edition.
# MAGIC
# MAGIC ```
# MAGIC 01 generate ─► 02 bronze ─► 03 silver ─► 04 gold ─► 05 governance ─┬─► 06 metric views ──┐
# MAGIC                                                                    └─► 07 scorecards ─────┼─► 09 Genie gate ─┬─► 10 dashboard (always)
# MAGIC                                                                         ├─► 08 brief agent │                  └─► 13 copilot eval (always)
# MAGIC                                                                         └─► 11 agent tools ─────────────────────┘
# MAGIC ```
# MAGIC
# MAGIC Running the job regenerates the same synthetic data (fixed seed), re-applies governance, re-runs both evaluations and the Genie benchmarks. Expect 30–45 minutes on serverless.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
dbutils.widgets.dropdown("run_now", "true", ["true", "false"], "Run the job now")
CATALOG = dbutils.widgets.get("catalog")
RUN_NOW = dbutils.widgets.get("run_now") == "true"

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs

w = WorkspaceClient()
JOB_NAME = "agency-performance-copilot-pipeline"

# The notebooks sit next to this one in the Git folder.
this_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
NB_DIR = this_path.rsplit("/", 1)[0]
print("Notebooks folder:", NB_DIR)

# COMMAND ----------

def task(key, notebook, depends=(), always=False, **params):
    return jobs.Task(
        task_key=key,
        notebook_task=jobs.NotebookTask(notebook_path=f"{NB_DIR}/{notebook}", source=jobs.Source.WORKSPACE,
                                        base_parameters={"catalog": CATALOG, **params}),
        depends_on=[jobs.TaskDependency(task_key=d) for d in depends],
        run_if=jobs.RunIf.ALL_DONE if always else None,
        timeout_seconds=3600,
    )


TASKS = [
    task("generate_data", "01_generate_synthetic_data"),
    task("bronze", "02_bronze_ingest", ["generate_data"]),
    task("silver", "03_silver_quality", ["bronze"]),
    task("gold", "04_gold_model", ["silver"]),
    task("governance", "05_governance", ["gold"]),
    task("metric_views", "06_metric_views", ["governance"]),
    task("scorecards", "07_scorecards_and_deals", ["governance"]),
    task("brief_agent", "08_brief_agent_mlflow", ["scorecards"]),
    task("agent_tools", "11_agent_bricks_prep", ["scorecards"]),
    task("genie_release_gate", "09_genie_agent_as_code", ["metric_views", "scorecards"],
         mode="deploy_and_test", min_pass_rate="0.9"),
    # Always run: the dashboard should show a failed gate, and the agent can be evaluated against the deployed Genie either way.
    task("monitoring_dashboard", "10_monitoring_dashboard", ["genie_release_gate"], always=True),
    task("sales_copilot_eval", "13_sales_copilot_agent", ["genie_release_gate", "agent_tools"], always=True),
]

settings = dict(
    name=JOB_NAME,
    tasks=TASKS,
    max_concurrent_runs=1,
    tags={"project": "agency-performance-copilot"},
    # A daily schedule, created paused: turning it on is one click when the data is real.
    schedule=jobs.CronSchedule(quartz_cron_expression="0 0 6 * * ?", timezone_id="America/Chicago",
                               pause_status=jobs.PauseStatus.PAUSED),
)

existing = next((j for j in w.jobs.list(name=JOB_NAME)), None)
if existing:
    w.jobs.reset(job_id=existing.job_id, new_settings=jobs.JobSettings(**settings))
    job_id = existing.job_id
    print("Updated job", job_id)
else:
    job_id = w.jobs.create(**settings).job_id
    print("Created job", job_id)

host = w.config.host.rstrip("/")
print(f"Job: {host}/jobs/{job_id}")

# COMMAND ----------

if RUN_NOW:
    run = w.jobs.run_now(job_id=job_id)
    print(f"Started run {run.run_id}. Watch it here: {host}/jobs/{job_id}/runs/{run.run_id}")
    print("Tip: the Graph view shows the dependencies; the Timeline view shows what ran in parallel.")
else:
    print("Not started (run_now = false).")
