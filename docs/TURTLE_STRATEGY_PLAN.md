# Turtle Quant Strategy — Section Plan & Data-Level Analysis

Status: Draft for review · Date: 2026-08-01

This document plans a new **"Turtle Strategy"** tab based on Turtle Wealth's
Quant Process (turtlewealth.in/turtle-quant-process) and the handwritten screen
mock-up. It maps every strategy field to existing data, flags gaps, lists what
we reuse, and defines the cron jobs required.

---

## 1. The strategy, formalised

Turtle's Quant Process classifies every stock into one of three boxes using
three core signals plus a pre-decided exit:

| Signal | Meaning | Our data field |
|--------|---------|----------------|
| **ATH Price** | Stock at/near all-time-high price | max historical close (yfinance) |
| **ATH Profit** | Trailing profit at all-time high | annual net-profit history *(gap — see §4)* |
| **Outperformance** | Stock beats its **sector** AND the **index** over 365d | 365-day relative strength |
| **Turtle Exit Price** | Pre-decided downside stop | proxy = 212-day SMA |

**3-box classification (Turtle original):**
- **ADD / Strong Buy** — meets ALL 3: ATH Price + ATH Profit + Outperformance
- **HOLD** — meets ANY 2 of: ATH Profit, Above Exit Price (212 SMA), Outperformance
- **EXIT / REPLACE / Sell** — meets NONE or ANY 1

This matches the handwritten note exactly:
- *Strong Buy* = ATH price + ATH profit (net) + relative strength (sector) +
  relative strength (index) + above 212 SMA
- *Sell* = below SMA / below relative index / below ATP — "if only one then sell"

Turtle uses **BSE 500** as the benchmark and **Top 750** as the universe; the
note substitutes **Nifty indices** (Nifty 50 / 100 / 200). Decision needed (§6).

---

## 2. Screen mock-up → columns

Filters: **Indices** (Nifty 50/100/200/All) · **Sector** (Auto/Pharma/All) ·
**Stock Name** · flags for *All-time-high* and *Yesterday*.

Output columns:
1. Stock Name
2. Sector
3. Industry
4. All-time-high (price flag)
5. Net Profit / ATH Profit / TTM Net Profit
6. ATH Sales / TTM Net Sales
7. Stock price above 212 SMA
8. Relative Strength vs Sector
9. Relative Strength vs Indices
10. (derived) Signal = ADD / HOLD / EXIT

Relative strength = 365-day close-to-close return of the stock vs the same
window for the sector basket and the index.

---

## 3. Data available today (what we can use as-is)

| Source file / module | Provides | Rows |
|----------------------|----------|------|
| `NSE_EQ_All_Stocks_Analysis.csv` | Symbol, Company, **Sector, Industry**, Market Cap, **Net Profit (Cr)**, ROCE/ROE/D/E, **Latest Quarter Profit**, **Last 3Q Profits** (→ TTM profit), MA10/50/100/200, **Current_Price** | 2,365 |
| `stock_fundamentals_yearly.csv` | ticker, **year (2000-2026)**, **sales**, book_value, **eps**, growth %s, roce, market_cap, sector | 28,633 (2,263 tickers, ~12 yrs each) |
| `Master_company_market_trend_analysis.csv` | Screened shortlist (fundamentals only) | 216 |
| `nse_categories.csv` | **Index membership** (NIFTY 50, NIFTY PHARMA, NIFTY AUTO…) | ~370 |
| `modules/breakout/data_feed.py` | yfinance monthly/weekly/daily OHLCV, 10+ yrs, cached | — |
| `modules/ma_calculator.py` | MA computation from yfinance | — |
| `modules/stock_screener.py` | Universe build, Nifty membership logic | — |

**Directly satisfied by existing data:**
Stock Name, Sector, Industry, Net Profit, TTM Net Profit (Latest Q + Last 3Q),
MA200, Current_Price, index membership, and full annual **sales** history (→ ATH
Sales is computable now).

---

## 4. Data-level gaps (per strategy point)

| # | Strategy field | Have? | Gap / plan |
|---|----------------|-------|-----------|
| 1 | **ATH Price** | ✗ stored | Compute max historical close via `data_feed.get_monthly/daily`. New daily compute + store. |
| 2 | **212-day SMA** | ✗ (have MA200) | Add MA212 in `ma_calculator` (cheap). Or accept MA200 as proxy. |
| 3 | **Above 212 SMA** | ✗ | Derived once #2 exists: Current_Price > MA212. |
| 4 | **ATH Sales** | ✓ annual | `max(sales)` per ticker from yearly file. Ready. |
| 5 | **TTM Net Sales** | ✗ | Not in any file (NSE_EQ has profit TTM, not sales TTM). Needs screener.in quarterly scrape *or* drop this sub-column. |
| 6 | **ATH Net Profit** | ⚠ partial | No annual **net-profit** series stored. Options: (a) use **EPS-ATH** as proxy (have eps 2000-2026, but dilution distorts); (b) scrape annual net profit from screener.in (parsers already exist: `enhanced_screener_parser.py`, `screener_de_analysis.py`). |
| 7 | **TTM Net Profit** | ✓ | Latest Quarter + Last 3Q in NSE_EQ. Ready. |
| 8 | **RS vs Sector** | ✗ | Need 365d return of a **sector basket / Nifty sector index**. Build equal-weight sector return from constituents, or fetch Nifty sector index via yfinance. New compute. |
| 9 | **RS vs Index** | ✗ | Need 365d index return (^NSEI / Nifty100 / Nifty200) via yfinance, vs stock 365d return. New fetch + compute. |
| 10 | **Nifty 100 / 200 membership** | ⚠ | `nse_categories.csv` currently carries NIFTY 50 but not 100/200 index constituents. Need to extend the categories scrape to include Nifty 100/200 lists. |
| 11 | **Turtle Exit Price** | ✗ | Using 212 SMA as the exit proxy (per note). True Turtle exit is ATR/volatility-based — out of scope v1. |

