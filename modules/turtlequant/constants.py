"""
Thresholds for the Turtle Quant screener, taken directly from the "TQ : W52" TradingView
indicator's Inputs panel (screenshots shared 2026-09-02) plus the "Turtle Quant" firm's own
description of their entry/exit rules. Named here, never inlined, matching this repo's existing
convention (see modules/turtle/constants.py).

Two things aren't literally specified anywhere and are documented assumptions, confirmed with
the user or flagged for review after the first real run:
  * RS formula: no Pine Script source is available. Per the user's own direction, RS reuses the
    existing, already-tested modules.turtle.compute.relative_strength() for both legs (stock and
    NSE:NIFTY), combined into a single ratio value -- see compute.py::relative_strength_vs_index.
  * "ADX: 20" is read as a minimum-ADX-reading THRESHOLD for entry, not a smoothing period --
    DMI_LENGTH (13) already supplies the period fed into the ADX/DI calculation, so a second,
    different "20" alongside it only makes sense as a threshold level (the standard ADX/DMI
    indicator pattern: one length, one minimum-strength gate).
"""

COMPARATIVE_TICKER = "^NSEI"          # NSE:NIFTY -- the indicator's own default Comparative Symbol
COMPARATIVE_LABEL = "vs NSE:NIFTY"

RS_LONG_TERM_WEEKS = 52
RS_SHORT_TERM_WEEKS = 13
RS_LONG_TERM_EXIT_THRESHOLD = -0.25   # ratio-based RS (see compute.py) at/below this -> SELL

SUPERTREND_ATR_LENGTH = 10
SUPERTREND_ATR_FACTOR = 3.0

RSI_LENGTH = 21
RSI_ENTRY = 55.0                      # RSI >= this required for BUY
RSI_EXIT = 45.0                       # RSI <= this alone triggers SELL

DMI_LENGTH = 13                       # smoothing period fed into the ADX/DI calculation
ADX_MIN_THRESHOLD = 20.0              # the indicator's plain "ADX: 20" input -- minimum ADX
                                       # reading required for BUY (see module docstring)

MA_LENGTH = 13                        # shared length for the price-trend MA and the
                                       # volume-build-up MA ("MA Length - Price & Volume" input)
VOLUME_BUILDING_LOOKBACK_WEEKS = 3     # "is the volume MA rising" compares against this many
                                       # weeks back, not just 1 -- a single noisy week (one light
                                       # week inside an otherwise-rising 13-week volume average)
                                       # was blocking BUY for several otherwise-fully-qualifying
                                       # stocks in live testing (2026-09-05); comparing across a
                                       # few weeks smooths that out while still requiring genuine,
                                       # sustained build-up rather than a one-week blip either way

WEEKLY_HISTORY_PERIOD = "5y"          # matches modules/breakout/constants.py's own default;
                                       # >= 52-week RS lookback + ample Wilder-smoothing warm-up
MIN_WEEKLY_ROWS = 60                  # reject symbols with too little weekly history (mirrors
                                       # MIN_MONTHLY_ROWS_FOR_ATH's guard in modules/turtle/constants.py)
