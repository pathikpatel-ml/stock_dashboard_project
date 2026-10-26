"""
Unit tests for generate_turtle_fundamentals.py's day-of-week slicing (2026-10-13).

A full-universe screener.in scrape was repeatedly unable to finish even inside a 6-hour
GitHub Actions window -- confirmed live that screener.in slows down hard for stretches of
~100 consecutive symbols, worsening across repeated same-day attempts (server-side
throttling, not a one-off fluke). Per the user's own request, the job now fetches only 1/7th
of the universe per day (selected by the current IST weekday), spreading the same weekly
refresh cadence across 7 small runs instead of one big one. These tests cover the pure
slicing logic -- no live network, no real universe data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_turtle_fundamentals as gtf


def _fake_universe(n):
    return [f"SYM{i:04d}" for i in range(n)]


def test_seven_slices_cover_every_symbol_exactly_once():
    universe = _fake_universe(2621)  # a real-sized universe, not a round number
    slices = [gtf.slice_for_day(universe, d) for d in range(7)]
    all_sliced = sorted(sym for s in slices for sym in s)
    assert all_sliced == sorted(universe)  # every symbol appears, nothing duplicated


def test_slices_are_disjoint():
    universe = _fake_universe(2621)
    slices = [set(gtf.slice_for_day(universe, d)) for d in range(7)]
    for i in range(7):
        for j in range(i + 1, 7):
            assert slices[i].isdisjoint(slices[j])


def test_slices_are_roughly_equal_size():
    universe = _fake_universe(2621)
    sizes = [len(gtf.slice_for_day(universe, d)) for d in range(7)]
    assert max(sizes) - min(sizes) <= 1  # at most off-by-one between the biggest/smallest slice
    assert sum(sizes) == 2621


def test_slice_is_deterministic_for_same_universe():
    universe = _fake_universe(500)
    assert gtf.slice_for_day(universe, 3) == gtf.slice_for_day(universe, 3)


def test_slice_hand_computed_small_universe():
    universe = [f"SYM{i}" for i in range(10)]  # indices 0..9
    assert gtf.slice_for_day(universe, 0) == ["SYM0", "SYM7"]  # i % 7 == 0 -> 0, 7
    assert gtf.slice_for_day(universe, 2) == ["SYM2", "SYM9"]  # i % 7 == 2 -> 2, 9
    assert gtf.slice_for_day(universe, 6) == ["SYM6"]          # i % 7 == 6 -> 6 only


def test_empty_universe_returns_empty_slice():
    assert gtf.slice_for_day([], 0) == []


def test_current_ist_weekday_returns_a_valid_weekday_index():
    assert gtf.current_ist_weekday() in range(7)


# --- Universe snapshot (2026-10-26) -- prevents the 7 Sunday slices from disagreeing on who
# owns which symbol if nse_universe gets refreshed by the separate weekly_stock_screening.yml
# job partway through the day (confirmed live: that race silently dropped 426 symbols, 16% of
# the universe, from one week's refresh). See generate_turtle_fundamentals.py's
# _write_universe_snapshot docstring for the full incident.

class _FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_write_universe_snapshot_replaces_table_with_given_symbols(monkeypatch):
    calls = {}

    def fake_replace_table_contents(conn, table, df):
        calls["table"] = table
        calls["symbols"] = df["symbol"].tolist()
        return len(df)

    monkeypatch.setattr(gtf.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(gtf.mdw, "replace_table_contents", fake_replace_table_contents)

    gtf._write_universe_snapshot(["BETA", "ALPHA"])

    assert calls["table"] == gtf.UNIVERSE_SNAPSHOT_TABLE
    assert calls["symbols"] == ["BETA", "ALPHA"]


def test_write_universe_snapshot_never_raises_on_db_failure(monkeypatch):
    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gtf.mdw, "get_connection", boom)
    gtf._write_universe_snapshot(["ALPHA"])  # must not raise


def test_read_universe_snapshot_returns_sorted_unique_symbols(monkeypatch):
    import pandas as pd

    monkeypatch.setattr(gtf.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        gtf.mdw, "fetch_dataframe",
        lambda conn, table: pd.DataFrame({"symbol": ["beta", "alpha", "beta"]}),
    )
    assert gtf._read_universe_snapshot() == ["ALPHA", "BETA"]


def test_read_universe_snapshot_empty_when_table_empty(monkeypatch):
    import pandas as pd

    monkeypatch.setattr(gtf.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(gtf.mdw, "fetch_dataframe", lambda conn, table: pd.DataFrame())
    assert gtf._read_universe_snapshot() == []


def test_read_universe_snapshot_empty_on_db_failure(monkeypatch):
    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gtf.mdw, "get_connection", boom)
    assert gtf._read_universe_snapshot() == []


def test_load_universe_symbols_for_slicing_day_zero_writes_snapshot_from_live_universe(monkeypatch):
    written = {}
    monkeypatch.setattr(gtf, "load_universe_symbols", lambda: ["LIVE1", "LIVE2"])
    monkeypatch.setattr(gtf, "_write_universe_snapshot", lambda symbols: written.setdefault("symbols", symbols))

    result = gtf.load_universe_symbols_for_slicing(0)

    assert result == ["LIVE1", "LIVE2"]
    assert written["symbols"] == ["LIVE1", "LIVE2"]


def test_load_universe_symbols_for_slicing_later_day_uses_existing_snapshot(monkeypatch):
    monkeypatch.setattr(gtf, "_read_universe_snapshot", lambda: ["SNAP1", "SNAP2"])

    def fail_if_called():
        raise AssertionError("should not fall back to the live universe when a snapshot exists")

    monkeypatch.setattr(gtf, "load_universe_symbols", fail_if_called)

    assert gtf.load_universe_symbols_for_slicing(3) == ["SNAP1", "SNAP2"]


def test_load_universe_symbols_for_slicing_falls_back_to_live_when_no_snapshot(monkeypatch):
    monkeypatch.setattr(gtf, "_read_universe_snapshot", lambda: [])
    monkeypatch.setattr(gtf, "load_universe_symbols", lambda: ["LIVE1"])

    assert gtf.load_universe_symbols_for_slicing(5) == ["LIVE1"]
