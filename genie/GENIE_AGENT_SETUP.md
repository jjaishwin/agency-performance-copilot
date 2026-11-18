# Genie Agent setup: "Agency Performance Copilot"

Genie Agents were called Genie Spaces until July 2026. Some screens and APIs may still say "space". This guide uses the current name.

Replace `workspace` with your catalog name everywhere below if yours is different.

---

## 1. Create the agent

1. In the left sidebar, open **Genie** and choose **New**.
2. **Title:** `Agency Performance Copilot`
3. **Description** (users see this):
   > Ask about AA passenger share, fair share (QSI), contract attainment, agency revenue share, NDC adoption, incentive cost and AAdvantage Business compliance. Built on certified Unity Catalog tables. Synthetic data for demonstration.
4. **Data:** add these five objects. Databricks recommends five or fewer; a small, curated set beats a big one.

| Object | Why |
|---|---|
| `workspace.gold.mv_account_performance` | Certified account metrics (metric view) |
| `workspace.gold.mv_agency_performance` | Certified agency metrics (metric view) |
| `workspace.gold.account_market_month` | Detail behind account metrics |
| `workspace.gold.agency_month` | Detail behind agency metrics |
| `workspace.gold.aadv_business_compliance` | AAdvantage Business ID compliance |

**Optional, after notebook 07:** to let Genie answer "which accounts are at risk?" and "what are the talking points for X?", swap `account_market_month` for `workspace.gold.account_scorecard`. That keeps the total at five. The metric view still covers detail by market and month. Re-run all benchmarks after the swap: B-questions that query `account_market_month` directly should still pass through the metric view; any that fail tell you which detail Genie still needs.

5. **Compute:** your serverless SQL warehouse.

---

## 2. General instructions

Paste this into **Instructions → Text**:

```
You answer questions for an airline's Global Sales account managers and sales leaders. All data is synthetic.

Definitions (always use these):
- "Share" means passenger share (AA passengers / all-carrier passengers) unless the user says "revenue share".
- "Fair share" and "QSI" mean the passenger-weighted QSI: SUM(qsi_share * total_pax) / SUM(total_pax). Never average qsi_share directly.
- "Share gap" or "share vs QSI" = passenger share minus fair share, in percentage points.
- "Contract attainment" = SUM(aa_pax) / SUM(target_share * total_pax), using only rows where qsi_eligible is true. Only Managed accounts have contracts.
- An account is "at risk" when contract attainment is below 0.90.
- "YTD" or "so far this year" means from 2026-01-01 through the latest month in the data (2026-10-01).
- Quarters are calendar quarters. Q3 2026 = months 2026-07-01 to 2026-09-01.
- AA is the home carrier in this synthetic data. XA and XB are competitors.
- "Agencies" are travel agencies in agency_month. Tiers are TMC, OTA and Leisure. Use parent_tmc_asof for parent company questions.

Rules:
- Always compute ratios as SUM(numerator) / SUM(denominator). Never average percentages.
- Prefer the metric views (mv_account_performance, mv_agency_performance) and use MEASURE() for their measures.
- Show percentages to one decimal place and currency in USD with no decimals.
- If a question is ambiguous (for example "share" over an unspecified period), ask which period, or state the assumption you used.
- Never return PNR or traveler-level fields.
```

---

## 3. SQL expressions

In **Instructions → SQL expressions**, add these so Genie computes key metrics the same way every time.

**Measures** (table: `account_market_month`)

| Name | Expression | Synonyms |
|---|---|---|
| passenger share | `SUM(aa_pax) / SUM(total_pax)` | share, pax share |
| fair share | `SUM(qsi_share * total_pax) / SUM(total_pax)` | QSI, expected share |
| share gap pts | `(SUM(aa_pax) - SUM(qsi_share * total_pax)) / SUM(total_pax) * 100` | share vs QSI |
| contract attainment | `SUM(CASE WHEN qsi_eligible THEN aa_pax END) / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END)` | attainment |

**Filters**

| Name | Expression |
|---|---|
| managed accounts | `segment = 'Managed'` |
| this year | `month >= DATE'2026-01-01'` |
| eligible markets | `qsi_eligible = true` |

---

## 4. Example SQL queries

In **Instructions → SQL queries**, add these five as trusted examples. Use the question as the title.

**Which managed accounts are at risk this year?**
```sql
SELECT account_name, account_manager,
       SUM(CASE WHEN qsi_eligible THEN aa_pax END)
         / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END) AS contract_attainment
FROM workspace.gold.account_market_month
WHERE segment = 'Managed' AND month >= DATE'2026-01-01'
GROUP BY account_name, account_manager
HAVING SUM(CASE WHEN qsi_eligible THEN aa_pax END)
         / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END) < 0.90
ORDER BY contract_attainment
```

**What is our share versus fair share by region this year?**
```sql
SELECT region,
       MEASURE(passenger_share)  AS passenger_share,
       MEASURE(fair_share_qsi)   AS fair_share,
       MEASURE(share_vs_qsi_pts) AS share_gap_pts
FROM workspace.gold.mv_account_performance
WHERE month >= DATE'2026-01-01'
GROUP BY region
ORDER BY share_gap_pts
```

