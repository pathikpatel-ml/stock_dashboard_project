"""
Supabase REST helpers for the Simulator tab's 5 tables (simulator_config, simulator_portfolio,
simulator_holdings, simulator_trades, simulator_decision_log) -- mirrors
modules/auth/user_store.py's _get/_post/_patch/_upsert/_delete pattern exactly, reusing
SUPABASE_URL/SUPABASE_SERVICE_KEY (the same service-role key user_store.py already uses, NOT
MARKET_DATA_DB_URL -- this is per-user simulator state, not shared market data).

Imported by BOTH the live Dash app (modules/simulator/callbacks.py -- read for display, write
for config/reset) and generate_simulator_decisions.py (the offline batch job -- reads every
active user's config across all users via get_active_configs, writes trades/holdings).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from modules.auth.user_store import _delete, _get, _patch, _post, _upsert

STRATEGIES = ("v20", "turtle")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config(user_id: int, strategy: str) -> Optional[dict]:
    rows = _get("simulator_config", {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}"})
    return rows[0] if rows else None


def get_active_configs(strategy: str) -> list:
    """Every user's config for this strategy with is_active=True -- used by the batch job,
    which needs cross-user access (SUPABASE_SERVICE_KEY bypasses RLS, same as every other
    service-role call in this codebase)."""
    return _get("simulator_config", {"strategy": f"eq.{strategy}", "is_active": "eq.true"})


def save_config(user_id: int, strategy: str, starting_balance: float, max_position_pct: float,
                 is_active: bool) -> dict:
    """Create or update this user's config for one strategy. If this is a brand-new config (no
    existing portfolio row yet), also seeds simulator_portfolio.cash_balance = starting_balance
    so a freshly-activated simulator has money to trade with."""
    existing = get_config(user_id, strategy)
    row = _upsert(
        "simulator_config",
        {
            "user_id": user_id, "strategy": strategy,
            "starting_balance": starting_balance,
            "max_position_pct": max_position_pct,
            "is_active": is_active,
        },
        on_conflict="user_id,strategy",
    )[0]
    if existing is None:
        init_portfolio(user_id, strategy, starting_balance)
    return row


def set_active(user_id: int, strategy: str, is_active: bool):
    _patch(
        "simulator_config",
        {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}"},
        {"is_active": is_active},
    )


# ---------------------------------------------------------------------------
# Portfolio (cash balance)
# ---------------------------------------------------------------------------

def get_portfolio(user_id: int, strategy: str) -> Optional[dict]:
    rows = _get("simulator_portfolio", {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}"})
    return rows[0] if rows else None


def init_portfolio(user_id: int, strategy: str, cash_balance: float):
    _upsert(
        "simulator_portfolio",
        {"user_id": user_id, "strategy": strategy, "cash_balance": cash_balance},
        on_conflict="user_id,strategy",
    )


def update_cash(user_id: int, strategy: str, new_cash_balance: float):
    _patch(
        "simulator_portfolio",
        {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}"},
        {"cash_balance": new_cash_balance, "updated_at": datetime.now(timezone.utc).isoformat()},
    )


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------

def get_holdings(user_id: int, strategy: str) -> list:
    return _get(
        "simulator_holdings",
        {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}", "order": "symbol"},
    )


def add_holding(user_id: int, strategy: str, symbol: str, quantity: float, entry_price: float,
                 entry_date: str, entry_rationale: str = ""):
    _upsert(
        "simulator_holdings",
        {
            "user_id": user_id, "strategy": strategy, "symbol": symbol,
            "quantity": quantity, "entry_price": entry_price,
            "entry_date": entry_date, "entry_rationale": entry_rationale,
        },
        on_conflict="user_id,strategy,symbol",
    )


def remove_holding(user_id: int, strategy: str, symbol: str):
    _delete("simulator_holdings", {
        "user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}", "symbol": f"eq.{symbol}",
    })


# ---------------------------------------------------------------------------
# Trades (append-only history)
# ---------------------------------------------------------------------------

def record_trade(user_id: int, strategy: str, symbol: str, action: str, price: float,
                  quantity: float, trade_date: str, realized_pnl: Optional[float] = None,
                  rationale: str = ""):
    _post("simulator_trades", {
        "user_id": user_id, "strategy": strategy, "symbol": symbol, "action": action,
        "price": price, "quantity": quantity, "trade_date": trade_date,
        "realized_pnl": realized_pnl, "rationale": rationale,
    }, prefer="return=minimal")


def get_trade_history(user_id: int, strategy: str) -> list:
    return _get(
        "simulator_trades",
        {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}", "order": "created_at.desc"},
    )


# ---------------------------------------------------------------------------
# Decision log (every candidate reviewed, including SKIP/HOLD)
# ---------------------------------------------------------------------------

def log_decision(user_id: int, strategy: str, symbol: str, decision: str, rationale: str,
                  run_date: str):
    _post("simulator_decision_log", {
        "user_id": user_id, "strategy": strategy, "symbol": symbol,
        "decision": decision, "rationale": rationale, "run_date": run_date,
    }, prefer="return=minimal")


def get_decision_log(user_id: int, strategy: str, limit: int = 50) -> list:
    return _get(
        "simulator_decision_log",
        {
            "user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}",
            "order": "created_at.desc", "limit": str(limit),
        },
    )


# ---------------------------------------------------------------------------
# Reset -- wipes holdings/trades/decisions and restores cash to starting_balance. Discards
# history deliberately (a "start over" action, not an archive) -- the UI must confirm with the
# user before calling this, since it's irreversible.
# ---------------------------------------------------------------------------

def reset_simulator(user_id: int, strategy: str):
    config = get_config(user_id, strategy)
    if config is None:
        return
    for holding in get_holdings(user_id, strategy):
        remove_holding(user_id, strategy, holding["symbol"])
    _delete("simulator_trades", {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}"})
    _delete("simulator_decision_log", {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}"})
    update_cash(user_id, strategy, config["starting_balance"])
    _patch(
        "simulator_config",
        {"user_id": f"eq.{user_id}", "strategy": f"eq.{strategy}"},
        {"reset_at": datetime.now(timezone.utc).isoformat()},
    )
