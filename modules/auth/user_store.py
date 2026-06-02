import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


class User(UserMixin):
    def __init__(self, id: int, email: str, is_active: bool):
        self.id = id
        self.email = email
        self._is_active = is_active

    @property
    def is_active(self):
        return self._is_active


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _get_conn():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    # Supabase uses postgres:// but psycopg2 needs postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Supabase requires SSL — append if not already specified
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor,
                            connect_timeout=10)


@contextmanager
def _cursor():
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "..", "..", "database", "schema.sql")
    schema_path = os.path.normpath(schema_path)
    with open(schema_path, "r") as f:
        sql = f.read()
    with _cursor() as cur:
        cur.execute(sql)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: int):
    with _cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    if not row:
        return None
    return User(row["id"], row["email"], row["is_active"])


def get_user_by_email(email: str):
    with _cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
        row = cur.fetchone()
    if not row:
        return None
    return User(row["id"], row["email"], row["is_active"])


def verify_password(email: str, password: str):
    with _cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
        row = cur.fetchone()
    if not row:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    # Update last_login_at
    with _cursor() as cur:
        cur.execute(
            "UPDATE users SET last_login_at = %s WHERE id = %s",
            (datetime.now(timezone.utc), row["id"]),
        )
    return User(row["id"], row["email"], row["is_active"])


def create_user(email: str, password: str) -> User:
    hashed = generate_password_hash(password)
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
            (email.lower().strip(), hashed),
        )
        user_id = cur.fetchone()["id"]
    return User(user_id, email.lower().strip(), True)


# ---------------------------------------------------------------------------
# Kite settings
# ---------------------------------------------------------------------------

def get_kite_settings(user_id: int) -> dict:
    with _cursor() as cur:
        cur.execute("SELECT * FROM kite_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    if not row:
        return {
            "user_id": user_id,
            "api_key_enc": None,
            "api_secret_enc": None,
            "access_token_enc": None,
            "access_token_set_at": None,
            "proximity_threshold_pct": 2.0,
            "max_allocation_pct": 3.0,
            "gtt_enabled": False,
        }
    return dict(row)


def upsert_kite_settings(user_id: int, **kwargs):
    allowed = {
        "api_key_enc", "api_secret_enc", "access_token_enc",
        "access_token_set_at", "proximity_threshold_pct",
        "max_allocation_pct", "gtt_enabled",
    }
    kwargs = {k: v for k, v in kwargs.items() if k in allowed}
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.now(timezone.utc)
    cols = list(kwargs.keys())
    vals = [kwargs[c] for c in cols]

    set_clause = ", ".join(f"{c} = %s" for c in cols)
    insert_cols = ", ".join(["user_id"] + cols)
    insert_placeholders = ", ".join(["%s"] * (1 + len(cols)))
    conflict_update = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)

    sql = f"""
        INSERT INTO kite_settings (user_id, {', '.join(cols)})
        VALUES (%s, {', '.join(['%s'] * len(cols))})
        ON CONFLICT (user_id) DO UPDATE SET {conflict_update}
    """
    with _cursor() as cur:
        cur.execute(sql, [user_id] + vals)


def get_all_gtt_enabled_users() -> list:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.email, ks.api_key_enc, ks.api_secret_enc,
                   ks.access_token_enc, ks.access_token_set_at,
                   ks.proximity_threshold_pct, ks.max_allocation_pct
            FROM users u
            JOIN kite_settings ks ON ks.user_id = u.id
            WHERE u.is_active = TRUE
              AND ks.gtt_enabled = TRUE
              AND ks.access_token_enc IS NOT NULL
            """
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# GTT log
# ---------------------------------------------------------------------------

def insert_gtt_log(user_id: int, run_date, symbol: str, strategy: str,
                   gtt_id, status: str, error_msg):
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO gtt_log (user_id, run_date, symbol, strategy, gtt_id, status, error_msg)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, run_date, symbol, strategy, gtt_id, status, error_msg),
        )


def get_gtt_log_today(user_id: int) -> list:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT symbol, strategy, gtt_id, status, error_msg, created_at
            FROM gtt_log
            WHERE user_id = %s AND run_date = CURRENT_DATE
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]