---

## 5. What we reuse vs build new

**Reuse (no rewrite):**
- Tab pattern — clone `modules/v20_layout.py` + `v20_callbacks.py` → `modules/turtle/`.
- Data loading pattern in `data_manager.py` (add a `turtle_signals_df` loader).
- `modules/breakout/data_feed.py` for cached yfinance OHLCV (ATH price, SMA, RS).
- `modules/ma_calculator.py` (extend to 212).
- `nse_categories.csv` for the Indices/Sector filters.
- Dash `dash_table` + `assets/filter_sort.js` for the screener grid.
- GitHub Actions workflow pattern + auto-commit of the output CSV.

**Build new:**
- `modules/turtle/compute.py` — ATH price, 212 SMA flag, 365d RS vs sector & index, ADD/HOLD/EXIT classifier.
- `modules/turtle/layout.py` + `callbacks.py` — the tab UI (filters + table).
- `generate_turtle_signals.py` — batch script the cron runs; writes `turtle_signals_YYYYMMDD.csv`.
- Extend `nse_categories` scrape to add Nifty 100/200 constituents.
- (If ATH profit via scrape) extend screener parser to persist annual net-profit history.

---

## 6. Cron jobs

**Existing jobs that already feed this strategy:**
- `weekly_stock_screening.yml` (Sun 00:30 UTC) → rebuilds `NSE_EQ_All_Stocks_Analysis.csv`, `Master_…csv`, `nse_categories.csv`. Supplies sector/industry/profit/TTM/membership. **Reuse — extend it to also refresh Nifty 100/200 membership and (optionally) annual net-profit history.**
- `delivery_data_download.yml` / `breakout_signals.yml` — not required, but the breakout `data_feed` cache they warm is shared.

**New job required:**
- `turtle_signals.yml` — runs `generate_turtle_signals.py` after market close on weekdays (price-driven fields: ATH price, 212 SMA, RS). Suggested cron `30 10 * * 1-5` (≈16:00 IST), chained after delivery/breakout jobs. Commits `turtle_signals_YYYYMMDD.csv`.
  - Cadence question: **daily** (price signals change daily) vs **weekly** (Turtle is a low-churn, long-horizon process). Recommend daily compute, weekly review.

---

## 7. Decisions (LOCKED 2026-08-01)

1. **ATH Profit** → **EPS-ATH proxy** using existing eps history (2000-2026). No scrape in v1.
2. **Benchmark** → **BSE 500** (Turtle original) for the outperformance test. Universe
   *filters* still use Nifty membership; the RS benchmark is BSE 500. See caveat below.
3. **Cadence** → **Daily** after market close (weekday), ≈16:00 IST.
4. **212 SMA** → **reuse existing MA200** as the exit-price proxy (not building 212).
5. **TTM Net Sales** → **dropped** from v1 (no source). Column omitted.
6. **Nifty 100/200 membership** → **in scope** — extend the categories scrape so the
   Indices filter works beyond Nifty 50.

### ⚠ Caveat on BSE 500 (decision 2)
BSE 500 is not cleanly available on yfinance (Yahoo has Sensex `^BSESN`, not BSE 500).
For the benchmark return we will need one of: (a) a BSE 500 index/ETF price series from
an alternative source, (b) build an equal-weight BSE 500 basket from constituents, or
(c) use **Nifty 500** as a near-equivalent proxy (nearly identical large+mid+small
coverage, easy yfinance access). Recommend (c) Nifty 500 as the practical stand-in for
BSE 500, labelled clearly in the UI. Confirm at build time.

---

## 8. Implementation roadmap (v1)

1. **Membership** — extend the `nse_categories` scrape (in `weekly_stock_screening`) to
   add Nifty 100 & Nifty 200 constituents.
2. **`modules/turtle/compute.py`**:
   - ATH price = max historical close via `breakout/data_feed.get_daily/monthly`.
   - ATH-profit proxy = max(eps) per ticker from `stock_fundamentals_yearly.csv`;
     current TTM profit = Latest Q + Last 3Q from `NSE_EQ…csv`; ATH-profit flag =
     current ≥ prior ATH.
   - Above-exit flag = Current_Price > MA200.
   - RS: 365d close return of stock vs sector basket AND vs benchmark (Nifty 500 proxy);
     outperformance = beats both.
   - Classifier → ADD / HOLD / EXIT per §1.
3. **`generate_turtle_signals.py`** — batch runner → writes `turtle_signals_YYYYMMDD.csv`.
4. **`.github/workflows/turtle_signals.yml`** — `30 10 * * 1-5`, auto-commit output.
5. **`data_manager.py`** — add `turtle_signals_df` loader (mirror breakout loader).
6. **`modules/turtle/layout.py` + `callbacks.py`** — tab: Indices/Sector/Stock-Name
   filters + ATH & Yesterday flags + results table with the §2 columns and Signal badge.
7. **Wire tab** into `app.py` (`dcc.Tab` + bottom-nav) alongside V20 / Breakout.
8. **Verify** — unit-test the classifier against hand-picked tickers; sanity-check a
   known ADD name (e.g. an ATH large-cap) end-to-end.
