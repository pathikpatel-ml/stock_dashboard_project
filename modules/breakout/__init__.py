"""
Multi-Year Breakout Swing Trading Strategy package.

Implements the strategy described in the requirements document
"Multi-Year Breakout Swing Trading Strategy v1.0" (Kundan Prajapati / The Trading
Scholar): detection of high-probability multi-year horizontal-resistance breakouts in
NSE equities, confirmed by delivery volume ("Smart Money"), managed with a measured-move
target plus a 21-EMA weekly trailing stop.

This package mirrors the existing V20 strategy pattern: pure-function engine modules
(deterministic, unit-tested) + a screener that composes them + a Dash layout/callbacks
pair that renders the six dashboard modules.

Submodules
----------
constants          : every exact threshold transcribed from the requirements doc.
trade_math         : SL, range, T1, R:R, distance, priority score, 21-EMA weekly trailing.
resistance         : multi-year horizontal resistance/support detection (doc §12.2).
candle_validation  : breakout-candle valid/invalid classification + supply absorption (doc §4).
volume_trend       : 5-6 month rising/flat/declining volume classification (doc §3.3).
data_feed          : yfinance OHLCV wrappers (monthly/weekly/daily).
delivery_data      : NSE Bhav Copy delivery-volume download/parse/aggregate.
screener           : full 9-step screening pipeline (doc §12.1) + scanners + watchlist.
backtest           : historical simulation of the full trade plan.
positions          : manual-positions-CSV tracking + live metrics.
layout / callbacks : Dash UI for the six dashboard modules.
"""
