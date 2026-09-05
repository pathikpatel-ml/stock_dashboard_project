"""
Turtle Quant Strategy: weekly relative-strength + trend-following screener.

Distinct from ``modules/turtle`` (Turtle Wealth's ATH/ATH-Profit/outperformance methodology) --
this package implements a different, unrelated firm's ("Turtle Quant") weekly-timeframe system:
dual-window relative strength vs NSE:NIFTY, SuperTrend, ADX/DMI, RSI, and a price/volume
moving-average build-up check, combined into a BUY / HOLD / SELL / NONE signal per stock.
"""
