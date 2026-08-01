# Task: Build the Turtle Quant "Strategy" tab end-to-end

You are working in the `stock_dashboard_project` repo (Dash + Flask app, Python 3.13,
deployed on Render, data jobs run via GitHub Actions). Implement a **new "Turtle
Strategy" tab** that screens NSE stocks with Turtle Wealth's Quant Process and
classifies each into **ADD / HOLD / EXIT**. Build it end-to-end: data compute, a daily
cron, the data-manager loader, and the tab UI wired into `app.py`. Then review and test
every scenario.

Read `docs/TURTLE_STRATEGY_PLAN.md` first — it has the full analysis, data map, and the
locked decisions. This prompt is the authoritative build spec.

---

## 1. The strategy (what to compute)

Classify every stock using three signals plus a pre-decided exit:

- **ATH Price** — stock at/near all-time-high close.
- **ATH Profit** — trailing profit at an all-time high (proxied via EPS — see decisions).
- **Outperformance** — stock's 365-day return beats BOTH its **sector** AND the
  **benchmark** over the same window.
- **Above Exit Price** — Current_Price > 200-day SMA (exit-price proxy).

**3-box classifier (implement exactly):**
- **ADD (Strong Buy)** — meets ALL 3: ATH Price + ATH Profit + Outperformance.
- **HOLD** — meets ANY 2 of: ATH Profit, Above Exit Price (MA200), Outperformance.
- **EXIT / REPLACE (Sell)** — meets NONE or ANY 1 of those.

---

## 2. LOCKED decisions (do not change without asking)

1. **ATH Profit source** = **EPS-ATH proxy**. Use `stock_fundamentals_yearly.csv`
   (`ticker, year, eps`, 2000-2026). ATH-profit flag = current trailing profit ≥ prior
   max. Use TTM profit (Latest Quarter + Last 3Q from `NSE_EQ_All_Stocks_Analysis.csv`)
   as the "current" figure; compare against max historical eps-derived profit. No
   screener.in scraping in v1.
2. **Benchmark** = **BSE 500**, BUT BSE 500 is not on yfinance. **Use Nifty 500 as the
   proxy** (`^CRSLDX` on Yahoo; verify the ticker returns data, else fall back to a Nifty
   500 ETF like `MON100.NS`/`NIFTYBEES.NS`-style — pick one that fetches). Label the
   column/UI as "vs BSE 500 (Nifty 500 proxy)". If `^CRSLDX` fails, STOP and ask.
3. **Cadence** = **daily**, weekdays after NSE close (~16:00 IST).
4. **Exit price** = reuse existing **MA200** column (do NOT build a 212-day SMA).
5. **TTM Net Sales** = **omit** from v1 (no data source).
6. **Nifty 100 / 200 membership** = **in scope** — the Indices filter must work for
   Nifty 50 / 100 / 200 / All.

---

## 3. Reuse these (do NOT rewrite)

- **Tab pattern** — mirror `modules/v20_layout.py` + `modules/v20_callbacks.py` and the
  `modules/breakout/` package structure. Create a new `modules/turtle/` package the same way.
- **yfinance OHLCV** — use `modules/breakout/data_feed.py` (`get_daily`, `get_monthly`,
  cached, `.NS` suffix handled) for ATH price and 365-day returns. Do not write a new fetcher.
- **Data loading** — mirror the breakout loader in `data_manager.py` for a new
  `turtle_signals_df`.
- **MA data** — MA200 is already in `NSE_EQ_All_Stocks_Analysis.csv` and computed by
  `modules/ma_calculator.py`.
- **Index/sector membership** — `nse_categories.csv` (`Symbol, NSE_Categories`).
- **UI grid** — Dash `dash_table` + `assets/filter_sort.js` (same as other tabs).
- **Cron pattern + auto-commit** — copy `.github/workflows/breakout_signals.yml`.

---

## 4. Build steps (implement all)

1. **Extend Nifty membership** — in the `nse_categories` generation path used by
   `generate_weekly_stock_list.py` / `modules/stock_screener.py`, add **Nifty 100** and
   **Nifty 200** constituents so `nse_categories.csv` carries those tags. Keep it
   idempotent and backward compatible.

2. **`modules/turtle/compute.py`** — pure, testable functions:
   - `ath_price_flag(symbol)` → is latest close within X% of max historical close
     (make the threshold a constant, default e.g. 5%).
   - `ath_profit_flag(symbol)` → TTM profit vs max historical (eps-derived) profit.
   - `above_exit_flag(row)` → Current_Price > MA200.
   - `relative_strength(symbol, window=365)` → 365-day close-to-close return.
   - `outperformance_flag(symbol)` → stock RS beats BOTH sector-basket RS AND benchmark RS.
     Sector basket = equal-weight 365d return of the stock's sector constituents.
   - `classify(flags)` → "ADD" | "HOLD" | "EXIT" per §1.
   - Keep every function unit-testable with injected data (no hidden global state).

