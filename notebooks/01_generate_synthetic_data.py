# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Generate synthetic data
# MAGIC
# MAGIC **What this does:** creates realistic, fully synthetic airline sales data and lands it as raw files in a Unity Catalog volume, the way real source systems would drop files.
# MAGIC
# MAGIC | File | Real-world equivalent |
# MAGIC |---|---|
# MAGIC | `bookings/bookings_YYYY_MM.csv` | Monthly ticket feed (ARC/BSP-style settlement + market data) |
# MAGIC | `agencies/agencies_snapshot_*.csv` | Agency master: two snapshots, some agencies change parent company |
# MAGIC | `accounts.csv`, `account_managers.csv` | Corporate and SMB accounts from the CRM |
# MAGIC | `contracts.csv` | Corporate contracts: share target expressed as "QSI + X points" |
# MAGIC | `markets.csv`, `qsi_market_month.csv` | Origin–destination markets and each carrier's fair share (QSI) |
# MAGIC | `legacy/Agency_Incentive_Targets_FY2026.xlsx` | A hand-maintained Excel workbook, the "legacy" source being modernized |
# MAGIC
# MAGIC **Carriers:** `AA` plus two fictional competitors, `XA` and `XB`. All companies, people and numbers are invented.
# MAGIC
# MAGIC **Planted defects** (so the silver layer has something to catch): duplicate tickets, missing account IDs, unknown agency IDs, non-positive fares, missing AAdvantage Business IDs, and a messy Excel file.

# COMMAND ----------

# MAGIC %pip install faker openpyxl --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catalog")
CATALOG = dbutils.widgets.get("catalog")

for schema in ["bronze", "silver", "gold"]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.bronze.landing")

OUT_DIR = f"/Volumes/{CATALOG}/bronze/landing"
print("Landing files in:", OUT_DIR)

# COMMAND ----------

import os
import random
import string

import numpy as np
import pandas as pd


