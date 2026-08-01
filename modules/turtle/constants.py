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
# Outperformance / relative strength (plan §1, §2)
# ---------------------------------------------------------------------------
RS_WINDOW_DAYS = 365  # close-to-close return window for stock / sector / benchmark

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
DAILY_HISTORY_PERIOD = "2y"      # >= RS_WINDOW_DAYS of daily closes for relative strength
