"""
OHLCV fetch-period defaults for ``modules/breakout/data_feed.py``.

The Multi-Year Breakout strategy itself (screener, backtest, layout, all its other
thresholds) was removed 2026-08-19. This file only survives because ``data_feed.py`` is
reused by the Turtle Strategy (``modules/turtle/screener.py`` imports it directly for
cached yfinance OHLCV) and imports its period defaults from here at module load time.
"""

MONTHLY_HISTORY_PERIOD = "max"   # full monthly history
WEEKLY_HISTORY_PERIOD = "5y"     # 5+ years weekly
DAILY_HISTORY_PERIOD = "1y"      # 1 year daily
