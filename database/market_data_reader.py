"""
Shared Postgres reader for the live Dash app (data_manager.py) -- the read-side counterpart to
database/market_data_writer.py's batch-write helper.

Uses the SAME REST/PostgREST access pattern already established in modules/auth/user_store.py
(SUPABASE_URL + SUPABASE_SERVICE_KEY), not psycopg2/MARKET_DATA_DB_URL -- deliberately a
different path from the writer side. The live app is a single long-lived process making
individual, infrequent reads (once per Dash render at most); that's exactly the shape REST is
good at, and it means the app never needs the batch-write credential at all. The batch scripts
never need SUPABASE_SERVICE_KEY either -- each side of the pipeline holds only the credential
its own access pattern actually needs.
"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd
import requests

_PAGE_SIZE = 1000  # PostgREST's own default max rows per request; paginate past it explicitly


def _base_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL environment variable is not set.")
    return f"{url}/rest/v1"


def _headers() -> dict:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_KEY environment variable is not set.")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def fetch_table(table: str, order_by: Optional[str] = None, timeout: int = 15) -> pd.DataFrame:
    """Fetch every row of ``table`` as a DataFrame with the table's own (snake_case) column
    names -- callers rename to the app's CamelCase/Title-Case column names themselves (keeping
    that mapping at the call site alongside the equivalent rename the writer side does, so
    the two stay obviously paired rather than hidden in a shared implicit convention here).

    Paginates past PostgREST's ~1,000-row default page size using ``Range`` headers, since our
    biggest tables (turtle_signals_latest, v20_signals_latest, nse_universe) are ~2,400 rows.
    Never raises on a connection/HTTP failure -- returns an empty DataFrame instead, so a
    Supabase blip degrades to "no data this render" (matching the old CSV-fallback-chain's
    same never-raise contract) rather than crashing the whole page.
    """
    try:
        params = {"select": "*"}
        if order_by:
            params["order"] = order_by

        rows = []
        offset = 0
        while True:
            headers = dict(_headers())
            headers["Range-Unit"] = "items"
            headers["Range"] = f"{offset}-{offset + _PAGE_SIZE - 1}"
            resp = requests.get(f"{_base_url()}/{table}", headers=headers, params=params, timeout=timeout)
            if resp.status_code not in (200, 206):
                resp.raise_for_status()
            page = resp.json()
            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE

        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()
