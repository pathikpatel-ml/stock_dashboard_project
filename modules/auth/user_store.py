import os
from datetime import date, datetime, timezone

from flask_login import UserMixin
from supabase import create_client, Client
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
# Client
# ---------------------------------------------------------------------------

def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables must be set."
        )
    return create_client(url, key)


def init_db():
    # Schema created manually via Supabase SQL editor — nothing to do here.
    pass


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: int):
    resp = _get_client().table("users").select("*").eq("id", user_id).execute()
    if not resp.data:
        return None
    row = resp.data[0]
    return User(row["id"], row["email"], row["is_active"])


def get_user_by_email(email: str):
    resp = _get_client().table("users").select("*").eq(
        "email", email.lower().strip()
    ).execute()
    if not resp.data:
        return None
    row = resp.data[0]
    return User(row["id"], row["email"], row["is_active"])


def verify_password(email: str, password: str):
    resp = _get_client().table("users").select("*").eq(
        "email", email.lower().strip()
    ).execute()
    if not resp.data:
        return None
    row = resp.data[0]
    if not check_password_hash(row["password_hash"], password):
        return None
    _get_client().table("users").update(
        {"last_login_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", row["id"]).execute()
    return User(row["id"], row["email"], row["is_active"])


def create_user(email: str, password: str) -> User:
    hashed = generate_password_hash(password)
    resp = _get_client().table("users").insert({
        "email": email.lower().strip(),
        "password_hash": hashed,
        "is_active": True,
    }).execute()
    row = resp.data[0]
    return User(row["id"], row["email"], row["is_active"])


# ---------------------------------------------------------------------------
# Kite settings
# ---------------------------------------------------------------------------

def get_kite_settings(user_id: int) -> dict:
    resp = _get_client().table("kite_settings").select("*").eq(
        "user_id", user_id
    ).execute()
    if not resp.data:
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
    return resp.data[0]


def upsert_kite_settings(user_id: int, **kwargs):
    allowed = {
        "api_key_enc", "api_secret_enc", "access_token_enc",
        "access_token_set_at", "proximity_threshold_pct",
        "max_allocation_pct", "gtt_enabled",
    }
    data = {k: v for k, v in kwargs.items() if k in allowed}
    if not data:
        return
    # Serialise datetime objects to ISO strings
    for key in ("access_token_set_at",):
        if key in data and hasattr(data[key], "isoformat"):
            data[key] = data[key].isoformat()
    data["user_id"] = user_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _get_client().table("kite_settings").upsert(data, on_conflict="user_id").execute()


def get_all_gtt_enabled_users() -> list:
    client = _get_client()
    settings_resp = client.table("kite_settings").select("*").eq(
        "gtt_enabled", True
    ).not_.is_("access_token_enc", "null").execute()

    if not settings_resp.data:
        return []

    user_ids = [s["user_id"] for s in settings_resp.data]
    users_resp = client.table("users").select(
        "id, email, is_active"
    ).in_("id", user_ids).eq("is_active", True).execute()

    users_by_id = {u["id"]: u for u in users_resp.data}

    result = []
    for s in settings_resp.data:
        user = users_by_id.get(s["user_id"])
        if user:
            result.append({
                "id": user["id"],
                "email": user["email"],
                "api_key_enc": s["api_key_enc"],
                "api_secret_enc": s["api_secret_enc"],
                "access_token_enc": s["access_token_enc"],
                "access_token_set_at": s.get("access_token_set_at"),
                "proximity_threshold_pct": s["proximity_threshold_pct"],
                "max_allocation_pct": s["max_allocation_pct"],
            })
    return result


# ---------------------------------------------------------------------------
# GTT log
# ---------------------------------------------------------------------------

def insert_gtt_log(user_id: int, run_date, symbol: str, strategy: str,
                   gtt_id, status: str, error_msg):
    _get_client().table("gtt_log").insert({
        "user_id": user_id,
        "run_date": str(run_date),
        "symbol": symbol,
        "strategy": strategy,
        "gtt_id": gtt_id,
        "status": status,
        "error_msg": error_msg,
    }).execute()


def get_gtt_log_today(user_id: int) -> list:
    resp = _get_client().table("gtt_log").select("*").eq(
        "user_id", user_id
    ).eq("run_date", str(date.today())).order(
        "created_at", desc=True
    ).execute()
    return resp.data or []
