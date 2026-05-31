"""
Golden-case validation against the documented historical examples (doc §14).

These tests hit the live yfinance API, so they are skipped automatically when the network
is unavailable (e.g. offline CI). They confirm the engine:
  * detects a >= 5-year resistance and a profitable multi-year breakout for known multibaggers, and
  * does NOT raise a BREAKOUT buy on a downtrend-recovery / fallen stock.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import backtest as bt
from modules.breakout import data_feed
from modules.breakout import screener as sc


def _net_ok():
    try:
        m = data_feed.get_monthly("RELIANCE", use_cache=False)
        return m is not None and len(m) > 12
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _net_ok(), reason="network/yfinance unavailable")


# Clean documented multibaggers (doc §14) with an unambiguous >=2-touch multi-year base that
# the faithful engine detects from full monthly history.
GOLDEN_WINNERS = ["SANGHVIMOV", "TITAGARH"]

# Broader documented set; not every name yields a clean >=2-touch near-ATH base within available
# data (the source doc is itself inconsistent on heavily-fallen names like BEML), so we assert
# breadth, not every single one.
GOLDEN_UNIVERSE = ["SANGHVIMOV", "TITAGARH", "BEML", "PCBL"]


@pytest.mark.parametrize("symbol", GOLDEN_WINNERS)
def test_golden_winner_breakout_is_profitable(symbol):
    monthly = data_feed.get_monthly(symbol)
    weekly = data_feed.get_weekly(symbol)
    if monthly is None or len(monthly) < 72:
        pytest.skip(f"insufficient history for {symbol}")
    res = bt.backtest_symbol(symbol, monthly, weekly if weekly is not None else pd.DataFrame())
    assert res.found, f"{symbol}: no multi-year breakout detected ({res.reason})"
    assert res.resistance_age_years >= 5, f"{symbol}: resistance age {res.resistance_age_years}y < 5y"
    assert res.outcome in ("WIN", "OPEN"), f"{symbol}: unexpected outcome {res.outcome}"
    assert res.return_pct > 0, f"{symbol}: non-positive return {res.return_pct}%"


def test_golden_universe_breadth():
    """At least half of the documented winners should yield a profitable multi-year breakout."""
    wins = 0
    for symbol in GOLDEN_UNIVERSE:
        monthly = data_feed.get_monthly(symbol)
        weekly = data_feed.get_weekly(symbol)
        if monthly is None or len(monthly) < 72:
            continue
        res = bt.backtest_symbol(symbol, monthly, weekly if weekly is not None else pd.DataFrame())
        if res.found and res.return_pct and res.return_pct > 0 and res.resistance_age_years >= 5:
            wins += 1
    assert wins >= 2, f"only {wins}/{len(GOLDEN_UNIVERSE)} documented winners validated"


def test_downtrend_recovery_not_a_breakout_buy():
    # Vodafone Idea: fell ~90% from peak -> ATH far above current ceiling -> must NOT be a BREAKOUT.
    monthly = data_feed.get_monthly("IDEA")
    daily = data_feed.get_daily("IDEA")
    if monthly is None or len(monthly) < 72:
        pytest.skip("insufficient history for IDEA")
    res = sc.screen_symbol("IDEA", "Vodafone Idea", monthly, daily, delivery_pcts=[70, 72, 75])
    assert res["status"] != "BREAKOUT", f"IDEA wrongly flagged as breakout: {res.get('reason')}"