**Which agencies have the highest NDC adoption this year?**
```sql
SELECT agency_name, agency_tier, MEASURE(ndc_share) AS ndc_share, MEASURE(aa_revenue) AS aa_revenue
FROM workspace.gold.mv_agency_performance
WHERE month >= DATE'2026-01-01'
GROUP BY agency_name, agency_tier
ORDER BY ndc_share DESC
LIMIT 10
```

**Which markets are below fair share for an account?**
```sql
SELECT market_name,
       SUM(total_pax) AS total_pax,
       SUM(aa_pax) / SUM(total_pax) AS passenger_share,
       SUM(qsi_share * total_pax) / SUM(total_pax) AS fair_share
FROM workspace.gold.account_market_month
WHERE account_name = :account_name AND month >= DATE'2026-01-01'
GROUP BY market_name
HAVING SUM(aa_pax) / SUM(total_pax) < SUM(qsi_share * total_pax) / SUM(total_pax)
ORDER BY total_pax DESC
```
(Add `account_name` as a parameter when Genie offers it, or replace `:account_name` with a real name.)

**How much AA revenue does each dollar of incentive buy, by agency tier?**
```sql
SELECT agency_tier, MEASURE(incentive_cost) AS incentive_cost,
       MEASURE(aa_revenue) AS aa_revenue, MEASURE(revenue_per_incentive_dollar) AS revenue_per_incentive_dollar
FROM workspace.gold.mv_agency_performance
WHERE month >= DATE'2026-01-01'
GROUP BY agency_tier
ORDER BY revenue_per_incentive_dollar DESC
```

---

## 5. Entity matching (value dictionaries)

In each table's settings, turn on value sampling or entity matching for these columns, so "Northeast", "DFW-LAX" or a misspelled agency name map to real values:

`region`, `segment`, `account_name`, `account_manager`, `market_name`, `agency_name`, `agency_tier`, `parent_tmc_asof`

---

## 6. Benchmarks: your release gate

Open **Benchmarks → Add benchmark**. For each question, paste the question and the SQL answer. Then choose **Run all benchmarks** and record the score in `docs/EVAL_REPORT.md`.

The rule: **when a benchmark fails, fix the cause** (a column comment, a join, an SQL expression, an instruction), then re-run *all* benchmarks. Don't patch a single question.

Before you start, replace `[Account X]` in benchmark 15 with a real managed account name. Get one with:
`SELECT account_name FROM workspace.gold.dim_account WHERE segment = 'Managed' LIMIT 5`

### B1. What was AA's passenger share by region in Q3 2026?
```sql
SELECT region, SUM(aa_pax) / SUM(total_pax) AS passenger_share
FROM workspace.gold.account_market_month
WHERE month BETWEEN DATE'2026-07-01' AND DATE'2026-09-01'
GROUP BY region
ORDER BY region
```

### B2. Which 10 managed accounts have the lowest contract attainment so far this year?
```sql
SELECT account_name,
       SUM(CASE WHEN qsi_eligible THEN aa_pax END)
         / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END) AS contract_attainment
FROM workspace.gold.account_market_month
WHERE segment = 'Managed' AND month >= DATE'2026-01-01'
GROUP BY account_name
ORDER BY contract_attainment ASC
LIMIT 10
```

### B3. How many managed accounts are at risk this year?
```sql
WITH a AS (
  SELECT account_id,
         SUM(CASE WHEN qsi_eligible THEN aa_pax END)
           / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END) AS contract_attainment
  FROM workspace.gold.account_market_month
  WHERE segment = 'Managed' AND month >= DATE'2026-01-01'
  GROUP BY account_id
)
SELECT COUNT(*) AS at_risk_accounts FROM a WHERE contract_attainment < 0.90
```

### B4. Which account managers have the most at-risk accounts this year?
```sql
WITH a AS (
  SELECT account_manager, account_id,
         SUM(CASE WHEN qsi_eligible THEN aa_pax END)
           / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END) AS contract_attainment
  FROM workspace.gold.account_market_month
  WHERE segment = 'Managed' AND month >= DATE'2026-01-01'
  GROUP BY account_manager, account_id
)
SELECT account_manager, COUNT(*) AS at_risk_accounts
FROM a WHERE contract_attainment < 0.90
GROUP BY account_manager
ORDER BY at_risk_accounts DESC
```

### B5. Which markets are below AA's fair share so far this year?
```sql
SELECT market_name,
       (SUM(aa_pax) - SUM(qsi_share * total_pax)) / SUM(total_pax) * 100 AS share_vs_qsi_pts
FROM workspace.gold.account_market_month
WHERE month >= DATE'2026-01-01'
GROUP BY market_name
HAVING (SUM(aa_pax) - SUM(qsi_share * total_pax)) / SUM(total_pax) < 0
ORDER BY share_vs_qsi_pts
```

