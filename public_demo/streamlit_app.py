"""Agency Performance Copilot: public demo (no sign-in).

Reads a snapshot of the certified gold tables from data/gold/*.parquet. Synthetic data.
The full version runs on Azure Databricks (Unity Catalog security, Genie, Agent Bricks) with
Power BI, Power Automate and Copilot Studio on Microsoft Fabric. See the README.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "data" / "gold"
REPO = "https://github.com/jjaishwin/agency-performance-copilot"

st.set_page_config(page_title="Agency Performance Copilot · demo", layout="wide")


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(GOLD / f"{name}.parquet")


st.title("Agency Performance Copilot")
st.caption("Public demo on a snapshot of the certified gold tables · **all data is synthetic** · "
           "the live version runs on Azure Databricks + Microsoft Fabric with per-user security")

tab_deal, tab_agency, tab_share, tab_how = st.tabs(["Deal what-if", "Agency scorecard", "Share vs fair share", "How it works"])

# ---------------------------------------------------------------------------------------------
with tab_deal:
    scorecard = load("account_scorecard").sort_values("contract_attainment")
    scenarios = load("contract_scenarios")
    counts = scorecard["risk_status"].value_counts()
    k1, k2, k3 = st.columns(3)
    k1.metric("Managed accounts at risk (< 90%)", int(counts.get("At risk", 0)))
    k2.metric("Watch (90–100%)", int(counts.get("Watch", 0)))
    k3.metric("On track", int(counts.get("On track", 0)))

    labels = [f"{r.account_name} ({r.risk_status})" for r in scorecard.itertuples()]
    choice = st.selectbox("Account", labels)
    card = scorecard.iloc[labels.index(choice)]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contract attainment (YTD)", f"{card.contract_attainment * 100:.1f}%")
    c2.metric("Passenger share", f"{card.passenger_share * 100:.1f}%")
    c3.metric("Fair share (QSI)", f"{card.fair_share * 100:.1f}%", f"{card.share_gap_pts:+.1f} pts")
    c4.metric("Revenue YTD", f"${card.aa_revenue_ytd:,.0f}")
    st.write(f"**Current contract:** QSI + {card.contract_pts} points · **Below fair share in:** {card.markets_below_fair_share}")

    scen = scenarios[scenarios["account_name"] == card.account_name].sort_values("scenario_pts")
    pts = st.select_slider("Model a renewal target: fair share + points", options=scen["scenario_pts"].tolist(),
                           value=int(card.contract_pts))
    row = scen[scen["scenario_pts"] == pts].iloc[0]
    d1, d2, d3 = st.columns(3)
    d1.metric("Projected attainment", f"{row.projected_attainment * 100:.1f}%")
    d2.metric("Passengers short", f"{int(row.passenger_gap):,}")
    d3.metric("Revenue short", f"${row.revenue_gap_usd:,.0f}")
    st.subheader("Talking points")
    st.write(card.talking_points)

    briefs = load("account_briefs")
    match = briefs[briefs["account_name"] == card.account_name]
    if not match.empty:
        with st.expander("Pre-call brief (generated in the pipeline; numbers checked by code)"):
            st.markdown(match.iloc[0]["brief"])

# ---------------------------------------------------------------------------------------------
with tab_agency:
    ag = load("agency_scorecard")
    s = ag["status"].value_counts()
    a1, a2, a3 = st.columns(3)
    a1.metric("Green", int(s.get("Green", 0)))
    a2.metric("Amber (within 5 pts of target)", int(s.get("Amber", 0)))
    a3.metric("Red", int(s.get("Red", 0)))
    status = st.multiselect("Status", ["Red", "Amber", "Green", "No target"], default=["Red", "Amber"])
    tier = st.multiselect("Tier", sorted(ag["agency_tier"].dropna().unique().tolist()))
    view = ag[ag["status"].isin(status)]
    if tier:
        view = view[view["agency_tier"].isin(tier)]
    view = view.sort_values("vs_target_pts")
    st.dataframe(
        view[["agency_name", "agency_tier", "status", "revenue_share", "share_change_pts", "vs_target_pts", "ndc_share", "summary"]]
        .rename(columns={"agency_name": "Agency", "agency_tier": "Tier", "status": "Status", "revenue_share": "Revenue share",
                         "share_change_pts": "Change vs last qtr (pts)", "vs_target_pts": "vs target (pts)",
                         "ndc_share": "NDC share", "summary": "Summary"}),
        hide_index=True, width="stretch")
    st.caption("In the live build, Power Automate posts the Red and Amber agencies to Microsoft Teams on the 3rd of each month.")

# ---------------------------------------------------------------------------------------------
with tab_share:
    amm = load("account_market_month")
    amm["month"] = pd.to_datetime(amm["month"])
    ytd = amm[amm["month"] >= "2026-01-01"]
    g = ytd.assign(fair_pax=ytd["qsi_share"] * ytd["total_pax"]).groupby("region")[["aa_pax", "total_pax", "fair_pax"]].sum()
    out = pd.DataFrame({"Passenger share": g["aa_pax"] / g["total_pax"], "Fair share (QSI)": g["fair_pax"] / g["total_pax"]})
    st.subheader("Passenger share vs fair share by region, 2026 YTD")
    st.bar_chart(out * 100, y_label="% of passengers", stack=False)
    out["Gap (pts)"] = (out["Passenger share"] - out["Fair share (QSI)"]) * 100
    st.dataframe(out.style.format({"Passenger share": "{:.1%}", "Fair share (QSI)": "{:.1%}", "Gap (pts)": "{:+.1f}"}), width="stretch")
    st.caption("Ratios are sums of passengers, never averages of percentages. Fair share is weighted by passengers.")

# ---------------------------------------------------------------------------------------------
with tab_how:
    img = ROOT / "docs" / "img" / "agency_copilot_architecture_official_icons.png"
    if img.exists():
        st.image(str(img), width="stretch")
    st.markdown(f"""
**What this demo is:** a read-only snapshot of the gold tables, so you can click around without an account.

**What the live build adds:** Unity Catalog row filters (each account manager sees only their region), a Genie Agent
deployed as code with a 15-question benchmark gate, an Agent Bricks sales copilot, MLflow-evaluated pre-call briefs,
a Fabric mirror with a Direct Lake model in Power BI, and Copilot Studio and Power Automate in Teams.

Code, notebooks and guides: [{REPO}]({REPO})
""")