def generate_all(out_dir, seed=42, months=24, start_month="2024-11-01"):
    """Generate every synthetic source file into out_dir. Deterministic for a given seed."""
    from faker import Faker
    from openpyxl import Workbook
    from openpyxl.styles import Font

    rng = np.random.default_rng(seed)
    random.seed(seed)
    fake = Faker("en_US")
    Faker.seed(seed)

    for sub in ["bookings", "agencies", "legacy"]:
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)

    month_starts = pd.date_range(start_month, periods=months, freq="MS")

    # ---------- Markets ----------
    hub_region = {"DFW": "Central", "ORD": "Central", "CLT": "Southeast", "MIA": "Southeast",
                  "PHX": "West", "LAX": "West", "PHL": "Northeast", "JFK": "Northeast", "DCA": "Northeast"}
    strong_hubs = {"DFW", "CLT", "MIA", "PHX", "PHL"}
    destinations = ["ATL", "DEN", "SEA", "SFO", "BOS", "IAH", "MSP", "DTW", "LAS", "MCO", "SAN", "AUS",
                    "BNA", "RDU", "STL", "SLC", "LHR", "CDG", "NRT", "MEX", "GRU", "YYZ"]
    pairs = [(h, d) for h in hub_region for d in destinations if h != d]
    rng.shuffle(pairs)
    pairs = pairs[:50]
    markets = []
    for i, (o, d) in enumerate(pairs, start=1):
        intl = d in {"LHR", "CDG", "NRT", "MEX", "GRU", "YYZ"}
        base_fare = float(rng.uniform(650, 1400) if intl else rng.uniform(180, 520))
        markets.append({"market_id": f"M{i:03d}", "origin": o, "destination": d,
                        "region": hub_region[o], "nonstop_flag": bool(rng.random() < 0.8),
                        "international_flag": intl, "base_fare_usd": round(base_fare, 2)})
    markets = pd.DataFrame(markets)
    # Five markets where AA's schedule is tiny: fair share near zero (tests the low-QSI exclusion rule)
    tiny = set(markets.sample(5, random_state=seed)["market_id"])

    # ---------- QSI (fair share) by market and month ----------
    qsi_rows = []
    for m in markets.itertuples():
        if m.market_id in tiny:
            aa_base = 0.03
        elif m.origin in strong_hubs:
            aa_base = rng.uniform(0.50, 0.70)
        else:
            aa_base = rng.uniform(0.30, 0.45)
        xa_split = rng.uniform(0.4, 0.6)
        for ms in month_starts:
            aa = float(np.clip(aa_base + rng.normal(0, 0.015), 0.01, 0.9))
            rest = 1 - aa
            xa = rest * float(np.clip(xa_split + rng.normal(0, 0.02), 0.2, 0.8))
            xb = rest - xa
            for carrier, q in [("AA", aa), ("XA", xa), ("XB", xb)]:
                qsi_rows.append({"market_id": m.market_id, "month": ms.date().isoformat(),
                                 "carrier": carrier, "qsi_share": round(q, 4)})
    qsi = pd.DataFrame(qsi_rows)

    # ---------- Account managers ----------
    regions = ["Central", "Southeast", "West", "Northeast"]
    ams = []
    for i in range(12):
        name = fake.unique.name()
        ams.append({"am_id": f"AM{i + 1:02d}", "am_name": name,
                    "am_email": f"am{i + 1:02d}@example.com", "region": regions[i % 4]})
    ams = pd.DataFrame(ams)

    # ---------- Agencies ----------
    parents = ["Northstar Travel Group", "Meridian Corporate Travel", "Atlas Business Travel",
               "Summit TMC Partners", "Harbor Travel Partners"]
    agencies = []
    for i in range(200):
        r = rng.random()
        tier = "TMC" if r < 0.30 else ("OTA" if r < 0.45 else "Leisure")
        parent = random.choice(parents) if tier == "TMC" else None
        arc = f"{rng.integers(10_000_000, 99_999_999)}"
        agencies.append({"agency_id": f"A{i + 1:04d}", "arc_number": arc,
                         "agency_name": fake.unique.company() + (" Travel" if tier != "OTA" else " Online"),
                         "tier": tier, "region": regions[i % 4], "parent_tmc": parent})
    agencies = pd.DataFrame(agencies)
    snap1 = agencies.copy()
    snap1["snapshot_date"] = month_starts[0].date().isoformat()
    snap2 = agencies.copy()
    tmc_idx = snap2.index[snap2["tier"] == "TMC"].tolist()
    reparented = random.sample(tmc_idx, 6)
    for idx in reparented:
        current = snap2.at[idx, "parent_tmc"]
        snap2.at[idx, "parent_tmc"] = random.choice([p for p in parents if p != current])
    renamed = random.sample([i for i in snap2.index if i not in reparented], 2)
    for idx in renamed:
        snap2.at[idx, "agency_name"] = snap2.at[idx, "agency_name"] + " Group"
    snap2["snapshot_date"] = month_starts[12].date().isoformat()
    snap1.to_csv(os.path.join(out_dir, "agencies", f"agencies_snapshot_{snap1['snapshot_date'][0]}.csv"), index=False)
    snap2.to_csv(os.path.join(out_dir, "agencies", f"agencies_snapshot_{snap2['snapshot_date'][0]}.csv"), index=False)

    # ---------- Accounts ----------
    accounts = []
    for i in range(300):
        segment = "Managed" if i < 200 else "SMB"
        region = regions[i % 4]
        am = ams[ams["region"] == region].sample(1, random_state=seed + i).iloc[0]
        accounts.append({"account_id": f"C{i + 1:04d}", "account_name": fake.unique.company(),
                         "segment": segment, "region": region, "am_id": am["am_id"],
                         "aadv_business_id": f"BEAN{rng.integers(1_000_000, 9_999_999)}" if segment == "SMB" else None})
    accounts = pd.DataFrame(accounts)

    # ---------- Contracts (managed accounts only) ----------
    contracts = []
    for a in accounts[accounts["segment"] == "Managed"].itertuples():
        contracts.append({"contract_id": f"K{a.account_id[1:]}", "account_id": a.account_id,
                          "start_date": month_starts[0].date().isoformat(),
                          "end_date": (month_starts[-1] + pd.offsets.MonthEnd(0)).date().isoformat(),
                          "discount_pct": round(float(rng.uniform(3, 15)), 1),
                          "share_target_vs_qsi_pts": int(rng.choice([0, 5, 10, 15]))})
    contracts = pd.DataFrame(contracts)

    # ---------- Bookings ----------
    tier_of = dict(zip(agencies["agency_id"], agencies["tier"]))
    tmc_ids = agencies.loc[agencies["tier"] == "TMC", "agency_id"].to_numpy()
    ota_ids = agencies.loc[agencies["tier"] == "OTA", "agency_id"].to_numpy()
    leisure_ids = agencies.loc[agencies["tier"] == "Leisure", "agency_id"].to_numpy()
    qsi_aa = qsi[qsi["carrier"] == "AA"].set_index(["market_id", "month"])["qsi_share"].to_dict()
    qsi_xa = qsi[qsi["carrier"] == "XA"].set_index(["market_id", "month"])["qsi_share"].to_dict()
    fare = dict(zip(markets["market_id"], markets["base_fare_usd"]))
    target_pts = dict(zip(contracts["account_id"], contracts["share_target_vs_qsi_pts"]))

    rows = []
    for a in accounts.itertuples():
        managed = a.segment == "Managed"
        home = markets[markets["region"] == a.region]["market_id"].tolist()
        other = markets[markets["region"] != a.region]["market_id"].tolist()
        n_mkts = int(rng.integers(5, 10))
        acct_mkts = random.sample(home, min(len(home), n_mkts - 2)) + random.sample(other, 2)
        # Loyalty bias in logit space: some accounts sit well below fair share, some above
        bias = float(rng.normal(0.0, 0.6)) + 0.04 * target_pts.get(a.account_id, 0) / 5
        primary_agency = rng.choice(tmc_ids) if managed else rng.choice(np.concatenate([ota_ids, leisure_ids]))
        for mkt in acct_mkts:
            lam = float(rng.lognormal(np.log(6 if managed else 2), 0.5))
            for ms in month_starts:
                mkey = (mkt, ms.date().isoformat())
                trend = 0.15 * (ms.year - 2025 + ms.month / 12)  # gentle growth in AA preference over time
                n = int(rng.poisson(lam))
                if n == 0:
                    continue
                q = qsi_aa[mkey]
                p_aa = 1 / (1 + np.exp(-(np.log(q / (1 - q)) + bias + trend)))
                q_xa = qsi_xa[mkey]
                p_xa = (1 - p_aa) * q_xa / max(1 - q, 1e-6)
                carriers = rng.choice(["AA", "XA", "XB"], size=n, p=[p_aa, p_xa, max(0.0, 1 - p_aa - p_xa)])
                for c in carriers:
                    agency = primary_agency if rng.random() < 0.8 else rng.choice(agencies["agency_id"])
                    tier = tier_of[agency]
                    if tier == "TMC":
                        channel = rng.choice(["GDS", "NDC", "Direct"], p=[0.62, 0.33, 0.05])
                    elif tier == "OTA":
                        channel = rng.choice(["GDS", "NDC", "Direct"], p=[0.40, 0.52, 0.08])
                    else:
                        channel = rng.choice(["GDS", "NDC", "Direct"], p=[0.70, 0.20, 0.10])
                    premium = rng.random() < (0.16 if managed else 0.07)
                    revenue = fare[mkt] * (3.2 if premium else 1.0) * float(rng.lognormal(0, 0.18))
                    travel_day = int(rng.integers(1, 28))
                    travel_date = ms + pd.Timedelta(days=travel_day - 1)
                    booking_date = travel_date - pd.Timedelta(days=int(rng.integers(1, 45)))
                    biz_id = None
                    if a.segment == "SMB" and c == "AA":
                        biz_id = None if rng.random() < 0.09 else a.aadv_business_id
                    rows.append((booking_date.date().isoformat(), travel_date.date().isoformat(),
                                 a.account_id, agency, mkt, c, "Premium" if premium else "Main",
                                 channel, 1, round(revenue, 2), biz_id,
                                 "".join(random.choices(string.ascii_uppercase + string.digits, k=6))))

    bookings = pd.DataFrame(rows, columns=["booking_date", "travel_date", "account_id", "agency_id",
                                           "market_id", "carrier", "cabin", "channel", "pax",
                                           "revenue_usd", "aadv_business_id", "pnr"])
    bookings.insert(0, "ticket_id", [f"T{i:09d}" for i in range(1, len(bookings) + 1)])

    # Planted defects
    n = len(bookings)
    null_idx = rng.choice(n, size=int(n * 0.002), replace=False)
    bookings.loc[null_idx, "account_id"] = None
    bad_agency_idx = rng.choice(n, size=int(n * 0.001), replace=False)
    bookings.loc[bad_agency_idx, "agency_id"] = "A9999"
    bad_fare_idx = rng.choice(n, size=int(n * 0.001), replace=False)
    bookings.loc[bad_fare_idx, "revenue_usd"] = -bookings.loc[bad_fare_idx, "revenue_usd"].abs()
    dupes = bookings.sample(frac=0.005, random_state=seed)
    bookings = pd.concat([bookings, dupes], ignore_index=True)

    bookings["file_month"] = pd.to_datetime(bookings["travel_date"]).dt.strftime("%Y_%m")
    for fm, part in bookings.groupby("file_month"):
        part.drop(columns="file_month").to_csv(os.path.join(out_dir, "bookings", f"bookings_{fm}.csv"), index=False)

    # ---------- Reference files ----------
    markets.to_csv(os.path.join(out_dir, "markets.csv"), index=False)
    qsi.to_csv(os.path.join(out_dir, "qsi_market_month.csv"), index=False)
    ams.to_csv(os.path.join(out_dir, "account_managers.csv"), index=False)
    accounts.to_csv(os.path.join(out_dir, "accounts.csv"), index=False)
    contracts.to_csv(os.path.join(out_dir, "contracts.csv"), index=False)

    # ---------- Legacy Excel workbook (deliberately messy) ----------
    wb = Workbook()
    ws = wb.active
    ws.title = "Targets"
    ws["A1"] = "AGENCY INCENTIVE TARGETS FY2026 (maintained by Sales Ops, do not sort)"
    ws["A1"].font = Font(bold=True)
    ws["A2"] = "Last updated by hand; see notes column"
    ws.append([])
    ws.append(["Agency", "ARC #", "Tier", "Target AA Share", "Incentive Rate", "Notes"])
    for c in ws[4]:
        c.font = Font(bold=True)
    for tier in ["TMC", "OTA", "Leisure"]:
        tier_rows = agencies[agencies["tier"] == tier]
        for ag in tier_rows.itertuples():
            arc = ag.arc_number
            arc_fmt = random.choice([arc, f"{arc[:2]}-{arc[2:7]}-{arc[7:]}", f" {arc} "])
            target = round(float(rng.uniform(0.35, 0.65)), 2)
            target_fmt = random.choice([target, f"{int(target * 100)}%"])
            rate = round(float(rng.uniform(0.5, 4.0)), 1)
            rate_fmt = random.choice([rate / 100, f"{rate}%", f"{rate}%"]) if rng.random() > 0.05 else "TBD"
            note = random.choice(["", "", "", "renegotiated Q3", "pending legal", "verify ARC"])
            ws.append([ag.agency_name, arc_fmt, tier, target_fmt, rate_fmt, note])
        ws.append([f"{tier} Subtotal", None, None, None, None, f"{len(tier_rows)} agencies"])
        ws.append([])
    # Unity Catalog volumes don't support the random-access writes a zip-based .xlsx needs,
    # so save to local disk first and copy the finished file into the volume.
    import shutil, tempfile
    local_xlsx = os.path.join(tempfile.mkdtemp(), "Agency_Incentive_Targets_FY2026.xlsx")
    wb.save(local_xlsx)
    shutil.copy(local_xlsx, os.path.join(out_dir, "legacy", "Agency_Incentive_Targets_FY2026.xlsx"))

    return {"bookings_rows": len(bookings), "agencies": len(agencies), "accounts": len(accounts),
            "markets": len(markets), "months": months, "duplicates_planted": len(dupes),
            "reparented_agencies": len(reparented)}

# COMMAND ----------

summary = generate_all(OUT_DIR)
summary

# COMMAND ----------

display(dbutils.fs.ls(OUT_DIR))
