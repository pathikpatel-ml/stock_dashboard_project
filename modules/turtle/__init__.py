"""
Turtle Strategy — Turtle Wealth's Quant Process screener (docs/TURTLE_STRATEGY_PLAN.md).

Classifies every NSE stock into ADD / HOLD / EXIT using three signals plus a pre-decided
exit price:
  * ATH Price       — latest close at/near its all-time-high close.
  * ATH Profit      — current (TTM-derived) EPS at/above its historical maximum EPS.
  * Outperformance  — 365-day return beats both the stock's sector basket and the
                       benchmark (Nifty 500 proxy for BSE 500).
  * Above Exit      — Current_Price > live 212-day SMA (falls back to the weekly CSV's
                       MA200 only when fewer than 212 days of live daily history exist).

Module map (mirrors ``modules/breakout/``):
  * ``constants.py`` — every threshold, named.
  * ``compute.py``   — pure, injected-data functions (ATH/profit/RS/classifier). Unit-tested
                        directly with synthetic data, no I/O.
  * ``screener.py``  — orchestration: pulls OHLCV via ``modules.breakout.data_feed``,
                        fundamentals via ``stock_fundamentals_yearly.csv``, and the
                        pre-computed universe via ``NSE_EQ_All_Stocks_Analysis.csv``, then
                        calls ``compute.py`` to produce one output row per symbol.
  * ``layout.py`` / ``callbacks.py`` — the Dash tab (IDs prefixed ``tt-``).

``generate_turtle_signals.py`` (repo root) is the batch entrypoint the daily GitHub Action
runs; ``data_manager.py`` loads its dated output CSV for the live dashboard.
"""
