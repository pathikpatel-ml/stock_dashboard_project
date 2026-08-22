"""
Shared Postgres writer for the batch/cron data pipeline (V20, Turtle, NSE universe/categories).

Uses ``MARKET_DATA_DB_URL`` -- a dedicated, least-privilege Postgres role (see
migrations/20260820_market_data_tables.sql) that can only read/write the 10 market-data tables
listed there, NOT users/sessions/kite_settings/gtt_log/groww_*. Deliberately a separate
credential from ``SUPABASE_SERVICE_KEY`` (which the live app uses via REST for auth/GTT data,
and which bypasses RLS entirely) -- a leaked GitHub Secret here can't expose auth data, unlike
the service-role key would.

Direct ``psycopg2`` connection, not the PostgREST REST API the rest of this codebase uses for
Supabase: these are short-lived batch jobs writing 1,000-2,500 rows in one shot, and
``execute_values()`` bulk upsert in a single round trip is a better fit for that than paginating
through PostgREST's per-request row limits. The live Dash app keeps reading via REST (see
``database/market_data_reader.py``) -- this module is write-only, used only by the
``generate_*.py`` batch scripts.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


def get_connection():
    """Connect using ``MARKET_DATA_DB_URL``. Raises KeyError with a clear message if the env
    var isn't set -- a batch script should fail loudly here, not silently skip the DB write.
    """
    url = os.environ.get("MARKET_DATA_DB_URL")
    if not url:
        raise RuntimeError(
            "MARKET_DATA_DB_URL is not set. This batch script needs it to write to Postgres "
            "(see migrations/20260820_market_data_tables.sql for the role/credential this "
            "expects). Set it as a GitHub Actions secret or in your local .env."
        )
    return psycopg2.connect(url, connect_timeout=20)


def upsert_dataframe(
    conn,
    table: str,
    df: pd.DataFrame,
    conflict_columns: Sequence[str],
    update_columns: Optional[Sequence[str]] = None,
    touch_updated_at: bool = True,
) -> int:
    """Bulk upsert every row of ``df`` into ``table`` in one round trip.

    ``df``'s column names must already match the table's column names exactly (snake_case --
    callers rename from the CSV-era CamelCase/Title-Case names before calling this; keeping
    that translation at the call site, not here, keeps this function reusable across every
    table without a hardcoded rename map). ``update_columns`` defaults to every column except
    the conflict columns (a plain "upsert everything" -- the common case for a full-refresh
    snapshot). Returns the number of rows upserted; a None/empty ``df`` is a no-op (returns 0)
    rather than issuing a zero-row query, which ``execute_values`` doesn't accept anyway.

    ``touch_updated_at`` (default True) adds ``updated_at = NOW()`` to the UPDATE clause even
    though ``updated_at`` isn't a column in ``df`` -- every table this writes to has that
    column with a ``DEFAULT NOW()`` that only fires on INSERT. Without this, a row's
    ``updated_at`` would freeze at whenever it was FIRST inserted and never move again on
    subsequent re-runs, silently breaking any staleness check built on top of it later.
    """
    if df is None or df.empty:
        return 0

    df = df.astype(object).where(pd.notnull(df), None)  # NaN/NaT -> real Python None -> SQL NULL
    columns = list(df.columns)
    if update_columns is None:
        update_columns = [c for c in columns if c not in conflict_columns]

    values = [tuple(row) for row in df.itertuples(index=False, name=None)]
    col_list = ", ".join(columns)
    conflict_list = ", ".join(conflict_columns)

    set_clauses = [f"{c} = EXCLUDED.{c}" for c in update_columns]
    if touch_updated_at:
        set_clauses.append("updated_at = NOW()")

    if set_clauses:
        update_clause = ", ".join(set_clauses)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES %s "
            f"ON CONFLICT ({conflict_list}) DO UPDATE SET {update_clause}"
        )
    else:
        sql = f"INSERT INTO {table} ({col_list}) VALUES %s ON CONFLICT ({conflict_list}) DO NOTHING"

    with conn.cursor() as cur:
        execute_values(cur, sql, values, page_size=500)
    conn.commit()
    return len(values)


def fetch_dataframe(conn, table: str, order_by: Optional[str] = None) -> pd.DataFrame:
    """Read a full table back via this same batch-writer connection.

    Used by generate_*.py scripts for cross-workflow inputs -- e.g. today's NSE universe,
    produced by a separate, earlier-running weekly workflow -- now that the CSVs those
    workflows used to hand off via git commits are no longer committed to the repo. ``table``
    and ``order_by`` are always internal literals from the call site, never user input.
    Returns an empty DataFrame (not an exception) if the table has no rows yet, so callers can
    fall back to a bundled/checked-in default the same way they already do for a missing CSV.
    """
    query = f"SELECT * FROM {table}"
    if order_by:
        query += f" ORDER BY {order_by}"
    with conn.cursor() as cur:
        cur.execute(query)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns)


def replace_table_contents(conn, table: str, df: pd.DataFrame) -> int:
    """Delete every row in ``table`` and bulk-insert ``df`` in its place, as one transaction.

    For tables that need REPLACE, not upsert, semantics -- e.g. ``v20_signals_latest``, whose
    daily batch job re-scans full price history and re-detects every currently-qualifying
    sequence from scratch each run. A sequence that no longer qualifies has to actually
    disappear from the table, not just sit there unrefreshed; ``upsert_dataframe`` can only
    add/update rows present in ``df``, never remove rows that dropped out of it. Wrapped in
    one transaction so a mid-write failure can't leave the table empty -- either the whole
    swap commits or the DELETE itself rolls back with it. A None/empty ``df`` still executes
    the DELETE (an empty day's result legitimately means "nothing currently qualifies"), unlike
    ``upsert_dataframe``'s no-op-on-empty behaviour, which would leave stale rows behind here.
    """
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table}")
        if df is not None and not df.empty:
            frame = df.astype(object).where(pd.notnull(df), None)
            columns = list(frame.columns)
            values = [tuple(row) for row in frame.itertuples(index=False, name=None)]
            col_list = ", ".join(columns)
            execute_values(cur, f"INSERT INTO {table} ({col_list}) VALUES %s", values, page_size=500)
    conn.commit()
    return 0 if df is None else len(df)