### B6. Which 10 agencies had the largest drop in AA revenue share from Q2 to Q3 2026?
```sql
WITH q AS (
  SELECT agency_id, agency_name,
         SUM(CASE WHEN month BETWEEN DATE'2026-04-01' AND DATE'2026-06-01' THEN aa_revenue END)
           / SUM(CASE WHEN month BETWEEN DATE'2026-04-01' AND DATE'2026-06-01' THEN total_revenue END) AS q2_share,
         SUM(CASE WHEN month BETWEEN DATE'2026-07-01' AND DATE'2026-09-01' THEN aa_revenue END)
           / SUM(CASE WHEN month BETWEEN DATE'2026-07-01' AND DATE'2026-09-01' THEN total_revenue END) AS q3_share
  FROM workspace.gold.agency_month
  WHERE month BETWEEN DATE'2026-04-01' AND DATE'2026-09-01'
  GROUP BY agency_id, agency_name
)
SELECT agency_name, q2_share, q3_share, q3_share - q2_share AS change
FROM q
WHERE q2_share IS NOT NULL AND q3_share IS NOT NULL
ORDER BY change ASC
LIMIT 10
```

### B7. What is the NDC share of AA bookings by agency tier this year?
```sql
SELECT agency_tier, SUM(aa_ndc_bookings) / SUM(aa_bookings) AS ndc_share
FROM workspace.gold.agency_month
WHERE month >= DATE'2026-01-01'
GROUP BY agency_tier
ORDER BY ndc_share DESC
```

### B8. What percent of SMB AA bookings were missing the AAdvantage Business ID in October 2026?
```sql
SELECT SUM(missing_id_bookings) / SUM(aa_bookings) * 100 AS pct_missing_business_id
FROM workspace.gold.aadv_business_compliance
WHERE month = DATE'2026-10-01'
```

### B9. How does premium mix compare between Managed and SMB accounts this year?
```sql
SELECT segment, SUM(aa_premium_revenue) / SUM(aa_revenue) AS premium_mix
FROM workspace.gold.account_market_month
WHERE month >= DATE'2026-01-01'
GROUP BY segment
```

### B10. What was incentive cost versus AA revenue by agency tier this year?
```sql
SELECT agency_tier,
       SUM(incentive_cost_usd) AS incentive_cost_usd,
       SUM(aa_revenue) AS aa_revenue,
       SUM(aa_revenue) / SUM(incentive_cost_usd) AS revenue_per_incentive_dollar
FROM workspace.gold.agency_month
WHERE month >= DATE'2026-01-01'
GROUP BY agency_tier
ORDER BY incentive_cost_usd DESC
```

### B11. Show monthly AA revenue for 2026.
```sql
SELECT month, SUM(aa_revenue) AS aa_revenue
FROM workspace.gold.account_market_month
WHERE month >= DATE'2026-01-01'
GROUP BY month
ORDER BY month
```

### B12. Which 5 Northeast accounts grew AA revenue the most, January–October 2026 versus the same months of 2025?
```sql
SELECT account_name,
       SUM(CASE WHEN month BETWEEN DATE'2026-01-01' AND DATE'2026-10-01' THEN aa_revenue ELSE 0 END)
     - SUM(CASE WHEN month BETWEEN DATE'2025-01-01' AND DATE'2025-10-01' THEN aa_revenue ELSE 0 END) AS revenue_growth_usd
FROM workspace.gold.account_market_month
WHERE region = 'Northeast'
GROUP BY account_name
ORDER BY revenue_growth_usd DESC
LIMIT 5
```

### B13. Which parent TMC drove the most AA revenue this year?
```sql
SELECT parent_tmc_asof AS parent_tmc, SUM(aa_revenue) AS aa_revenue
FROM workspace.gold.agency_month
WHERE month >= DATE'2026-01-01' AND parent_tmc_asof IS NOT NULL
GROUP BY parent_tmc_asof
ORDER BY aa_revenue DESC
```

### B14. How many managed accounts are at or above their contract target this year?
```sql
WITH a AS (
  SELECT account_id,
         SUM(CASE WHEN qsi_eligible THEN aa_pax END)
           / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END) AS contract_attainment
  FROM workspace.gold.account_market_month
  WHERE segment = 'Managed' AND month >= DATE'2026-01-01'
  GROUP BY account_id
)
SELECT COUNT(*) AS accounts_on_or_above_target FROM a WHERE contract_attainment >= 1.0
```

### B15. For [Account X], what is passenger share versus fair share in its top 5 markets this year?
```sql
SELECT market_name,
       SUM(total_pax) AS total_pax,
       SUM(aa_pax) / SUM(total_pax) AS passenger_share,
       SUM(qsi_share * total_pax) / SUM(total_pax) AS fair_share
FROM workspace.gold.account_market_month
WHERE account_name = '[Account X]' AND month >= DATE'2026-01-01'
GROUP BY market_name
ORDER BY total_pax DESC
LIMIT 5
```

---

## 7. Monitor and share

- **Monitoring tab:** review real questions, thumbs-down feedback and the SQL Genie generated. Any new type of question becomes a new benchmark.
- **Share:** give "Can run" access to a colleague, or open it in Genie One to see the end-user experience. Screenshot both for your README.
- **Iteration log:** record each change and the benchmark score before and after in `docs/EVAL_REPORT.md`. This log is the most impressive artifact in the project.
