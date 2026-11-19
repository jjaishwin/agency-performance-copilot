# Advanced SQL in this project

Two places use advanced SQL:

1. **The pipeline** (notebooks 03 and 04), where it makes the data correct.
2. **The Genie advanced tier** (benchmarks A1–A10 in `genie/GENIE_AGENT_SETUP.md`), which tests whether Genie can write it. These ten are tracked separately and don't block a release.

All tables are synthetic. Each pattern below says what it's for, the core idea, and the mistake it avoids.

---

## In the pipeline

### Deduplicate: keep the latest load of each ticket (notebook 03)
```sql
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY ticket_id ORDER BY _ingested_at DESC, _source_file DESC) AS rn
  FROM bronze.bookings
) WHERE rn = 1
```
`ROW_NUMBER`, not `RANK`: two loads with the same timestamp would both get rank 1 and the duplicate would survive. The second ordering column breaks ties deterministically. Rows with `rn > 1` go to a quarantine table, not the bin.

### Slowly changing dimension, Type 2 (notebook 03)
A `MERGE` closes the current row (`is_current = false`, `effective_to` = day before the change) and inserts a new one when an agency's parent company, name or tier changes. The trick is the staged source: every changed agency appears **twice**, once with its key (to match and close the old row) and once with a `NULL` key (so it can't match, and gets inserted as the new current row). `<=>` is null-safe equality, so a `NULL` parent company compares correctly.

### As-of join (notebook 04)
```sql
LEFT JOIN dim_agency_history ag
  ON b.agency_id = ag.agency_id
 AND b.travel_date >= ag.effective_from
 AND b.travel_date <= COALESCE(ag.effective_to, DATE'9999-12-31')
```
Each booking gets the agency attributes **that were true on the travel date**. Joining to the current row instead would silently move last year's revenue to this year's parent company.

### Weighted ratios, never averaged percentages (everywhere)
```sql
SUM(aa_pax) / SUM(total_pax)                                   -- passenger share
SUM(qsi_share * total_pax) / SUM(total_pax)                    -- fair share (QSI), passenger-weighted
SUM(CASE WHEN qsi_eligible THEN aa_pax END)
  / SUM(CASE WHEN qsi_eligible THEN target_share * total_pax END)  -- contract attainment
```
`AVG(share)` would let a market of 3 passengers count as much as one of 3,000. Conditional aggregation applies the eligibility rule inside the ratio, so ineligible markets drop out of both numerator and denominator.

---

## Genie advanced tier (A1–A10)

| # | Question (short) | Pattern | Mistake it catches |
|---|---|---|---|
| A1 | Month-over-month change in share by region | `LAG() OVER (PARTITION BY region ORDER BY month)` | Filtering to Feb–Oct **before** the window makes February's change NULL. Compute the window first, then filter (`QUALIFY`). |
| A2 | Each account manager's lowest-attainment account | `ROW_NUMBER() OVER (PARTITION BY account_manager ORDER BY attainment) = 1` | `MIN(attainment)` gives the value, not the account. |
| A3 | Top 3 markets by revenue in each region | Top-N per group with `QUALIFY ROW_NUMBER() … <= 3` | A global `LIMIT 3` returns 3 rows, not 3 per region. |
| A4 | Fewest accounts that make up 80% of revenue | Running total: `SUM() OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING) / SUM() OVER ()` | Counting accounts with cumulative share **≤ 80%** is off by one: you need the first account that **crosses** 80%. |
| A5 | Markets below fair share 3+ months in a row | Gaps and islands: `ROW_NUMBER() OVER (month) − ROW_NUMBER() OVER (below, month)` | Counting below-fair-share months finds markets with 3 bad months, not 3 **consecutive** ones. |
| A6 | Rolling 3-month revenue | `SUM() OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` | Same as A1: filter after the window, or April loses February and March. |
| A7 | Agencies with 2025 revenue but none in 2026 | Anti-join: `NOT EXISTS (… same agency_id …)` | **Matching on name.** Two agencies were renamed ("X Travel" → "X Travel Group"). By name they look lost; by ID they're still booking. The correct answer is **none**. |
| A8 | Each tier's percent of total revenue | Window over an aggregate: `SUM(revenue) / SUM(SUM(revenue)) OVER ()` | A second query or a hard-coded total. |
| A9 | Median attainment by region | `percentile_cont(0.5) WITHIN GROUP (ORDER BY attainment)` | Using the mean: a few accounts far above target pull it up. |
| A10 | Revenue by region, one column per quarter | Pivot with conditional aggregation | Returning a long table (region, quarter, revenue) when columns were asked for. |

`QUALIFY` filters on a window function without a subquery. It's supported in Databricks SQL; in engines without it, wrap the query and filter in the outer `SELECT`.

---

## How the benchmarks are scored

A benchmark passes when the row count matches and every column of the expected answer has a matching column in Genie's result (same values, any order, numbers to 4 significant figures; percent-vs-ratio scale is accepted). Notebook 09 runs both tiers; only the core 15 gate a release. See `docs/EVAL_REPORT.md` for results.
