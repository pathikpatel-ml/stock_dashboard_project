"""
Unit tests for the Turtle Quant pure functions (modules/turtlequant/compute.py).

Mirrors tests/test_turtle_engine.py's style: plain asserts, pytest.approx for floats,
synthetic in-memory data only, no network, no mocking of pure functions.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtlequant import compute as tq


def _weekly_close(values):
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=len(values), freq="W-MON")
    return pd.Series(values, index=dates)


def _weekly_ohlcv(closes, volumes=None):
    """OHLCV frame with High = Low = Close (a common test simplification -- ATR/true-range
    still reflects real week-over-week volatility via the |Close - prev_close| term)."""
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=len(closes), freq="W-MON")
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    return pd.DataFrame(
        {"High": closes, "Low": closes, "Close": closes, "Volume": volumes}, index=dates
    )


def _linear(start, end, n):
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


# ---------------------------------------------------------------------------
# rsi
# ---------------------------------------------------------------------------
def test_rsi_all_gains_is_100():
    close = pd.Series(_linear(100, 200, 40))
    result = tq.rsi(close, length=21)
    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_0():
    close = pd.Series(_linear(200, 100, 40))
    result = tq.rsi(close, length=21)
    assert result.iloc[-1] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# atr / true_range
# ---------------------------------------------------------------------------
def test_true_range_uses_prev_close_gap():
    high = pd.Series([10, 10, 20])
    low = pd.Series([9, 9, 19])
    close = pd.Series([9.5, 9.5, 19.5])
    tr = tq.true_range(high, low, close)
    # Row 2: High-Low=1, |High-prevClose|=|20-9.5|=10.5, |Low-prevClose|=|19-9.5|=9.5 -> max=10.5
    assert tr.iloc[2] == pytest.approx(10.5)


# ---------------------------------------------------------------------------
# supertrend
# ---------------------------------------------------------------------------
def test_supertrend_bullish_on_steady_uptrend():
    closes = _linear(100, 300, 60)
    df = _weekly_ohlcv(closes)
    direction = tq.supertrend(df["High"], df["Low"], df["Close"])
    assert direction.iloc[-1] == 1


def test_supertrend_bearish_on_steady_downtrend():
    closes = _linear(300, 100, 60)
    df = _weekly_ohlcv(closes)
    direction = tq.supertrend(df["High"], df["Low"], df["Close"])
    assert direction.iloc[-1] == -1


# ---------------------------------------------------------------------------
# rolling_ma / volume_building / price_trend_ok
# ---------------------------------------------------------------------------
def test_rolling_ma_matches_pandas_directly():
    series = pd.Series(_linear(1, 100, 50))
    assert tq.rolling_ma(series, length=13).iloc[-1] == pytest.approx(series.iloc[-13:].mean())


def test_volume_building_true_when_ma_rising():
    volume = pd.Series(_linear(100_000, 500_000, 30))
    assert tq.volume_building(volume, length=13) is True


def test_volume_building_false_when_ma_falling():
    volume = pd.Series(_linear(500_000, 100_000, 30))
    assert tq.volume_building(volume, length=13) is False


def test_volume_building_none_when_too_short():
    volume = pd.Series([100_000] * 5)
    assert tq.volume_building(volume, length=13) is None


def test_volume_building_smooths_a_single_week_dip():
    # MA sequence [5, 6, 7, 6.5] (length=1 -> the MA is just the raw series, for arithmetic
    # simplicity): the immediately-prior week alone (lookback=1) says this looks like it's
    # falling (6.5 < 7) -- but 3 weeks back (lookback=3, the new default) it's still clearly up
    # (6.5 > 5), which is the real, sustained trend a single soft week shouldn't erase.
    volume = pd.Series([5.0, 6.0, 7.0, 6.5])
    assert tq.volume_building(volume, length=1, lookback=1) is False
    assert tq.volume_building(volume, length=1, lookback=3) is True


def test_price_trend_ok_true_above_ma_false_below():
    rising = pd.Series(_linear(100, 200, 30))
    falling = pd.Series(_linear(200, 100, 30))
    assert tq.price_trend_ok(rising, length=13) is True
    assert tq.price_trend_ok(falling, length=13) is False


# ---------------------------------------------------------------------------
# relative_strength_vs_index
# ---------------------------------------------------------------------------
def test_relative_strength_vs_index_known_ratio():
    # 81 weekly points (index 0..80); latest=index80, 52 weeks back=index28 exactly (7-day
    # weekly spacing => 52*7=364 days = exactly 52 weeks).
    stock = _weekly_close(_linear(100, 200, 81))   # value(28)=100+100*28/80=135, return=200/135-1
    index = _weekly_close(_linear(100, 150, 81))   # value(28)=100+50*28/80=117.5, return=150/117.5-1
    result = tq.relative_strength_vs_index(stock, index, window_weeks=52)

    stock_return = (200 / 135.0 - 1) * 100
    index_return = (150 / 117.5 - 1) * 100
    expected = (1 + stock_return / 100) / (1 + index_return / 100) - 1
    assert result == pytest.approx(expected, rel=1e-6)


def test_relative_strength_vs_index_none_when_insufficient_history():
    stock = _weekly_close(_linear(100, 200, 10))  # far fewer than 52 weeks of history
    index = _weekly_close(_linear(100, 150, 10))
    assert tq.relative_strength_vs_index(stock, index, window_weeks=52) is None


def test_relative_strength_vs_index_none_when_either_leg_missing():
    stock = _weekly_close(_linear(100, 200, 81))
    assert tq.relative_strength_vs_index(stock, None, window_weeks=52) is None
    assert tq.relative_strength_vs_index(None, stock, window_weeks=52) is None


# ---------------------------------------------------------------------------
# classify -- truth table
# ---------------------------------------------------------------------------
def test_classify_buy_requires_every_condition():
    assert tq.classify(
        rs_long=0.30, rs_short=0.05, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "BUY"


def test_classify_sell_via_supertrend_bearish_alone():
    # Every other condition looks BUY-worthy -- SuperTrend bearish alone must still win.
    assert tq.classify(
        rs_long=0.30, rs_short=0.05, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=False,
    ) == "SELL"


def test_classify_sell_via_rs_long_exit_threshold_alone():
    assert tq.classify(
        rs_long=-0.25, rs_short=0.05, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "SELL"
    assert tq.classify(
        rs_long=-0.30, rs_short=0.05, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "SELL"


def test_classify_sell_via_rsi_exit_alone():
    assert tq.classify(
        rs_long=0.30, rs_short=0.05, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=45.0, supertrend_bullish=True,
    ) == "SELL"


def test_classify_hold_when_supertrend_bullish_but_buy_not_confirmed():
    # ADX below threshold -- everything else BUY-worthy.
    assert tq.classify(
        rs_long=0.30, rs_short=0.05, adx_value=10.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "HOLD"
    # RS long/short flat-to-negative but above the exit threshold, RSI healthy.
    assert tq.classify(
        rs_long=-0.05, rs_short=-0.02, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "HOLD"


def test_classify_none_inputs_never_buy():
    assert tq.classify(
        rs_long=None, rs_short=0.05, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "HOLD"
    assert tq.classify(
        rs_long=0.30, rs_short=0.05, adx_value=None, volume_ok=True,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "HOLD"
    assert tq.classify(
        rs_long=0.30, rs_short=0.05, adx_value=25.0, volume_ok=None,
        price_trend_ok_=True, rsi_value=60.0, supertrend_bullish=True,
    ) == "HOLD"
    assert tq.classify(
        rs_long=0.30, rs_short=0.05, adx_value=25.0, volume_ok=True,
        price_trend_ok_=True, rsi_value=None, supertrend_bullish=True,
    ) == "HOLD"
