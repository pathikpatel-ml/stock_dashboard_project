"""
Multi-Year Breakout Swing Trading Strategy -- removed from the dashboard 2026-08-19.

Only ``data_feed.py`` (cached yfinance OHLCV wrappers) and ``constants.py`` (its period
defaults) survive here -- the Turtle Strategy imports ``data_feed`` directly
(``modules/turtle/screener.py``) for its own monthly/daily price fetching, so this package
can't be deleted outright without breaking Turtle.
"""
