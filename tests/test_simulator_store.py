"""
Unit tests for modules/simulator/store.py -- the Supabase REST helpers backing the Simulator
tab's 5 tables. No live network: requests.get/post/patch/delete are stubbed via monkeypatching
modules.auth.user_store's `requests` module object (the same one store.py's imported
_get/_post/_patch/_upsert/_delete helpers call through).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-key")

from modules.auth import user_store
from modules.simulator import store


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.content = b"x" if payload is not None else b""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeRequests:
    """Records every call and returns pre-programmed responses per table, mirroring how a real
    PostgREST endpoint would respond to GET (list rows) / POST (insert, returns representation)
    / PATCH (update) / DELETE (no body)."""

    def __init__(self):
        self.calls = []
        self.tables = {}  # table -> list of row dicts, the fake "database"

    def get(self, url, headers=None, params=None, timeout=None):
        table = url.rsplit("/", 1)[-1]
        self.calls.append(("GET", table, params))
        rows = self.tables.get(table, [])
        user_id = params.get("user_id")
        strategy = params.get("strategy")
        symbol = params.get("symbol")
        is_active = params.get("is_active")
        result = rows
        if user_id:
            result = [r for r in result if f"eq.{r['user_id']}" == user_id]
        if strategy:
            result = [r for r in result if f"eq.{r['strategy']}" == strategy]
        if symbol:
            result = [r for r in result if f"eq.{r['symbol']}" == symbol]
        if is_active:
            result = [r for r in result if str(r.get("is_active")).lower() == "true"]
        return _FakeResponse(200, result)

    def post(self, url, headers=None, params=None, json=None, timeout=None):
        table = url.rsplit("/", 1)[-1]
        self.calls.append(("POST", table, json))
        row = dict(json)
        row.setdefault("id", len(self.tables.get(table, [])) + 1)
        if params and "on_conflict" in params:
            conflict_cols = params["on_conflict"].split(",")
            existing = self.tables.setdefault(table, [])
            for i, r in enumerate(existing):
                if all(r.get(c) == row.get(c) for c in conflict_cols):
                    existing[i] = {**r, **row}
                    return _FakeResponse(200, [existing[i]])
            existing.append(row)
            return _FakeResponse(200, [row])
        self.tables.setdefault(table, []).append(row)
        return _FakeResponse(200, [row] if "return=representation" in (headers or {}).get("Prefer", "") else None)

    def patch(self, url, headers=None, params=None, json=None, timeout=None):
        table = url.rsplit("/", 1)[-1]
        self.calls.append(("PATCH", table, params, json))
        rows = self.tables.get(table, [])
        updated = []
        for r in rows:
            match = True
            for key in ("user_id", "strategy"):
                if key in params and f"eq.{r.get(key)}" != params[key]:
                    match = False
            if match:
                r.update(json)
                updated.append(r)
        return _FakeResponse(200, updated)

    def delete(self, url, headers=None, params=None, timeout=None):
        table = url.rsplit("/", 1)[-1]
        self.calls.append(("DELETE", table, params))
        rows = self.tables.get(table, [])

        def matches(r):
            for key, val in params.items():
                if f"eq.{r.get(key)}" != val:
                    return False
            return True

        self.tables[table] = [r for r in rows if not matches(r)]
        return _FakeResponse(200, None)


@pytest.fixture()
def fake_requests(monkeypatch):
    fake = _FakeRequests()
    monkeypatch.setattr(user_store, "requests", fake)
    return fake


def test_save_config_creates_config_and_seeds_portfolio(fake_requests):
    config = store.save_config(1, "v20", starting_balance=100000, max_position_pct=12.0, is_active=True)
    assert config["starting_balance"] == 100000
    assert store.get_portfolio(1, "v20")["cash_balance"] == 100000


def test_save_config_update_does_not_reseed_portfolio(fake_requests):
    store.save_config(1, "v20", starting_balance=100000, max_position_pct=12.0, is_active=True)
    store.update_cash(1, "v20", 42000.0)
    store.save_config(1, "v20", starting_balance=100000, max_position_pct=15.0, is_active=True)
    # updating an EXISTING config must not reset cash back to starting_balance
    assert store.get_portfolio(1, "v20")["cash_balance"] == 42000.0


def test_get_active_configs_filters_by_strategy_and_active(fake_requests):
    store.save_config(1, "v20", 100000, 12.0, is_active=True)
    store.save_config(2, "v20", 50000, 10.0, is_active=False)
    store.save_config(3, "turtle", 100000, 12.0, is_active=True)
    active_v20 = store.get_active_configs("v20")
    assert [c["user_id"] for c in active_v20] == [1]


def test_holdings_roundtrip_add_get_remove(fake_requests):
    store.add_holding(1, "v20", "RELIANCE", quantity=5, entry_price=1300.0, entry_date="2026-08-25")
    holdings = store.get_holdings(1, "v20")
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "RELIANCE"
    store.remove_holding(1, "v20", "RELIANCE")
    assert store.get_holdings(1, "v20") == []


def test_record_trade_and_get_trade_history(fake_requests):
    store.record_trade(1, "v20", "TCS", "BUY", 2300.0, 3, "2026-08-25", rationale="strong buy zone")
    trades = store.get_trade_history(1, "v20")
    assert len(trades) == 1
    assert trades[0]["action"] == "BUY"
    assert trades[0]["symbol"] == "TCS"


def test_log_decision_and_get_decision_log(fake_requests):
    store.log_decision(1, "v20", "INFY", "SKIP", "too far from buy zone", "2026-08-25")
    log = store.get_decision_log(1, "v20")
    assert len(log) == 1
    assert log[0]["decision"] == "SKIP"


def test_reset_simulator_clears_everything_and_restores_cash(fake_requests):
    store.save_config(1, "v20", starting_balance=100000, max_position_pct=12.0, is_active=True)
    store.add_holding(1, "v20", "RELIANCE", 5, 1300.0, "2026-08-25")
    store.update_cash(1, "v20", 43500.0)
    store.record_trade(1, "v20", "RELIANCE", "BUY", 1300.0, 5, "2026-08-25")
    store.log_decision(1, "v20", "TCS", "SKIP", "not ready", "2026-08-25")

    store.reset_simulator(1, "v20")

    assert store.get_holdings(1, "v20") == []
    assert store.get_trade_history(1, "v20") == []
    assert store.get_decision_log(1, "v20") == []
    assert store.get_portfolio(1, "v20")["cash_balance"] == 100000


def test_reset_simulator_no_config_is_a_safe_noop(fake_requests):
    store.reset_simulator(999, "v20")  # no config ever saved for this user -- must not raise
    assert store.get_holdings(999, "v20") == []


def test_strategies_are_only_v20_and_turtle(fake_requests):
    assert store.STRATEGIES == ("v20", "turtle")