3. **`generate_turtle_signals.py`** — batch runner over the NSE universe → writes
   `turtle_signals_YYYYMMDD.csv` with columns: Symbol, Company, Sector, Industry,
   Current_Price, ATH_Price_Flag, TTM_Net_Profit, ATH_Profit_Flag, Above_MA200_Flag,
   RS_vs_Sector, RS_vs_Benchmark, Outperformance_Flag, Signal. Handle missing/невdata
   symbols gracefully (skip, log, never crash the batch).

4. **`.github/workflows/turtle_signals.yml`** — copy the breakout workflow; schedule
   `30 10 * * 1-5`; install `pandas numpy yfinance requests`; run the script;
   auto-commit `turtle_signals_*.csv`. Keep `workflow_dispatch` for manual runs.

5. **`data_manager.py`** — add `turtle_signals_df` + a loader mirroring the breakout
   loader (latest-dated file, cache, graceful empty-frame fallback).

6. **`modules/turtle/layout.py`** — tab UI:
   - Filters: **Indices** dropdown (Nifty 50 / 100 / 200 / All), **Sector** dropdown
     (from data + All), **Stock Name** dropdown, and **ATH-only** / **Yesterday** toggles.
   - Results `dash_table`: Stock Name, Sector, Industry, ATH Price flag, Net Profit /
     ATH Profit / TTM Net Profit, ATH Sales, Above MA200, RS vs Sector, RS vs Benchmark,
     and a coloured **Signal** badge (ADD green / HOLD amber / EXIT red).
   - (ATH Sales = max(sales) per ticker from `stock_fundamentals_yearly.csv`.)

7. **`modules/turtle/callbacks.py`** — filter → table wiring, following v20/breakout
   callback conventions (pattern-matching IDs, no duplicate output collisions).

8. **Wire into `app.py`** — add `dcc.Tab(label="Turtle Strategy", value="tab-turtle", …)`
   next to V20 / Breakout, register callbacks, and add the bottom-nav button for mobile.

---

## 5. Testing — cover ALL scenarios (required)

Add tests under `tests/` (match existing pytest style). Do not mark the task done until
these pass:

**Unit — classifier truth table (exhaustive):**
- ADD: all 3 true.
- HOLD: each of the 3 valid 2-of-3 combinations (using ATH Profit / Above-Exit / Outperf).
- EXIT: all "exactly 1 true" cases and the "0 true" case.
- Edge: ATH Price true but the HOLD set only counts {ATH Profit, Above-Exit, Outperf} —
  verify the box definitions in §1 are honoured precisely (ADD uses ATH **Price**; HOLD
  uses Above-Exit instead of ATH Price).

**Unit — compute functions:**
- ATH price flag with a synthetic rising series (True) and a series off its high (False).
- ATH profit flag: current ≥ historical max (True) and below (False).
- Above-MA200 flag both directions.
- Relative strength math on a known series (assert exact % ).
- Outperformance: stock beats both / beats one / beats neither.

**Data-integrity:**
- Missing symbol / empty yfinance response → function returns a safe default, batch skips.
- NaN handling in profit/sales/price columns.
- Symbol normalisation (upper/strip, `.NS` suffix).

**Filters:**
- Nifty 50 / 100 / 200 / All each return the right membership subset.
- Sector + Stock-Name + ATH-only filters combine correctly.

**End-to-end (mirror `test_stock_screener_e2e.py`):**
- Run `generate_turtle_signals.py` on a small fixed symbol list; assert output CSV
  schema, row count, and that Signal ∈ {ADD, HOLD, EXIT}.
- Load via `data_manager`, assert the tab renders and filters return rows.

Run the full suite (`pytest`) and confirm no regressions in existing tests.

---

## 6. Review & report back

After building and testing, do a thorough self-review and produce a short report covering:
- Files created/changed (with paths).
- The classifier truth table and confirmation it matches §1.
- Test results (pass/fail counts, coverage of the §5 scenarios).
- Any deviation from §2 decisions and why.
- The BSE 500 → Nifty 500 proxy: which ticker you used and whether it fetched.
- Known limitations (EPS-as-profit-proxy dilution, MA200-as-exit-proxy, no TTM sales).
- Anything you had to stub or leave for v2.

Do not silently change a locked decision — if something is blocked, stop and flag it.
When everything passes, summarise and hand back for my review.
