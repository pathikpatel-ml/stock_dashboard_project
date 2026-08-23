"""
Thresholds for the Turtle Strategy screener (docs/TURTLE_STRATEGY_PLAN.md, LOCKED decisions).

Named here, never inlined, so a rule change is a one-line diff and the unit tests can assert
the documented values are followed literally.
"""

# ---------------------------------------------------------------------------
# ATH Price (plan §1) — "at/near all-time-high close"
# ---------------------------------------------------------------------------
ATH_PRICE_THRESHOLD_PCT = 5.0  # within 5% of the historical max close counts as ATH

# yfinance sometimes returns a single degenerate "monthly" row -- today's live quote mislabeled
# as a historical monthly candle -- for tickers with limited Yahoo Finance coverage. Verified
# live (2026-08-22): 7 of the 10 SECTORAL_INDEX_TICKERS below (AUTO, ENERGY, FMCG, MEDIA,
# METAL, PSU BANK, REALTY) do this consistently and reproducibly; only BANK/IT/PHARMA return
# real multi-year monthly history. Treating that single point as the historical max corrupted
# the Sector Pulse ATH flag for every affected sector (sometimes True, sometimes False,
# depending on how that one live quote happened to compare to itself). Individual NSE equities
# were checked too (RELIANCE/TCS/TATASTEEL/ITC: 289-368 rows; even young listings like
# IREDA/NYKAA/PAYTM: 34-58 rows) and none showed this pattern, so 12 (a full year) rejects only
# genuinely-degenerate responses, not real young-but-legitimate listings.
MIN_MONTHLY_ROWS_FOR_ATH = 12

# ---------------------------------------------------------------------------
# Outperformance / relative strength (plan §1, §2). SUPERSEDES the original daily-close,
# 365-calendar-day lookback -- now weekly-bucketed (each week's HIGHEST daily close, not its
# last trading day's close), latest week vs. exactly 52 weeks earlier. Avoids day-of-week
# noise inherent in picking "whichever daily close happens to land ~365 days back".
# ---------------------------------------------------------------------------
RS_WINDOW_WEEKS = 52  # weekly-high-close return window for stock / sector / benchmark

# Sector-RS peer group (added 2026-08-15): prefer NSE's own curated sectoral index (NIFTY
# BANK, NIFTY PHARMA, etc., from nse_categories.csv) over the broad yfinance "Sector" tag as
# the peer basket, when a stock belongs to one -- a real, market-recognized peer set beats a
# broad tag that lumps unrelated sub-industries together (e.g. yfinance's "Healthcare" mixing
# pharma manufacturers with hospitals/diagnostics chains). Falls back to the broad Sector tag
# for stocks not in any sectoral index (most sectoral indices only cover large/established
# names). These four are excluded from "sectoral" since they're market-CAP-tier groupings
# (mix every industry within a size band), not sector groupings -- confirmed live: without
# excluding MIDCAP/SMALLCAP 50, pharma names like LUPIN/AUROPHARMA/ALKEM (also Nifty Midcap 50
# constituents) got grouped with random midcap companies from unrelated industries instead of
# NIFTY PHARMA, the exact "diluted peer group" problem this feature exists to fix. Anything
# else in NSE_Categories (a true sectoral index) counts as sectoral.
BROAD_INDEX_TAGS = {"NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY MIDCAP 50", "NIFTY SMALLCAP 50"}

# Sectoral-index-direct RS (added 2026-08-20): for a sectoral index with a real yfinance
# ticker, RS_vs_Sector compares the stock against the INDEX'S OWN price series directly --
# same treatment as the benchmark (BENCHMARK_TICKER below) -- instead of averaging its member
# stocks' individual RS. More accurate: reflects the index's real market-cap-weighted
# performance rather than an equal-weight approximation of it, and matches how RS_vs_Benchmark
# already works. Only indices with a verified-live-working yfinance ticker are listed here
# (each individually confirmed with real 2-year history before being added -- guessed tickers
# for NIFTY CONSUMER DURABLES and NIFTY OIL AND GAS all 404'd/returned empty, so those two
# still fall back to compute.py's leave-one-out peer-average in run_pipeline, same as any
# sectoral index without a ticker mapping here).
SECTORAL_INDEX_TICKERS = {
    "NIFTY AUTO": "^CNXAUTO",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY ENERGY": "^CNXENERGY",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY IT": "^CNXIT",
    "NIFTY METAL": "^CNXMETAL",
    "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY REALTY": "^CNXREALTY",
    "NIFTY MEDIA": "^CNXMEDIA",
    "NIFTY PSU BANK": "^CNXPSUBANK",
}

# Sector Pulse table (added 2026-08-20): a dashboard-level, index-only summary (one row per
# sectoral index, not per stock) -- ATH Price Flag and RS computed for each index the exact
# same way as for a stock, just fed the index's own price series. NIFTY_50_INDEX_TICKER is
# the comparison baseline for this table's "RS vs Nifty50" column specifically (a different
# reference point than RS_vs_Benchmark's Nifty 500 -- verified live: ^NSEI, real ticker).
NIFTY_50_INDEX_TICKER = "^NSEI"

# ---------------------------------------------------------------------------
# Exit price (plan §1). SUPERSEDES the original LOCKED decision #4 ("reuse MA200, do not
# build a 212-day SMA") — Turtle's actual methodology uses a 212-day SMA; explicitly
# requested to switch to it. The weekly-cron CSV only ever has MA200 (no MA212 column), so
# it's kept as the fallback for the rare case of <212 days of live daily history.
# ---------------------------------------------------------------------------
EXIT_MA_PERIOD = 212

# ---------------------------------------------------------------------------
# Benchmark — LOCKED decision #2: BSE 500 proxied by Nifty 500 (^CRSLDX not on yfinance
# as BSE 500 itself; ^CRSLDX is the closest large+mid+small-cap equivalent).
# ---------------------------------------------------------------------------
BENCHMARK_TICKER = "^CRSLDX"
BENCHMARK_LABEL = "vs BSE 500 (Nifty 500 proxy)"
BENCHMARK_FALLBACK_TICKERS = ["NIFTYBEES.NS"]

# ---------------------------------------------------------------------------
# Data fetch periods (yfinance, via modules.breakout.data_feed — reused, not rewritten)
# ---------------------------------------------------------------------------
MONTHLY_HISTORY_PERIOD = "max"   # full history for the ATH-price max-close calc
DAILY_HISTORY_PERIOD = "2y"      # >= RS_WINDOW_WEEKS of weekly buckets for relative strength
