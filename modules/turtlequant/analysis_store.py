"""
REST store for the Turtle Quant "Analyze" button's per-stock LLM research
(turtlequant_stock_analysis table -- see database/schema.sql).

Reuses modules.auth.user_store's Supabase REST helpers directly (_get/_patch/_upsert) rather
than reinventing HTTP plumbing -- same SUPABASE_URL/SUPABASE_SERVICE_KEY path the live app
already writes through for its own data (auth, simulator config), NOT MARKET_DATA_DB_URL (that
credential is deliberately batch-script-only, see database/market_data_writer.py's docstring).

This is a GLOBAL cache keyed by symbol (one row per symbol, overwritten on re-Analyze) -- a
stock's research doesn't depend on which admin asked for it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from modules.auth.user_store import _get, _patch, _upsert

_TABLE = "turtlequant_stock_analysis"


def get_analysis(symbol: str) -> Optional[dict]:
    rows = _get(_TABLE, {"symbol": f"eq.{symbol.upper()}", "select": "*"})
    return rows[0] if rows else None


def start_analysis(symbol: str, company: str, requested_by: str, model: str) -> dict:
    """Upsert a fresh 'running' row -- clears any previous reports/error so a re-Analyze doesn't
    show stale content while the new run is in progress. ``model`` is recorded on the row itself
    (not just read from the current env var later) so a report keeps an accurate record of what
    actually generated it even after STOCK_ANALYSIS_MODEL is changed -- see
    modules/turtlequant/callbacks.py's _render_analysis_panel for why this matters (the free-tier
    model fabricates facts rather than saying "NOT FOUND"; the UI warns based on this field)."""
    now = datetime.now(timezone.utc).isoformat()
    rows = _upsert(_TABLE, {
        "symbol": symbol.upper(),
        "company": company,
        "status": "running",
        "management_report": None, "management_citations": None,
        "business_report": None, "business_citations": None,
        "price_report": None, "price_citations": None,
        "error_message": None,
        "requested_by": requested_by,
        "requested_at": now,
        "completed_at": None,
        "updated_at": now,
        "model": model,
    }, on_conflict="symbol")
    return rows[0]


def save_stage(symbol: str, report_field: str, text: str, citations: list) -> None:
    """Patch one report field + its citations + updated_at (this IS the heartbeat -- called
    after each of the 3 stages completes, not just at the end, so a row's updated_at reflects
    real progress even before the whole run finishes)."""
    citations_field = f"{report_field.replace('_report', '')}_citations"
    _patch(_TABLE, {"symbol": f"eq.{symbol.upper()}"}, {
        report_field: text,
        citations_field: json.dumps(citations or []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def mark_done(symbol: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    _patch(_TABLE, {"symbol": f"eq.{symbol.upper()}"}, {
        "status": "done", "completed_at": now, "updated_at": now,
    })


def mark_error(symbol: str, message: str) -> None:
    _patch(_TABLE, {"symbol": f"eq.{symbol.upper()}"}, {
        "status": "error",
        "error_message": str(message)[:2000],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def is_stale(row: dict, threshold_s: int = 480) -> bool:
    """True if a 'running' row hasn't been touched in threshold_s seconds -- the background
    thread almost certainly died (e.g. Render recycled the process mid-run) without ever
    reaching mark_done/mark_error. Anything other than 'running' is never stale by definition."""
    if not row or row.get("status") != "running":
        return False
    updated_at = row.get("updated_at")
    if not updated_at:
        return True
    try:
        updated = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - updated > timedelta(seconds=threshold_s)
