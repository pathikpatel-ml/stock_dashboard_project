import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests
from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "ssd_sid"
DEFAULT_TTL_SECONDS = 30 * 60          # 30-minute idle timeout
REMEMBER_TTL_SECONDS = 7 * 24 * 3600  # 7-day remember-me


# ---------------------------------------------------------------------------
# Session object
# ---------------------------------------------------------------------------

class SupabaseSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid: str = "", new: bool = False):
        def on_update(self):
            self.modified = True
        CallbackDict.__init__(self, initial or {}, on_update)
        self.sid = sid or str(uuid.uuid4())
        self.new = new
        self.permanent = True  # SessionMixin.permanent.setter writes to dict → triggers on_update
        self.modified = False  # must be last line


# ---------------------------------------------------------------------------
# Supabase REST helpers (isolated — no import from user_store to avoid circles)
# ---------------------------------------------------------------------------

def _url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/") + "/rest/v1/sessions"


def _hdrs(prefer: str = "") -> dict:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _fetch(sid: str) -> dict | None:
    try:
        resp = requests.get(
            _url(),
            headers=_hdrs(),
            params={"id": f"eq.{sid}", "select": "*"},
            timeout=5,
        )
        rows = resp.json() if resp.ok else []
        return rows[0] if rows else None
    except Exception as exc:
        logger.debug("Session fetch failed: %s", exc)
        return None


def _save(sid: str, data: dict, expires_at: datetime,
          remember_me: bool, ip: str, ua: str):
    try:
        requests.post(
            _url(),
            headers=_hdrs("resolution=merge-duplicates,return=minimal"),
            params={"on_conflict": "id"},
            json={
                "id": sid,
                "data": json.dumps(data),
                "expires_at": expires_at.isoformat(),
                "last_active": datetime.now(timezone.utc).isoformat(),
                "remember_me": remember_me,
                "ip_address": ip,
                "user_agent": ua[:200] if ua else None,
            },
            timeout=5,
        )
    except Exception as exc:
        logger.warning("Session save failed: %s", exc)


def _delete(sid: str):
    try:
        requests.delete(
            _url(),
            headers=_hdrs(),
            params={"id": f"eq.{sid}"},
            timeout=5,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Admin helpers (used by admin callbacks)
# ---------------------------------------------------------------------------

def get_all_active_sessions() -> list:
    """Return all non-expired sessions with user info joined."""
    try:
        import requests as _r
        base = os.environ.get("SUPABASE_URL", "").rstrip("/") + "/rest/v1"
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        hdrs = {"apikey": key, "Authorization": f"Bearer {key}"}
        now_iso = datetime.now(timezone.utc).isoformat()
        resp = _r.get(
            f"{base}/sessions",
            headers=hdrs,
            params={
                "expires_at": f"gt.{now_iso}",
                "select": "id,user_id,last_active,expires_at,remember_me,ip_address,created_at",
                "order": "last_active.desc",
            },
            timeout=5,
        )
        sessions = resp.json() if resp.ok else []

        # Fetch user emails in one query
        if sessions:
            ids = ",".join(str(s["user_id"]) for s in sessions if s.get("user_id"))
            users_resp = _r.get(
                f"{base}/users",
                headers=hdrs,
                params={"id": f"in.({ids})", "select": "id,email,name"},
                timeout=5,
            )
            users = {u["id"]: u for u in (users_resp.json() if users_resp.ok else [])}
            for s in sessions:
                u = users.get(s.get("user_id"), {})
                s["email"] = u.get("email", "—")
                s["name"] = u.get("name", "—")
        return sessions
    except Exception as exc:
        logger.warning("get_all_active_sessions failed: %s", exc)
        return []


def revoke_session(sid: str):
    _delete(sid)


def revoke_all_user_sessions(user_id: int):
    try:
        requests.delete(
            _url(),
            headers=_hdrs(),
            params={"user_id": f"eq.{user_id}"},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("revoke_all_user_sessions failed: %s", exc)


# ---------------------------------------------------------------------------
# Flask session interface
# ---------------------------------------------------------------------------

class SupabaseSessionInterface(SessionInterface):

    def open_session(self, app, request):
        sid = request.cookies.get(SESSION_COOKIE_NAME)
        if not sid:
            return SupabaseSession(new=True)

        row = _fetch(sid)
        if not row:
            return SupabaseSession(new=True)

        # Check expiry
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        except Exception:
            return SupabaseSession(new=True)

        if datetime.now(timezone.utc) > exp:
            _delete(sid)
            return SupabaseSession(new=True)

        # Deserialise
        try:
            data = json.loads(row.get("data") or "{}")
        except Exception:
            data = {}

        sess = SupabaseSession(data, sid=sid, new=False)

        # Extend TTL if less than half of it remains (sliding window, reduces DB writes)
        remember_me = row.get("remember_me", False)
        ttl = REMEMBER_TTL_SECONDS if remember_me else DEFAULT_TTL_SECONDS
        remaining = (exp - datetime.now(timezone.utc)).total_seconds()
        if remaining < ttl / 2:
            sess.modified = True  # triggers save_session to extend expiry

        return sess

    def save_session(self, app, session, response):
        if not session and not session.modified:
            return

        # Don't set cookies for API endpoints
        path = getattr(getattr(app, "_request_ctx_stack", None), "top", None)
        try:
            import flask
            req_path = flask.request.path
        except Exception:
            req_path = ""
        if req_path.startswith("/api/"):
            return

        remember_me = bool(session.get("_remember") == "set")
        ttl = REMEMBER_TTL_SECONDS if remember_me else DEFAULT_TTL_SECONDS
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        try:
            import flask
            ip = flask.request.remote_addr or ""
            ua = flask.request.headers.get("User-Agent", "")
        except Exception:
            ip, ua = "", ""

        _save(session.sid, dict(session), expires_at, remember_me, ip, ua)

        # Cookie: long-lived for remember-me, session cookie otherwise
        cookie_expires = expires_at if remember_me else None
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session.sid,
            expires=cookie_expires,
            httponly=True,
            secure=bool(os.environ.get("RENDER")),
            samesite="Lax",
            path="/",
        )
