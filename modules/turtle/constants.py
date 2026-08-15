"""
Thresholds for the Turtle Strategy screener (docs/TURTLE_STRATEGY_PLAN.md, LOCKED decisions).

Named here, never inlined, so a rule change is a one-line diff and the unit tests can assert
the documented values are followed literally.
"""

# ---------------------------------------------------------------------------
# ATH Price (plan §1) — "at/near all-time-high close"
# ---------------------------------------------------------------------------
ATH_PRICE_THRESHOLD_PCT = 5.0  # within 5% of the historical max close counts as ATH

# ---------------------------------------------------------------------------
# Outperformance / relative strength (plan §1, §2). SUPERSEDES the original daily-close,
# 365-calendar-day lookback -- now weekly-bucketed (each week's HIGHEST daily close, not its
# last trading day's close), latest week vs. exactly 52 weeks earlier. Avoids day-of-week
# noise inherent in picking "whichever daily close happens to land ~365 days back".
# ---------------------------------------------------------------------------
RS_WINDOW_WEEKS = 52  # weekly-high-close return window for stock / sector / benchmark

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
