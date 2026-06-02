import os
from datetime import date, datetime, timezone

import requests
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
# Supabase REST helpers
# ---------------------------------------------------------------------------

def _base_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL environment variable is not set.")
    return f"{url}/rest/v1"


def _headers(prefer: str = "") -> dict:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_KEY environment variable is not set.")
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _get(table: str, params: dict) -> list:
    resp = requests.get(
        f"{_base_url()}/{table}",
        headers=_headers("return=representation"),
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _post(table: str, data: dict, prefer: str = "return=representation") -> list:
    resp = requests.post(
        f"{_base_url()}/{table}",
        headers=_headers(prefer),
        json=data,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _patch(table: str, params: dict, data: dict) -> list:
    resp = requests.patch(
        f"{_base_url()}/{table}",
        headers=_headers("return=representation"),
        params=params,
        json=data,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _upsert(table: str, data: dict, on_conflict: str) -> list:
    resp = requests.post(
        f"{_base_url()}/{table}",
        headers=_headers(f"resolution=merge-duplicates,return=representation"),
        params={"on_conflict": on_conflict},
        json=data,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def init_db():
    # Schema created manually in Supabase SQL editor — nothing to do.
    pass


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: int):
    rows = _get("users", {"id": f"eq.{user_id}", "select": "*"})
    if not rows:
        return None
    r = rows[0]
    return User(r["id"], r["email"], r["is_active"])


def get_user_by_email(email: str):
    rows = _get("users", {"email": f"eq.{email.lower().strip()}", "select": "*"})
    if not rows:
        return None
    r = rows[0]
    return User(r["id"], r["email"], r["is_active"])


def verify_password(email: str, password: str):
    rows = _get("users", {"email": f"eq.{email.lower().strip()}", "select": "*"})
    if not rows:
        return None
    r = rows[0]
    if not check_password_hash(r["password_hash"], password):
        return None
    _patch("users",
           {"id": f"eq.{r['id']}"},
           {"last_login_at": datetime.now(timezone.utc).isoformat()})
    return User(r["id"], r["email"], r["is_active"])


def create_user(email: str, password: str) -> User:
    rows = _post("users", {
        "email": email.lower().strip(),
        "password_hash": generate_password_hash(password),
        "is_active": True,
    })
    r = rows[0]
    return User(r["id"], r["email"], r["is_active"])


# ---------------------------------------------------------------------------
# Kite settings
# ---------------------------------------------------------------------------

def get_kite_settings(user_id: int) -> dict:
    rows = _get("kite_settings", {"user_id": f"eq.{user_id}", "select": "*"})
    if not rows:
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
    return rows[0]


def upsert_kite_settings(user_id: int, **kwargs):
    allowed = {
        "api_key_enc", "api_secret_enc", "access_token_enc",
        "access_token_set_at", "proximity_threshold_pct",
        "max_allocation_pct", "gtt_enabled",
    }
    data = {k: v for k, v in kwargs.items() if k in allowed}
    if not data:
        return
    # Serialise datetime objects
    if "access_token_set_at" in data and hasattr(data["access_token_set_at"], "isoformat"):
        data["access_token_set_at"] = data["access_token_set_at"].isoformat()
    data["user_id"] = user_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _upsert("kite_settings", data, on_conflict="user_id")


def get_all_gtt_enabled_users() -> list:
    settings = _get("kite_settings", {
        "gtt_enabled": "eq.true",
        "access_token_enc": "not.is.null",
        "select": "*",
    })
    if not settings:
        return []

    user_ids = ",".join(str(s["user_id"]) for s in settings)
    users = _get("users", {
        "id": f"in.({user_ids})",
        "is_active": "eq.true",
        "select": "id,email",
    })
    users_by_id = {u["id"]: u for u in users}

    result = []
    for s in settings:
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
    _post("gtt_log", {
        "user_id": user_id,
        "run_date": str(run_date),
        "symbol": symbol,
        "strategy": strategy,
        "gtt_id": gtt_id,
        "status": status,
        "error_msg": error_msg,
    }, prefer="return=minimal")


def get_gtt_log_today(user_id: int) -> list:
    return _get("gtt_log", {
        "user_id": f"eq.{user_id}",
        "run_date": f"eq.{date.today()}",
        "select": "*",
        "order": "created_at.desc",
    })
