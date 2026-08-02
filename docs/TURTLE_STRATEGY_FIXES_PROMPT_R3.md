# Task: Turtle Strategy — stale-price fix + cron refresh (round 3)

Context: live validation of the deployed Turtle tab found the **displayed Current Price
and the Above-MA200 flag are stale** (reading ~May-16 values from
`NSE_EQ_All_Stocks_Analysis.csv`), while the ATH-Price flag correctly uses the live
yfinance close. This produces contradictory rows and wrong signals.

Validated evidence (NSE close, 30–31 Jul 2026):

| Stock | Displayed price | Real price | TTM Net Profit shown | Verdict |
|---|---|---|---|---|
| ICICIBANK | 1244.5 | 1435.4 (−13%) | 54,207 (correct) | price stale; Above-MA200=false is WRONG (real 1435 >> 200-DMA) → should flip EXIT→HOLD |
| TITAN | 4169.1 | 4875.2 (−15%) | 4,825 (~correct) | price stale |
| JSWSTEEL | 1278.8 | 1276.2 (flat since May) | 6,543 (~correct) | coincidental match, still stale source |

Root cause: the Turtle pipeline uses live yfinance data for the ATH-Price flag and RS,
but reads **Current_Price and MA200 from the stale weekly CSV** for the displayed price
and the `above_exit_flag`. And the weekly screening cron hasn't refreshed that CSV since
~May 16, 2026.

Do NOT change the classifier or the locked decisions (`docs/TURTLE_STRATEGY_PLAN.md §7`).
These are data-freshness fixes. Report back with before/after evidence.

---

## Fix 1 — Use live price + live 200-DMA in the Turtle screen [HIGH]

**Where:** `modules/turtle/screener.py::run_pipeline`. The pipeline already fetches ~2y
of live daily closes per symbol (`daily_close`) for RS and the ATH reference. Use that
same series for the price-based display and flag instead of the stale CSV.

**Do:**
- **Displayed price:** set the output `Current_Price` to the **live** last daily close
  (`ath_reference_price` already equals this) when daily data is available; fall back to
  the CSV `Current_Price` only when daily is missing. Consider renaming the output column
  intent in a comment so it's clear this is the live close, not the CSV snapshot.
- **Above-exit flag:** compute a **live 200-day SMA** from the daily closes
  (`daily_close.rolling(200).mean().iloc[-1]`, guarding for `< 200` rows → fall back to
  CSV `MA200`, and if that's also missing → `None`/flag False). Pass the **live close**
  and this **live MA200** into `compute.above_exit_flag` so the price and the average are
  from the same fresh series.
- Keep `ath_profit_flag` inputs as-is (TTM profit + market cap + max EPS): those are
  fundamentals that change quarterly, not a freshness problem — but use the **live close**
  for the `current_price` arg there too, so the derived share count / EPS is internally
  consistent with the price actually shown.
- Add a `MA200_source` or similar note in a comment (live vs csv-fallback) so a future
  reader knows which path produced the value.

**Result to verify:** the "ATH Price = true but Above-MA200 = false" contradiction for a
stock trading near its high (e.g. ICICIBANK) must disappear — a stock at/near ATH is by
definition above its 200-DMA, so both flags should agree.

**Tests (extend `tests/test_turtle_screener.py`):**
- Synthetic daily series where the last close is near the max and well above the rolling
  200-DMA → `ATH_Price_Flag = True` AND `Above_MA200_Flag = True` (no contradiction).
- `< 200` daily rows → falls back to CSV MA200; CSV MA200 missing too → flag False, no crash.
- Displayed `Current_Price` equals the live last daily close when daily present, and the
  CSV value only when daily is absent.

---

## Fix 2 — Refresh the stale fundamentals CSV + investigate the cron [HIGH]

`NSE_EQ_All_Stocks_Analysis.csv` (and `Master_company_market_trend_analysis.csv`,
`nse_categories.csv`) are the weekly-screening outputs and are ~2.5 months stale.

**Do:**
1. Inspect `.github/workflows/weekly_stock_screening.yml` and `generate_weekly_stock_list.py`
   for why the last successful refresh was ~May 16 (check for a silently-failing step,
   an exception that still exits 0, a data-source/endpoint change, or a commit/push that
   isn't happening). Report the likely cause.
2. Run the weekly screening **locally** now to produce a fresh CSV:
   `python generate_weekly_stock_list.py` — capture the console output, confirm it writes
   updated `NSE_EQ_All_Stocks_Analysis.csv` with a current `Screening Date` and fresh
   `Current_Price`/`MA200`, and note how many symbols it processed.
3. If it fails, fix the failure (or document exactly where it breaks) rather than leaving
   it stale.

---

## Fix 3 — Run the Turtle job fresh and observe [HIGH]

After Fix 1 (and ideally Fix 2's refreshed CSV):

1. Run `python generate_turtle_signals.py --limit 25` and **observe the output**:
   - Confirm displayed prices now match live NSE prices for a few names
     (ICICIBANK ≈ 1435, TITAN ≈ 4875, JSWSTEEL ≈ 1276 — spot-check against a live source).
   - Confirm no "ATH Price true / Above-MA200 false" contradictions for near-high stocks.
   - Print the ADD/HOLD/EXIT distribution and confirm ICICIBANK moved EXIT→HOLD.
2. Then run the **full** batch `python generate_turtle_signals.py` (expect ~30–60 min of
   yfinance calls; use the `--pause` pacing) to produce the real dated
   `turtle_signals_YYYYMMDD.csv`. Report row count, signal distribution, and rejections.
3. If running the GitHub Actions path instead, trigger `turtle_signals.yml` via
   `workflow_dispatch` and confirm it commits a fresh file on the production path.

---

## Report back

- Files changed + what each fix does.
- Before/after table for ICICIBANK, TITAN, JSWSTEEL (displayed price, Above-MA200 flag,
  Signal) showing the stale→live correction.
- Root-cause finding for the stale weekly CSV, and whether the local refresh succeeded.
- New/updated test names + full-suite pass/fail (confirm 0 regressions).
- Confirm classifier and locked decisions untouched.
