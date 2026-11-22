"""
Unit tests for generate_turtlequant_benchmark_drawdown.py::main() -- the wiring that fetches
Nifty 50's reference, computes every stock's drawdown comparison, and writes both
turtlequant_nifty_benchmark and turtlequant_signals_latest. Every I/O boundary (yfinance,
data_feed, Postgres, universe loading) is stubbed -- no live network/DB.
"""
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_turtlequant_benchmark_drawdown as gbd


class _FakeConn:
    def close(self):
        pass


_UNIVERSE = pd.DataFrame([{"Symbol": "AAA"}, {"Symbol": "BBB"}])

_NIFTY_REF = {
    "ath_price": 200.0, "ath_date": date(2026, 1, 5),
    "low_52wk_price": 150.0, "low_52wk_date": date(2026, 10, 8),
    "today_price": 190.0, "today_date": date(2026, 11, 20),
}


def test_main_aborts_without_writing_if_nifty_reference_unavailable(monkeypatch):
    monkeypatch.setattr(gbd.tq_screener, "fetch_nifty50_reference", lambda: None)
    written = []
    monkeypatch.setattr(gbd.mdw, "get_connection", lambda: written.append("connected") or _FakeConn())
    monkeypatch.setattr(sys, "argv", ["generate_turtlequant_benchmark_drawdown.py"])

    try:
        gbd.main()
        assert False, "expected SystemExit"
    except SystemExit:
        pass

    assert written == []  # must never even attempt a DB connection


def test_main_writes_benchmark_reference_and_drawdown_columns(monkeypatch):
    monkeypatch.setattr(gbd.tq_screener, "fetch_nifty50_reference", lambda: _NIFTY_REF)
    monkeypatch.setattr(gbd, "load_universe", lambda: _UNIVERSE)

    drawdown_df = pd.DataFrame([
        {"Symbol": "AAA", "ath_price_flag": True, "stock_ath_return_pct": -10.0,
         "stock_52wklow_return_pct": 5.0, "rs_vs_nifty_ath": -5.0, "rs_vs_nifty_52wklow": 1.0},
        {"Symbol": "BBB", "ath_price_flag": None, "stock_ath_return_pct": None,
         "stock_52wklow_return_pct": None, "rs_vs_nifty_ath": None, "rs_vs_nifty_52wklow": None},
    ])
    monkeypatch.setattr(gbd.tq_screener, "compute_universe_drawdown", lambda *a, **k: drawdown_df)

    captured = {}

    def fake_upsert(conn, table, df, conflict_columns, update_columns=None):
        captured[table] = {"df": df, "conflict_columns": conflict_columns, "update_columns": update_columns}
        return len(df)

    monkeypatch.setattr(gbd.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(gbd.mdw, "upsert_dataframe", fake_upsert)

    monkeypatch.setattr(sys, "argv", ["generate_turtlequant_benchmark_drawdown.py"])
    gbd.main()

    assert captured["turtlequant_nifty_benchmark"]["df"].iloc[0]["ath_price"] == 200.0
    assert captured["turtlequant_nifty_benchmark"]["conflict_columns"] == ["benchmark"]

    signals_call = captured["turtlequant_signals_latest"]
    assert "symbol" in signals_call["df"].columns
    assert "Symbol" not in signals_call["df"].columns  # renamed before the write
    assert signals_call["conflict_columns"] == ["symbol"]
    assert set(signals_call["update_columns"]) == {gbd.tq_screener.PRICE_ATH_FIELD} | set(gbd.bd.DRAWDOWN_FIELDS)


def test_main_skips_signals_write_when_drawdown_df_empty(monkeypatch):
    monkeypatch.setattr(gbd.tq_screener, "fetch_nifty50_reference", lambda: _NIFTY_REF)
    monkeypatch.setattr(gbd, "load_universe", lambda: pd.DataFrame(columns=["Symbol"]))
    monkeypatch.setattr(
        gbd.tq_screener, "compute_universe_drawdown",
        lambda *a, **k: pd.DataFrame(columns=["Symbol", gbd.tq_screener.PRICE_ATH_FIELD] + list(gbd.bd.DRAWDOWN_FIELDS)),
    )

    calls = []
    monkeypatch.setattr(gbd.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        gbd.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns, update_columns=None: calls.append(table) or len(df),
    )

    monkeypatch.setattr(sys, "argv", ["generate_turtlequant_benchmark_drawdown.py"])
    gbd.main()

    assert calls == ["turtlequant_nifty_benchmark"]  # the reference row, but not the empty signals write


def test_main_postgres_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(gbd.tq_screener, "fetch_nifty50_reference", lambda: _NIFTY_REF)
    monkeypatch.setattr(gbd, "load_universe", lambda: _UNIVERSE)
    monkeypatch.setattr(
        gbd.tq_screener, "compute_universe_drawdown",
        lambda *a, **k: pd.DataFrame(columns=["Symbol", gbd.tq_screener.PRICE_ATH_FIELD] + list(gbd.bd.DRAWDOWN_FIELDS)),
    )

    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gbd.mdw, "get_connection", boom)
    monkeypatch.setattr(sys, "argv", ["generate_turtlequant_benchmark_drawdown.py"])
    gbd.main()  # must not raise
