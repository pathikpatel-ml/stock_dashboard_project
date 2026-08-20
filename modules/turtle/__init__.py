"""
Turtle Strategy — Turtle Wealth's Quant Process screener (docs/TURTLE_STRATEGY_PLAN.md).

Classifies every NSE stock into ADD / HOLD / EXIT using three signals plus a pre-decided
exit price:
  * ATH Price       — latest close at/near its all-time-high close.
  * ATH Profit      — consolidated TTM Net Profit (screener.in) at/above the max annual Net
                       Profit on record.
  * Outperformance  — 52-week return (weekly high-close basis) beats both the stock's
                       sector basket and the benchmark (Nifty 500 proxy for BSE 500).
  * Above Exit      — Current_Price > live 212-day SMA (falls back to the weekly CSV's
                       MA200 only when fewer than 212 days of live daily history exist).

Module map (mirrors ``modules/breakout/``):
  * ``constants.py``               — every threshold, named.
  * ``compute.py``                 — pure, injected-data functions (ATH/profit/RS/classifier).
                                      Unit-tested directly with synthetic data, no I/O.
  * ``standalone_fundamentals.py`` — screener.in scraper (module name is historical; fetches
                                      the ``/consolidated/`` page): consolidated TTM +
                                      historical-annual Net Profit/Net Sales, with search-API
                                      slug fallback for NSE-ticker/screener.in-slug mismatches.
  * ``screener.py``                — orchestration: pulls OHLCV via
                                      ``modules.breakout.data_feed``, fundamentals via
                                      ``turtle_screener_fundamentals.csv`` (screener.in), and
                                      the pre-computed universe via
                                      ``NSE_EQ_All_Stocks_Analysis.csv``, then calls
                                      ``compute.py`` to produce one output row per symbol.
  * ``layout.py`` / ``callbacks.py`` — the Dash tab (IDs prefixed ``tt-``).

``generate_turtle_fundamentals.py`` (repo root) is the weekly batch entrypoint that scrapes
screener.in into ``turtle_screener_fundamentals.csv``; ``generate_turtle_signals.py`` is the
daily batch entrypoint that reads it plus live OHLCV to produce the dated signals CSV;
``data_manager.py`` loads that CSV for the live dashboard.
"""
