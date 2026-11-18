"""Deal Desk: a Databricks App for account managers.

Tab 1, Deal what-if: pick a managed account, see where it stands, test contract targets of QSI + 0 to 15 pts.
Tab 2, Ask Genie: ask the Agency Performance Copilot Genie Agent a question in plain English.

Runs as the signed-in user when user authorization is on (scopes: sql, genie), so the Unity Catalog
region row filter shows each account manager only their own accounts. Otherwise it falls back to the
app's service principal. Reads only certified gold tables. Synthetic data for demonstration.
"""
import hashlib
import os
import time

import pandas as pd
import streamlit as st
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

CATALOG = os.getenv("CATALOG", "workspace")
GOLD = f"{CATALOG}.gold"
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")

st.set_page_config(page_title="Deal Desk", layout="wide")
cfg = Config()  # the app's own credentials, injected by Databricks Apps

# On-behalf-of-user: Databricks Apps forwards the signed-in user's token in this header.
user_token = st.context.headers.get("x-forwarded-access-token")
# Caches are keyed by identity, so one user's row-filtered results are never shown to another user.
identity = hashlib.sha256(user_token.encode()).hexdigest()[:16] if user_token else "service-principal"


@st.cache_resource
def connection(identity_key: str):
    kwargs = {"access_token": user_token} if user_token else {"credentials_provider": lambda: cfg.authenticate}
    return sql.connect(server_hostname=cfg.host, http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}", **kwargs)


@st.cache_data(ttl=600)
def query(identity_key: str, statement: str, params: dict | None = None) -> pd.DataFrame:
    with connection(identity_key).cursor() as cur:
        cur.execute(statement, params or {})
        return cur.fetchall_arrow().to_pandas()


def q(statement: str, params: dict | None = None) -> pd.DataFrame:
    return query(identity, statement, params)


def workspace_client() -> WorkspaceClient:
    if user_token:
        return WorkspaceClient(host=cfg.host, token=user_token, auth_type="pat")
    return WorkspaceClient()


st.title("Deal Desk")
who = q("SELECT current_user() AS u").iloc[0]["u"]
st.caption(f"Signed in as **{who}** · {'your Unity Catalog permissions apply' if user_token else 'app service principal'}"
           " · certified gold tables · synthetic demo data")

tab_deal, tab_genie = st.tabs(["Deal what-if", "Ask Genie"])

# ---------------------------------------------------------------------------------------------
with tab_deal:
    accounts = q(f"SELECT account_name, risk_status FROM {GOLD}.account_scorecard ORDER BY contract_attainment")
    if accounts.empty:
        st.warning("No accounts visible to you. The region row filter only shows accounts in your region: ask an admin "
                   "to add you (or the app's service principal) to gold.am_region_access, and grant SELECT on the gold schema.")
        st.stop()

    labels = [f"{r.account_name} ({r.risk_status})" for r in accounts.itertuples()]
    choice = st.selectbox("Account", labels)
    account = accounts.iloc[labels.index(choice)]["account_name"]

    card = q(f"SELECT * FROM {GOLD}.account_scorecard WHERE account_name = :name", {"name": account}).iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contract attainment", f"{card.contract_attainment * 100:.1f}%", card.risk_status, delta_color="off")
    c2.metric("Passenger share", f"{card.passenger_share * 100:.1f}%")
    c3.metric("Fair share (QSI)", f"{card.fair_share * 100:.1f}%", f"{card.share_gap_pts:+.1f} pts")
    c4.metric("AA revenue YTD", f"${card.aa_revenue_ytd:,.0f}")
    st.write(f"**Current contract:** QSI + {card.contract_pts} points · **Below fair share in:** {card.markets_below_fair_share}")

    st.subheader("What-if: contract target")
    scen = q(f"SELECT * FROM {GOLD}.contract_scenarios WHERE account_name = :name ORDER BY scenario_pts", {"name": account})
    pts = st.select_slider("Target = fair share + points", options=scen["scenario_pts"].tolist(), value=int(card.contract_pts))
    row = scen[scen["scenario_pts"] == pts].iloc[0]
    d1, d2, d3 = st.columns(3)
    d1.metric("Projected attainment", f"{row.projected_attainment * 100:.1f}%")
    d2.metric("Passengers short", f"{int(row.passenger_gap):,}")
    d3.metric("Revenue short", f"${row.revenue_gap_usd:,.0f}")

    st.dataframe(
        scen[["scenario_pts", "target_share", "projected_attainment", "passenger_gap", "revenue_gap_usd", "is_current_contract"]]
        .rename(columns={"scenario_pts": "QSI + pts", "target_share": "Target share", "projected_attainment": "Attainment",
                         "passenger_gap": "Passengers short", "revenue_gap_usd": "Revenue short ($)",
                         "is_current_contract": "Current"}),
        hide_index=True, width="stretch")

    st.subheader("Talking points")
    st.write(card.talking_points)
    try:
        brief = q(f"SELECT brief FROM {GOLD}.account_briefs WHERE account_name = :name", {"name": account})
        if not brief.empty:
            with st.expander("AI-drafted pre-call brief (review before use)"):
                st.markdown(brief.iloc[0]["brief"])
    except Exception:
        pass

# ---------------------------------------------------------------------------------------------
with tab_genie:
    space_id = GENIE_SPACE_ID
    if not space_id:
        try:
            space_id = q(f"SELECT space_id FROM {GOLD}.genie_agent_registry ORDER BY deployed_at DESC LIMIT 1").iloc[0]["space_id"]
        except Exception:
            space_id = ""
    if not space_id:
        st.info("Set GENIE_SPACE_ID in app.yaml, or run notebook 09 to deploy the Genie Agent.")
    else:
        st.write("Ask the **Agency Performance Copilot** Genie Agent. Answers use certified metrics and your data permissions.")
        question = st.text_input("Question", placeholder="Which managed accounts are at risk this year?")
        if st.button("Ask", type="primary") and question:
            api = workspace_client().api_client
            with st.spinner("Genie is working..."):
                start = api.do("POST", f"/api/2.0/genie/spaces/{space_id}/start-conversation", body={"content": question})
                conv, msg = start["conversation_id"], start["message_id"]
                base = f"/api/2.0/genie/spaces/{space_id}/conversations/{conv}/messages/{msg}"
                delay, t0 = 1.0, time.time()
                while True:
                    m = api.do("GET", base)
                    if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED") or time.time() - t0 > 120:
                        break
                    time.sleep(delay)
                    delay = min(delay * 1.5, 8)
            if m.get("status") != "COMPLETED":
                st.error(f"Genie didn't finish: {m.get('status')} {(m.get('error') or {}).get('error', '')}")
            for a in m.get("attachments", []) or []:
                if a.get("text"):
                    st.markdown(a["text"].get("content", ""))
                if a.get("query"):
                    if a["query"].get("description"):
                        st.caption(a["query"]["description"])
                    r = api.do("GET", f"{base}/attachments/{a['attachment_id']}/query-result")
                    sr = r.get("statement_response", {})
                    cols = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
                    st.dataframe(pd.DataFrame((sr.get("result") or {}).get("data_array") or [], columns=cols),
                                 hide_index=True, width="stretch")
                    with st.expander("SQL Genie ran"):
                        st.code(a["query"].get("query", ""), language="sql")
