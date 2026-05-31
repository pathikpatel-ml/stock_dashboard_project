"""
Exact thresholds for the Multi-Year Breakout Swing Strategy.

Every constant here is transcribed directly from the requirements document
(section references in comments). The engine imports these by name so the unit tests
can assert the documented values are followed literally — change a rule HERE, never inline.
"""

# ---------------------------------------------------------------------------
# FILTER 1 — Multi-year horizontal resistance (doc §3.1, §12.2)
# ---------------------------------------------------------------------------
MIN_RESISTANCE_AGE_YEARS = 5          # resistance must be >= 5 years old
MIN_RESISTANCE_AGE_MONTHS = 60        # 5 years == 60 monthly candles
RESISTANCE_CLUSTER_TOLERANCE_PCT = 2.0  # monthly highs within 2% form one cluster / count as a touch
MIN_RESISTANCE_TOUCHES = 2            # resistance must have been tested at least 2 times

# ---------------------------------------------------------------------------
# FILTER 2 — All-Time-High breakout only (doc §3.2, §12.1 STEP 3)
# ---------------------------------------------------------------------------
ATH_PROXIMITY_PCT = 5.0     # resistance must be at or within 5% of ATH (checklist #2)
ATH_REJECT_ABOVE_PCT = 10.0  # reject if ATH is > 10% above the breakout resistance (downtrend recovery)

# ---------------------------------------------------------------------------
# FILTER 3 — Rising volume in last 5-6 months (doc §3.3)
# ---------------------------------------------------------------------------
VOLUME_TREND_LOOKBACK_MONTHS = 6   # examine the 5-6 months before breakout
VOLUME_TREND_WINDOW = 5            # "3 of the last 5 months"
VOLUME_TREND_MIN_ABOVE_AVG = 3     # >= 3 of last 5 months above average => rising
VOLUME_TREND_SLOPE_EPS = 0.02      # relative slope band for FLAT classification

# ---------------------------------------------------------------------------
# FILTER 4/5 — Delivery volume %, "Smart Money" (doc §3.4, §15 #5/#6)
# ---------------------------------------------------------------------------
DELIVERY_MIN_PCT = 50.0           # minimum valid delivery %
DELIVERY_STRONG_PCT = 60.0        # 60-80%+ == strong accumulation
DELIVERY_HARD_REJECT_PCT = 30.0   # < 30% => hard reject (speculative/intraday)
DELIVERY_WEAK_REJECT_PCT = 40.0   # < 40% consistently => reject
DELIVERY_LOOKBACK_MONTHS = 3      # check breakout month + prior 2-3 months

# ---------------------------------------------------------------------------
# Breakout candle validation (doc §4)
# ---------------------------------------------------------------------------
WEAK_CLOSE_PCT = 1.5        # close < 1.5% above resistance => weak close (reject)
STRONG_CLOSE_PCT = 2.0      # close >= 2% above resistance => strong (valid)
UPPER_WICK_REJECT_PCT = 30.0  # upper wick > 30% of range => reject (checklist #8 pass threshold)
UPPER_WICK_IDEAL_PCT = 20.0   # upper wick < 20% => ideal Marubozu
CLOSE_UPPER_RANGE_FRAC_PCT = 40.0  # close in "upper 60% of range" => close position >= 40% from low
VOLUME_SPIKE_MIN = 1.5      # breakout volume >= 1.5x prior 3-month avg (valid)
VOLUME_SPIKE_STRONG = 2.0   # >= 2x == strong
VOLUME_SPIKE_LOOKBACK = 3   # prior 3 months average

# Supply-absorption bonus (doc §4.3)
SUPPLY_ABSORPTION_PROXIMITY_PCT = 3.0   # close within 3% of resistance
SUPPLY_ABSORPTION_RANGE_PCT = 50.0      # candle range < 50% of average range (tight)
SUPPLY_ABSORPTION_MIN_MONTHS = 1
SUPPLY_ABSORPTION_MAX_MONTHS = 3

# ---------------------------------------------------------------------------
# Stop loss (doc §6.1)
# ---------------------------------------------------------------------------
SL_BUFFER = 0.01            # 1% buffer below breakout candle low
SL_MULTIPLIER = 1.0 - SL_BUFFER  # SL = breakout candle low * 0.99

# ---------------------------------------------------------------------------
# Targets & Risk:Reward (doc §5.3, §7.1)
# ---------------------------------------------------------------------------
MIN_RR_RATIO = 2.0          # entry only allowed if R:R >= 1:2
PREFERRED_RR_RATIO = 3.0    # preferred minimum 1:3
T1_EXIT_FRACTION = 0.5      # exit 50% at Target 1

# ---------------------------------------------------------------------------
# 21-EMA weekly trailing stop (doc §7.2, §12.3)
# ---------------------------------------------------------------------------
TRAILING_EMA_PERIOD = 21
TRAILING_CONSECUTIVE_CLOSES = 2  # exit on 2 consecutive weekly closes below 21 EMA

# ---------------------------------------------------------------------------
# Scanners (doc §8)
# ---------------------------------------------------------------------------
WEEK52_HIGH_PROXIMITY_PCT = 1.0   # trading at or within 1% of 52-week high
FIVE_YEAR_LOOKBACK_MONTHS = 60    # 5-year high == highest high of last 60 months
FIVE_YEAR_TRADING_DAYS = 1250     # equivalently ~1250 trading days
NEAR_BREAKOUT_PROXIMITY_PCT = 3.0  # watchlist: within 3% of resistance

# ---------------------------------------------------------------------------
# Universe build (doc §12.1 STEP 1)
# ---------------------------------------------------------------------------
MIN_PRICE = 10.0            # exclude penny stocks (CMP < 10)
MIN_AVG_DAILY_VOLUME = 50000  # exclude illiquid (avg daily volume < 50,000)
MIN_LISTING_YEARS = 5       # exclude recently listed (< 5 years)

# ---------------------------------------------------------------------------
# Priority score (doc §10.3) — literal formula, see note in trade_math.priority_score
# ---------------------------------------------------------------------------
PRIORITY_W_AGE = 0.3
PRIORITY_W_DELIVERY = 0.4
PRIORITY_W_DISTANCE = 0.3

# ---------------------------------------------------------------------------
# Alerts (doc §6.2, §9.1 Module 3, §9.1 Module 6)
# ---------------------------------------------------------------------------
SL_WARNING_PROXIMITY_PCT = 2.0   # §6.2: alert when price within 2% of SL
SL_YELLOW_PROXIMITY_PCT = 3.0    # §9.1 Module 3: yellow status within 3% of SL

# ---------------------------------------------------------------------------
# Data fetch periods (yfinance)
# ---------------------------------------------------------------------------
# Monthly uses full listed history ("max"): the doc defines ATH as the highest price in the
# stock's *entire* listed history (glossary) and "10+ years" is a stated minimum (§10.1). Full
# history is required to see 13/17-year resistances (e.g. BEML) older than a fixed 10y window.
MONTHLY_HISTORY_PERIOD = "max"   # full monthly history (>= 10 years; doc §10.1, §3.2 ATH)
WEEKLY_HISTORY_PERIOD = "5y"     # 5+ years weekly (21-EMA trailing)
DAILY_HISTORY_PERIOD = "1y"      # 1 year daily (SL monitoring, daily-close basis)
