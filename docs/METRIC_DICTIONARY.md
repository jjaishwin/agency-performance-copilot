# Metric dictionary

Every metric below is defined **once** in a Unity Catalog metric view. Genie, dashboards and any agent use these definitions.

| Metric | Definition | Formula | Source | Notes |
|---|---|---|---|---|
| Passenger share | AA's share of all passengers | `SUM(aa_pax) / SUM(total_pax)` | `mv_account_performance` | Default meaning of "share" |
| Revenue share | AA's share of all ticket revenue | `SUM(aa_revenue) / SUM(total_revenue)` | `mv_account_performance`, `mv_agency_performance` | |
| Fair share (QSI) | Share AA's schedule should earn | `SUM(qsi_share × total_pax) / SUM(total_pax)` | `mv_account_performance` | Passenger-weighted; never average QSI |
| Share vs QSI (pts) | Gap to fair share | `(SUM(aa_pax) − SUM(qsi_share × total_pax)) / SUM(total_pax) × 100` | `mv_account_performance` | Negative = below fair share |
| Contract attainment | Actual share ÷ contracted target | `SUM(aa_pax) / SUM(target_share × total_pax)`, QSI-eligible markets only | `mv_account_performance` | Managed accounts only; < 0.90 = at risk |
| Target share | Contracted share | `MIN(qsi_share + contract points / 100, 0.95)` | `account_market_month` | Null for SMB |
| QSI-eligible | Market counts toward targets | `qsi_share ≥ 0.05` | `account_market_month` | Tiny-QSI markets distort "QSI + X" goals |
| Premium mix | Share of AA revenue from premium cabins | `SUM(aa_premium_revenue) / SUM(aa_revenue)` | `mv_account_performance` | |
| NDC share | Share of an agency's AA bookings made via NDC | `SUM(aa_ndc_bookings) / SUM(aa_bookings)` | `mv_agency_performance` | |
| Incentive cost | Incentive paid to agencies | `SUM(aa_revenue × incentive_rate)` | `mv_agency_performance` | Rates from the legacy Excel workbook |
| Revenue per incentive $ | AA revenue per incentive dollar | `SUM(aa_revenue) / SUM(incentive_cost_usd)` | `mv_agency_performance` | |
| Missing business ID % | SMB AA bookings without the AAdvantage Business ID | `SUM(missing_id_bookings) / SUM(aa_bookings)` | `aadv_business_compliance` | Uncredited trips |
