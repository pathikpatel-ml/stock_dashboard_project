"""
Unit tests for modules/turtlequant/analysis_store.py -- the REST store backing the Turtle
Quant tab's admin-only "Analyze" per-stock LLM research feature.

No live network: _get/_patch/_upsert (imported directly from modules.auth.user_store into this
module's namespace) are monkeypatched directly, rather than faking the underlying requests
layer -- simpler, since analysis_store.py itself has no filtering/query-building logic of its
own to exercise beyond what it passes straight through.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtlequant import analysis_store as store


def _iso(dt):
    return dt.isoformat()


class _Recorder:
    def __init__(self):
        self.get_calls = []
        self.patch_calls = []
        self.upsert_calls = []
        self.get_return = []

    def fake_get(self, table, params):
        self.get_calls.append((table, params))
        return self.get_return

    def fake_patch(self, table, params, data):
        self.patch_calls.append((table, params, data))
        return [data]

    def fake_upsert(self, table, data, on_conflict):
        self.upsert_calls.append((table, data, on_conflict))
        return [data]


def test_get_analysis_returns_first_row(monkeypatch):
    rec = _Recorder()
    rec.get_return = [{"symbol": "RELIANCE", "status": "done"}]
    monkeypatch.setattr(store, "_get", rec.fake_get)

    result = store.get_analysis("reliance")

    assert result == {"symbol": "RELIANCE", "status": "done"}
    table, params = rec.get_calls[0]
    assert table == "turtlequant_stock_analysis"
    assert params["symbol"] == "eq.RELIANCE"  # uppercased


def test_get_analysis_returns_none_when_missing(monkeypatch):
    rec = _Recorder()
    rec.get_return = []
    monkeypatch.setattr(store, "_get", rec.fake_get)
    assert store.get_analysis("NOSYMBOL") is None


def test_start_analysis_upserts_running_and_clears_old_fields(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(store, "_upsert", rec.fake_upsert)

    row = store.start_analysis("tcs", "Tata Consultancy Services", "admin@example.com")

    table, data, on_conflict = rec.upsert_calls[0]
    assert table == "turtlequant_stock_analysis"
    assert on_conflict == "symbol"
    assert data["symbol"] == "TCS"
    assert data["status"] == "running"
    assert data["management_report"] is None
    assert data["business_report"] is None
    assert data["price_report"] is None
    assert data["error_message"] is None
    assert data["requested_by"] == "admin@example.com"
    assert row["status"] == "running"


def test_save_stage_patches_report_and_matching_citations_field(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(store, "_patch", rec.fake_patch)

    store.save_stage("infy", "management_report", "some report text", ["https://a.com", "https://b.com"])

    table, params, data = rec.patch_calls[0]
    assert params["symbol"] == "eq.INFY"
    assert data["management_report"] == "some report text"
    assert json.loads(data["management_citations"]) == ["https://a.com", "https://b.com"]
    assert "updated_at" in data


def test_save_stage_business_field_maps_to_business_citations(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(store, "_patch", rec.fake_patch)
    store.save_stage("INFY", "business_report", "text", [])
    _, _, data = rec.patch_calls[0]
    assert "business_citations" in data
    assert json.loads(data["business_citations"]) == []


def test_mark_done_sets_status_and_completed_at(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(store, "_patch", rec.fake_patch)
    store.mark_done("HDFCBANK")
    _, params, data = rec.patch_calls[0]
    assert params["symbol"] == "eq.HDFCBANK"
    assert data["status"] == "done"
    assert data["completed_at"] is not None


def test_mark_error_sets_status_and_truncates_long_messages(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(store, "_patch", rec.fake_patch)
    store.mark_error("HDFCBANK", "x" * 5000)
    _, _, data = rec.patch_calls[0]
    assert data["status"] == "error"
    assert len(data["error_message"]) == 2000


def test_is_stale_false_when_not_running():
    row = {"status": "done", "updated_at": _iso(datetime.now(timezone.utc) - timedelta(hours=1))}
    assert store.is_stale(row) is False


def test_is_stale_false_when_running_and_recent():
    row = {"status": "running", "updated_at": _iso(datetime.now(timezone.utc) - timedelta(seconds=10))}
    assert store.is_stale(row) is False


def test_is_stale_true_when_running_and_old():
    row = {"status": "running", "updated_at": _iso(datetime.now(timezone.utc) - timedelta(seconds=600))}
    assert store.is_stale(row, threshold_s=480) is True


def test_is_stale_true_when_running_with_no_updated_at():
    assert store.is_stale({"status": "running", "updated_at": None}) is True


def test_is_stale_false_for_none_row():
    assert store.is_stale(None) is False
