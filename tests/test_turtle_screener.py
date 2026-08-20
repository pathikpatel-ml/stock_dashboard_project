"""
End-to-end-style test of the Turtle screening pipeline (modules/turtle/screener.py),
mirroring tests/test_generate_fundamentals_yearly.py's monkeypatch style: no live network,
OHLCV is stubbed via monkeypatching modules.breakout.data_feed so the whole pipeline runs
against small, fully-known synthetic data.

Symbol design (deterministic by construction, not by numeric coincidence):
  - Two sectors of two stocks each: within a sector, the "strong" stock's relative strength
    always exceeds the sector's equal-weight average (average of two numbers is always below
    the larger one), and the "weak" stock's RS always falls below it. Both are set far enough
    from the fixed benchmark RS to leave no ambiguity.
  - STOCKA (Alpha, strong)  -> ADD   (ATH price + ATH profit + outperformance all true)
  - STOCKB (Alpha, weak)    -> EXIT  (nothing true)
  - STOCKC (Beta, strong)   -> HOLD  (ATH profit deliberately false; above-exit + outperformance true)
  - STOCKD (Beta, weak)     -> EXIT  (nothing true)
  - STOCKE                  -> rejected (no monthly data -- simulates an unfetchable symbol)
  - STOCKF (Gamma, alone)   -> HOLD  (single-member sector: the leave-one-out sector RS has
                                       no peers to average, so it's undefined (None) and
                                       outperformance is structurally impossible -- documents
                                       a known edge case, not a bug)

Sector RS uses a leave-one-out mean (each stock is compared to the mean of its sector
*peers*, excluding its own value) -- see the Fix-1 tests below for a case proving this
differs numerically from a naive (self-inclusive) mean.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import data_feed
from modules.turtle import compute as tt_compute
from modules.turtle import screener as sc

BENCHMARK_RS = 10.0  # fixed, well below every "strong" RS and above every "weak" RS below


def _daily(start_close, end_close, n=400):
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq="D")
    step = (end_close - start_close) / (n - 1)
    closes = [start_close + step * i for i in range(n)]
    return pd.DataFrame({"Close": closes}, index=dates)


def _monthly(closes):
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=len(closes), freq="ME")
    return pd.DataFrame({"Close": closes}, index=dates)


MONTHLY = {
    # current price = 100 for every symbol (see UNIVERSE); max-close == 100 -> ATH price True.
    "STOCKA": _monthly([60, 80, 100]),
    "STOCKC": _monthly([60, 80, 100]),
    "STOCKF": _monthly([60, 80, 100]),
    # max-close well above 100 -> current price is off its high -> ATH price False.
    "STOCKB": _monthly([60, 130, 150]),
    "STOCKD": _monthly([60, 130, 150]),
    # STOCKE: no monthly data at all -> must be rejected, not crash the batch.
}

DAILY = {
    "STOCKA": _daily(20, 200),   # strong uptrend -> high positive RS
    "STOCKB": _daily(200, 20),   # strong downtrend -> deeply negative RS
    "STOCKC": _daily(20, 200),
    "STOCKD": _daily(200, 20),
    "STOCKF": _daily(20, 200),
}


def _fake_get_monthly(symbol, period=None, use_cache=True):
    return MONTHLY.get(symbol)


def _fake_get_daily(symbol, period=None, use_cache=True):
    return DAILY.get(symbol)


@pytest.fixture(autouse=True)
def _stub_data_feed(monkeypatch):
    monkeypatch.setattr(data_feed, "get_monthly", _fake_get_monthly)
    monkeypatch.setattr(data_feed, "get_daily", _fake_get_daily)


def _universe_row(symbol, sector, ma200):
    return {
        "Symbol": symbol,
        "Company Name": f"{symbol} Ltd.",
        "Sector": sector,
        "Industry": "Test Industry",
        "Current_Price": 100.0,
        "MA200": ma200,
    }


UNIVERSE_DF = pd.DataFrame([
    _universe_row("STOCKA", "Alpha", ma200=90),
    _universe_row("STOCKB", "Alpha", ma200=110),
    _universe_row("STOCKC", "Beta", ma200=90),
    _universe_row("STOCKD", "Beta", ma200=110),
    _universe_row("STOCKE", "Alpha", ma200=90),
    _universe_row("STOCKF", "Gamma", ma200=90),
])


def _fundamentals_row(symbol, ttm_net_profit, max_annual_net_profit, ttm_net_sales, max_annual_net_sales):
    return {
        "Symbol": symbol,
        "TTM_Net_Profit": ttm_net_profit,
        "Max_Annual_Net_Profit": max_annual_net_profit,
        "TTM_Net_Sales": ttm_net_sales,
        "Max_Annual_Net_Sales": max_annual_net_sales,
    }


FUNDAMENTALS_DF = pd.DataFrame([
    # STOCKA/STOCKF: TTM profit (10) >= max annual profit (8) -> ATH Profit True.
    _fundamentals_row("STOCKA", ttm_net_profit=10, max_annual_net_profit=8, ttm_net_sales=90, max_annual_net_sales=100),
    _fundamentals_row("STOCKF", ttm_net_profit=10, max_annual_net_profit=8, ttm_net_sales=90, max_annual_net_sales=100),
    # STOCKB/STOCKC/STOCKD: TTM profit (1) is far below max annual profit (1000) -> False.
    _fundamentals_row("STOCKB", ttm_net_profit=1, max_annual_net_profit=1000, ttm_net_sales=None, max_annual_net_sales=None),
    _fundamentals_row("STOCKC", ttm_net_profit=1, max_annual_net_profit=1000, ttm_net_sales=400, max_annual_net_sales=500),
    _fundamentals_row("STOCKD", ttm_net_profit=1, max_annual_net_profit=1000, ttm_net_sales=400, max_annual_net_sales=500),
    # STOCKE intentionally omitted (irrelevant -- it's rejected before fundamentals are used).
])


@pytest.fixture()
def pipeline_result():
    return sc.run_pipeline(UNIVERSE_DF, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)


def test_output_schema(pipeline_result):
    signals = pipeline_result["signals"]
    assert list(signals.columns) == sc.SIGNAL_COLUMNS


def test_row_count_excludes_unfetchable_symbol(pipeline_result):
    signals = pipeline_result["signals"]
    # 6 universe rows, STOCKE has no monthly data -> rejected, not in signals.
    assert len(signals) == 5
    assert "STOCKE" not in signals["Symbol"].tolist()


def test_stocke_is_rejected_not_crashed(pipeline_result):
    rejections = pipeline_result["rejections"]
    assert not rejections.empty
    stocke_rejects = rejections[rejections["Symbol"] == "STOCKE"]
    assert len(stocke_rejects) == 1
    assert "no_monthly_data" in stocke_rejects.iloc[0]["reason"]


def test_signal_values_are_valid_enum(pipeline_result):
    signals = pipeline_result["signals"]
    assert set(signals["Signal"].unique()) <= {"ADD", "HOLD", "EXIT"}


def test_strong_alpha_stock_is_add(pipeline_result):
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKA"]
    assert row["ATH_Price_Flag"] is True or row["ATH_Price_Flag"] == True  # noqa: E712
    assert row["ATH_Profit_Flag"] == True  # noqa: E712
    assert row["Outperformance_Flag"] == True  # noqa: E712
    assert row["Signal"] == "ADD"


def test_weak_alpha_stock_is_exit(pipeline_result):
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKB"]
    assert row["Signal"] == "EXIT"


def test_beta_hold_case_ath_profit_false_but_two_others_true(pipeline_result):
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKC"]
    assert row["ATH_Profit_Flag"] == False  # noqa: E712
    assert row["Above_MA212_Flag"] == True  # noqa: E712
    assert row["Outperformance_Flag"] == True  # noqa: E712
    assert row["Signal"] == "HOLD"


def test_weak_beta_stock_is_exit(pipeline_result):
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKD"]
    assert row["Signal"] == "EXIT"


def test_single_member_sector_cannot_outperform_its_own_basket(pipeline_result):
    # STOCKF is the only member of "Gamma" -- its sector-average RS equals its own RS, so
    # stock_rs > sector_rs is never true (equal, not greater). This is a documented edge
    # case of the equal-weight-basket definition, not a bug.
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKF"]
    assert row["Outperformance_Flag"] == False  # noqa: E712
    assert row["Signal"] == "HOLD"  # ATH profit + above-exit true, outperformance structurally false


def test_ath_sales_from_fundamentals_max(pipeline_result):
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKA"]
    assert row["ATH_Sales"] == 100


def test_missing_fundamentals_never_crashes():
    # A symbol entirely absent from the fundamentals file must degrade to ATH_Profit_Flag=False,
    # not raise -- build_fundamentals_lookup.get(...) returns {} for it.
    universe = pd.DataFrame([_universe_row("NODATA", "Alpha", ma200=90)])
    MONTHLY["NODATA"] = _monthly([60, 80, 100])
    DAILY["NODATA"] = _daily(20, 200)
    empty_fundamentals = pd.DataFrame(
        columns=["Symbol", "TTM_Net_Profit", "Max_Annual_Net_Profit", "TTM_Net_Sales", "Max_Annual_Net_Sales"]
    )
    try:
        out = sc.run_pipeline(universe, empty_fundamentals, BENCHMARK_RS, verbose=False)
        row = out["signals"].set_index("Symbol").loc["NODATA"]
        assert row["ATH_Profit_Flag"] == False  # noqa: E712
        assert pd.isna(row["ATH_Sales"])
    finally:
        MONTHLY.pop("NODATA", None)
        DAILY.pop("NODATA", None)


def test_build_fundamentals_lookup_symbol_normalisation():
    df = pd.DataFrame([_fundamentals_row(" reliance ", ttm_net_profit=10, max_annual_net_profit=8,
                                          ttm_net_sales=100, max_annual_net_sales=90)])
    lookup = sc.build_fundamentals_lookup(df)
    assert "RELIANCE" in lookup
    assert lookup["RELIANCE"]["ttm_net_profit"] == 10
    assert lookup["RELIANCE"]["max_annual_net_profit"] == 8


def test_build_fundamentals_lookup_shape():
    df = pd.DataFrame([_fundamentals_row("X", ttm_net_profit=110, max_annual_net_profit=100,
                                          ttm_net_sales=210, max_annual_net_sales=200)])
    lookup = sc.build_fundamentals_lookup(df)
    assert lookup["X"] == {
        "ttm_net_profit": 110, "max_annual_net_profit": 100,
        "ttm_net_sales": 210, "max_annual_net_sales": 200,
    }


# ---------------------------------------------------------------------------
# Fix 1 -- leave-one-out sector RS (round-2 review)
# ---------------------------------------------------------------------------
def test_leave_one_out_sector_rs_differs_from_naive_mean():
    """A 3-stock sector: the displayed RS_vs_Sector for the strong stock must be computed
    against the leave-one-out mean of its two peers, not the naive mean that includes its
    own (much larger) value -- the two means are shown to be numerically different here.
    """
    symbols = ["STOCKX", "STOCKY", "STOCKZ"]
    MONTHLY.update({s: _monthly([60, 80, 100]) for s in symbols})
    DAILY.update({
        "STOCKX": _daily(20, 200),   # strong
        "STOCKY": _daily(50, 90),    # mild
        "STOCKZ": _daily(90, 50),    # weak
    })
    try:
        universe = pd.DataFrame([
            _universe_row(s, "Delta", ma200=90) for s in symbols
        ])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signals = out["signals"].set_index("Symbol")

        rs = {
            s: tt_compute.relative_strength(pd.to_numeric(DAILY[s]["Close"], errors="coerce").dropna())
            for s in symbols
        }

        naive_mean_x = (rs["STOCKX"] + rs["STOCKY"] + rs["STOCKZ"]) / 3
        loo_mean_x = (rs["STOCKY"] + rs["STOCKZ"]) / 2  # leave STOCKX out, per the fix

        naive_rs_vs_sector_x = round(rs["STOCKX"] - naive_mean_x, 2)
        loo_rs_vs_sector_x = round(rs["STOCKX"] - loo_mean_x, 2)

        assert loo_rs_vs_sector_x != naive_rs_vs_sector_x  # proves LOO differs from naive
        assert signals.loc["STOCKX", "RS_vs_Sector"] == pytest.approx(loo_rs_vs_sector_x, abs=0.01)
    finally:
        for s in symbols:
            MONTHLY.pop(s, None)
            DAILY.pop(s, None)


def test_single_member_sector_rs_vs_sector_is_undefined_not_zero(pipeline_result):
    # Before the fix, a single-member sector's naive self-inclusive mean equalled the
    # stock's own RS exactly, showing a misleading RS_vs_Sector of 0.00 ("tied with its
    # sector"). With leave-one-out there are no peers to average, so it must be undefined.
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKF"]
    assert pd.isna(row["RS_vs_Sector"])


# ---------------------------------------------------------------------------
# RS peer group (2026-08-15) -- prefer a stock's NSE sectoral index (NIFTY BANK, NIFTY
# PHARMA, ...) over the broad Sector column as the RS peer-group basket, when it's in one.
# ---------------------------------------------------------------------------
def test_no_categories_df_falls_back_to_broad_sector(pipeline_result):
    # No categories_df passed to the fixture -> every stock falls back to "Sector: <Sector>",
    # i.e. exactly the pre-2026-08-15 behaviour (proven by the untouched RS_vs_Sector values
    # in the other tests above, which all still pass unchanged).
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKA"]
    assert row["RS_Peer_Group"] == "Sector: Alpha"


def test_sectoral_index_basket_overrides_broad_sector_grouping():
    # STOCKX and STOCKY are in different broad Sectors (Alpha vs Beta) but the SAME NIFTY
    # BANK sectoral index -- with categories_df supplied, they must be grouped together (by
    # NIFTY BANK), not split apart by their differing Sector column.
    symbols = ["STOCKX", "STOCKY"]
    MONTHLY.update({s: _monthly([60, 80, 100]) for s in symbols})
    DAILY.update({
        "STOCKX": _daily(20, 200),   # strong
        "STOCKY": _daily(50, 90),    # mild
    })
    try:
        universe = pd.DataFrame([
            _universe_row("STOCKX", "Alpha", ma200=90),
            _universe_row("STOCKY", "Beta", ma200=90),
        ])
        categories = pd.DataFrame([
            {"Symbol": "STOCKX", "NSE_Categories": "NIFTY 50,NIFTY BANK"},
            {"Symbol": "STOCKY", "NSE_Categories": "NIFTY BANK"},
        ])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, categories_df=categories, verbose=False)
        signals = out["signals"].set_index("Symbol")

        assert signals.loc["STOCKX", "RS_Peer_Group"] == "NIFTY BANK"
        assert signals.loc["STOCKY", "RS_Peer_Group"] == "NIFTY BANK"

        rs_x = tt_compute.relative_strength(pd.to_numeric(DAILY["STOCKX"]["Close"], errors="coerce").dropna())
        rs_y = tt_compute.relative_strength(pd.to_numeric(DAILY["STOCKY"]["Close"], errors="coerce").dropna())
        # Leave-one-out with only 2 members: each stock's peer group is just the OTHER stock.
        assert signals.loc["STOCKX", "RS_vs_Sector"] == pytest.approx(round(rs_x - rs_y, 2), abs=0.01)
        assert signals.loc["STOCKY", "RS_vs_Sector"] == pytest.approx(round(rs_y - rs_x, 2), abs=0.01)
    finally:
        for s in symbols:
            MONTHLY.pop(s, None)
            DAILY.pop(s, None)


def test_stock_without_sectoral_index_falls_back_to_broad_sector_even_with_categories_df():
    # STOCKZ has NSE_Categories but only broad-market tags (Nifty 50/100/200), no sectoral
    # index -- must fall back to "Sector: <Sector>", not be left ungrouped/None.
    symbol = "STOCKZ"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    DAILY[symbol] = _daily(20, 200)
    try:
        universe = pd.DataFrame([_universe_row(symbol, "Gamma", ma200=90)])
        categories = pd.DataFrame([{"Symbol": symbol, "NSE_Categories": "NIFTY 50,NIFTY 100,NIFTY 200"}])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, categories_df=categories, verbose=False)
        row = out["signals"].set_index("Symbol").loc[symbol]
        assert row["RS_Peer_Group"] == "Sector: Gamma"
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


def test_missing_sector_stocks_are_not_grouped_together():
    # Two stocks with NO Sector value (NaN, e.g. yfinance couldn't classify them) and no
    # sectoral index tag -- must NOT collapse into a shared "Sector: nan" bucket and get
    # compared against each other (caught live: this exact bug affected 79 real stocks).
    # Each must be left with an undefined RS_Peer_Group/RS_vs_Sector, same as any other
    # stock with zero valid peers.
    symbols = ["STOCKNOSECTOR1", "STOCKNOSECTOR2"]
    MONTHLY.update({s: _monthly([60, 80, 100]) for s in symbols})
    DAILY.update({s: _daily(20, 200) for s in symbols})
    try:
        universe = pd.DataFrame([_universe_row(s, sector=None, ma200=90) for s in symbols])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signals = out["signals"].set_index("Symbol")

        for s in symbols:
            assert signals.loc[s, "RS_Peer_Group"] is None or pd.isna(signals.loc[s, "RS_Peer_Group"])
            assert pd.isna(signals.loc[s, "RS_vs_Sector"])
    finally:
        for s in symbols:
            MONTHLY.pop(s, None)
            DAILY.pop(s, None)


def test_build_categories_lookup_symbol_normalisation():
    df = pd.DataFrame([{"Symbol": " reliance ", "NSE_Categories": "NIFTY 50,NIFTY BANK"}])
    lookup = sc.build_categories_lookup(df)
    assert lookup["RELIANCE"] == "NIFTY 50,NIFTY BANK"


def test_build_categories_lookup_empty_or_missing_column():
    assert sc.build_categories_lookup(None) == {}
    assert sc.build_categories_lookup(pd.DataFrame()) == {}
    assert sc.build_categories_lookup(pd.DataFrame({"Symbol": ["X"]})) == {}


# ---------------------------------------------------------------------------
# Fix 2 -- ATH-price source: live daily close + full-history max guard (round-2 review)
# ---------------------------------------------------------------------------
def test_ath_price_uses_live_daily_close_not_stale_csv_price():
    # Monthly month-end closes cap out at 100 and the weekly-cron CSV price is a stale 80,
    # but the live daily series just rallied to a new high of 110 today -- above both.
    symbol = "STOCKLIVE"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=400, freq="D")
    closes = [90.0] * 399 + [110.0]
    DAILY[symbol] = pd.DataFrame({"Close": closes}, index=dates)
    try:
        row = _universe_row(symbol, "Alpha", ma200=90)
        row["Current_Price"] = 80.0  # stale CSV price, well below the live rally
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        assert signal_row["ATH_Price_Flag"] == True  # noqa: E712
        # Round-3 fix: the displayed Current_Price is now the live daily close, not the
        # stale CSV snapshot -- this is exactly what fixes the ICICIBANK-type incident
        # (displayed price reading ~2.5-month-old data).
        assert signal_row["Current_Price"] == 110.0
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


def test_ath_price_combined_max_catches_older_monthly_high_outside_daily_window():
    # The stock's true ATH (500) happened years ago, outside the 2y daily window, and it
    # trades much lower today. The 2y daily window alone would show a much smaller "high"
    # (~119) and could wrongly flag today's price as near-ATH; the monthly (full-history)
    # max must still be honoured via max(daily_max, monthly_max).
    symbol = "STOCKOLDHIGH"
    MONTHLY[symbol] = _monthly([100, 500, 150, 120, 115])
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=400, freq="D")
    closes = [100.0 + (i % 20) for i in range(400)]
    closes[-1] = 115.0
    DAILY[symbol] = pd.DataFrame({"Close": closes}, index=dates)
    try:
        row = _universe_row(symbol, "Alpha", ma200=90)
        row["Current_Price"] = 115.0
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        # 115 is nowhere near the true ATH of 500 -- must NOT be flagged, proving the
        # monthly (full-history) max wasn't lost to the smaller 2y daily-window max.
        assert signal_row["ATH_Price_Flag"] == False  # noqa: E712
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


def test_ath_price_falls_back_to_monthly_only_when_daily_missing():
    # No daily data at all (e.g. yfinance daily fetch came back empty) -- must fall back to
    # the previous monthly-only behaviour (CSV Current_Price vs monthly max) rather than
    # crash or silently treat the symbol as never at its ATH.
    symbol = "STOCKNODAILY"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    DAILY[symbol] = None
    try:
        row = _universe_row(symbol, "Alpha", ma200=90)
        row["Current_Price"] = 100.0  # at the monthly max
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        assert signal_row["ATH_Price_Flag"] == True  # noqa: E712
        # Round-3: displayed price falls back to the CSV snapshot only when there's no
        # daily series at all to take a live close from.
        assert signal_row["Current_Price"] == 100.0
        assert signal_row["Above_MA212_Flag"] == True  # noqa: E712 (CSV MA200=90, CSV price=100)
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


# ---------------------------------------------------------------------------
# Fix 1 (round-3) -- live 212-DMA from the same daily series as the live price, so the
# ATH-Price and Above-MA212 flags can never contradict each other for a stock at its high.
# (Exit-price period switched from 200 to 212 -- Turtle's actual methodology -- afterward;
# these tests were updated in place rather than left asserting the old 200-day threshold.)
# ---------------------------------------------------------------------------
def test_ath_and_above_ma212_agree_for_a_stock_near_its_live_high():
    # Reproduces the ICICIBANK-type incident at the unit level: a stock trading near its
    # live high must show ATH_Price_Flag=True AND Above_MA212_Flag=True together -- by
    # definition, a stock at/near an all-time high is above its own 212-day average. Before
    # this fix, Above_MA212_Flag compared a live-ish signal against a stale CSV MA200 and
    # could disagree.
    symbol = "STOCKNEARHIGH"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    n = 400
    # Steady climb from 100 to 300 over the full window -- the last close (300) is both the
    # series max (ATH) and far above the rolling-212 mean of a rising series.
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq="D")
    closes = [100.0 + i * (200.0 / (n - 1)) for i in range(n)]
    DAILY[symbol] = pd.DataFrame({"Close": closes}, index=dates)
    try:
        row = _universe_row(symbol, "Alpha", ma200=90)
        row["Current_Price"] = 50.0  # deliberately wrong/stale CSV price -- must be ignored
        row["MA200"] = 500.0  # deliberately wrong/stale CSV MA200 (would force False if used)
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        assert signal_row["ATH_Price_Flag"] == True  # noqa: E712
        assert signal_row["Above_MA212_Flag"] == True  # noqa: E712
        # The stale/wrong CSV MA200 (500, which alone would force False) must not have been
        # used -- the live rolling-212 mean of the climbing series is well below 300.
        assert signal_row["Current_Price"] == pytest.approx(300.0)
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


def test_ma212_falls_back_to_csv_ma200_when_fewer_than_212_daily_rows():
    # Fewer than 212 daily rows -- can't compute a live 212-DMA -- must fall back to the CSV
    # MA200 rather than crash or silently treat every such stock as never above its exit.
    symbol = "STOCKSHORTDAILY"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=150, freq="D")  # < 212
    closes = [90.0 + i * 0.1 for i in range(150)]
    DAILY[symbol] = pd.DataFrame({"Close": closes}, index=dates)
    try:
        row = _universe_row(symbol, "Alpha", ma200=90)
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        # Live close (last of the 150 rows) is 104.9, CSV MA200 is 90 -> above.
        assert signal_row["Above_MA212_Flag"] == True  # noqa: E712
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


def test_ma212_boundary_between_200_and_212_rows_still_falls_back():
    # 205 daily rows: enough for the OLD 200-day threshold but still short of the current
    # 212-day one -- guards against a silent regression back to comparing against 200.
    symbol = "STOCKBOUNDARY"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=205, freq="D")
    closes = [90.0 + i * 0.1 for i in range(205)]
    DAILY[symbol] = pd.DataFrame({"Close": closes}, index=dates)
    try:
        row = _universe_row(symbol, "Alpha", ma200=1_000_000)
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        # If the code still used a 200-row threshold, it would compute a live rolling-212
        # mean anyway (rolling() doesn't require a full window by default -- min_periods
        # defaults to the window size, so this only proves the *guard*, not rolling()
        # itself). The real proof is the fallback firing: with 205 rows (< 212) the CSV's
        # absurd MA200 of 1,000,000 must be used, forcing Above_MA212_Flag False.
        assert signal_row["Above_MA212_Flag"] == False  # noqa: E712
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


def test_ma212_false_no_crash_when_both_live_and_csv_ma200_unavailable():
    # < 212 daily rows (can't compute live MA212) AND the CSV MA200 is itself missing/NaN --
    # must degrade to Above_MA212_Flag=False, never raise.
    symbol = "STOCKNOMADATA"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=150, freq="D")
    closes = [90.0 + i * 0.1 for i in range(150)]
    DAILY[symbol] = pd.DataFrame({"Close": closes}, index=dates)
    try:
        row = _universe_row(symbol, "Alpha", ma200=90)
        row["MA200"] = None
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, FUNDAMENTALS_DF, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        assert signal_row["Above_MA212_Flag"] == False  # noqa: E712
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


# ---------------------------------------------------------------------------
# ATH_Sales_Flag -- same shape as ATH_Profit_Flag: consolidated TTM Net Sales (screener.in) vs.
# max annual Net Sales on record, both from the same table -- see compute.ath_sales_flag.
# ---------------------------------------------------------------------------
def test_ath_sales_flag_true_when_ttm_is_a_new_record():
    symbol = "STOCKSALESUP"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    DAILY[symbol] = _daily(20, 200)
    fundamentals = pd.DataFrame([
        _fundamentals_row(symbol, ttm_net_profit=1, max_annual_net_profit=1000,
                           ttm_net_sales=150, max_annual_net_sales=100),  # TTM is a new record
    ])
    try:
        row = _universe_row(symbol, "Alpha", ma200=90)
        universe = pd.DataFrame([row])
        out = sc.run_pipeline(universe, fundamentals, BENCHMARK_RS, verbose=False)
        signal_row = out["signals"].set_index("Symbol").loc[symbol]

        assert signal_row["ATH_Sales_Flag"] == True  # noqa: E712
        assert signal_row["ATH_Sales"] == 100  # the raw ATH_Sales column shows the historical max, unaffected
        assert signal_row["TTM_Net_Sales"] == 150
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)


def test_ath_sales_flag_false_when_ttm_below_historical_max(pipeline_result):
    # STOCKA's fundamentals (shared fixture): TTM sales=90, historical max=100 -- TTM hasn't
    # set a new all-time high.
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKA"]
    assert row["ATH_Sales_Flag"] == False  # noqa: E712
    assert row["ATH_Sales"] == 100  # the all-time max is still shown


def test_ath_sales_flag_false_when_sales_data_missing(pipeline_result):
    # STOCKB's fundamentals (shared fixture) have no sales data at all -- must degrade to
    # False rather than guessing.
    row = pipeline_result["signals"].set_index("Symbol").loc["STOCKB"]
    assert row["ATH_Sales_Flag"] == False  # noqa: E712
    assert pd.isna(row["ATH_Sales"])


# ---------------------------------------------------------------------------
# ATH_Profit_Flag must come entirely from the screener.in fundamentals lookup (TTM vs max
# annual), NOT from price at all -- unlike the old EPS-proxy implementation (shares-outstanding
# derived from Market_Cap / price), which silently drifted "current EPS" with every live price
# tick even when profit and real share count hadn't changed (the DEEPINDS incident that led to
# dropping that approach). This regression-guards that ATH_Profit_Flag is fully price-independent.
# ---------------------------------------------------------------------------
def test_ath_profit_flag_unaffected_by_live_price_movement():
    symbol = "STOCKEPSTABLE"
    MONTHLY[symbol] = _monthly([60, 80, 100])
    fundamentals = pd.DataFrame([
        _fundamentals_row(symbol, ttm_net_profit=10, max_annual_net_profit=8,
                           ttm_net_sales=90, max_annual_net_sales=100),
    ])
    row = _universe_row(symbol, "Alpha", ma200=90)

    try:
        results = {}
        for label, live_close_range in [("day_high_price", (400.0, 500.0)), ("day_low_price", (80.0, 50.0))]:
            DAILY[symbol] = _daily(*live_close_range)
            universe = pd.DataFrame([row])
            out = sc.run_pipeline(universe, fundamentals, BENCHMARK_RS, verbose=False)
            results[label] = out["signals"].set_index("Symbol").loc[symbol]

        # The live/displayed price genuinely differs between the two runs (as it should)...
        assert results["day_high_price"]["Current_Price"] != results["day_low_price"]["Current_Price"]
        assert results["day_high_price"]["Current_Price"] == pytest.approx(500.0)
        assert results["day_low_price"]["Current_Price"] == pytest.approx(50.0)

        # ...but ATH_Profit_Flag must be identical in both, since it's sourced purely from the
        # screener.in fundamentals lookup, never from whichever live price the daily fetch
        # happened to return that day.
        assert results["day_high_price"]["ATH_Profit_Flag"] == True  # noqa: E712
        assert results["day_low_price"]["ATH_Profit_Flag"] == True  # noqa: E712
    finally:
        MONTHLY.pop(symbol, None)
        DAILY.pop(symbol, None)
