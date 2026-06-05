import json
import logging
import os
import time
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
# In-process session cache
# Avoids a Supabase round-trip on every /_dash-update-component request.
# Key: session ID  Value: {"data": {...}, "expires_at": ISO str, "ts": float}
# TTL: 45 seconds. Cache is per-process (fine for single-worker Render free tier).
# ---------------------------------------------------------------------------
_CACHE_TTL_SEC = 45
_session_cache: dict = {}


def _cache_get(sid: str) -> dict | None:
    entry = _session_cache.get(sid)
    if entry and (time.monotonic() - entry["ts"]) < _CACHE_TTL_SEC:
        return entry
    _session_cache.pop(sid, None)
    return None


def _cache_set(sid: str, data: dict, expires_at_iso: str):
    _session_cache[sid] = {"data": data, "expires_at": expires_at_iso, "ts": time.monotonic()}


def _cache_invalidate(sid: str):
    _session_cache.pop(sid, None)


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
        self.modified = False  # must be last line — do NOT set self.permanent here,
        # it would write {"_permanent": True} into the dict making every empty session
        # appear non-empty and causing a Supabase write on every unauthenticated request.


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
    _cache_invalidate(sid)
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
                "select": "id,data,last_active,expires_at,remember_me,ip_address,created_at",
                "order": "last_active.desc",
            },
            timeout=5,
        )
        sessions = resp.json() if resp.ok else []

        # Extract user_id from session data JSON (Flask-Login stores it as "_user_id")
        for s in sessions:
            try:
                data_dict = json.loads(s.get("data") or "{}")
                raw_id = data_dict.get("_user_id")
                s["user_id"] = int(raw_id) if raw_id else None
            except Exception:
                s["user_id"] = None

        # Only keep sessions that belong to a logged-in user
        sessions = [s for s in sessions if s.get("user_id")]
        if not sessions:
            return []

        # Fetch user names/emails in one query
        user_ids = [s["user_id"] for s in sessions]
        ids_str = ",".join(str(i) for i in user_ids)
        users_resp = _r.get(
            f"{base}/users",
            headers=hdrs,
            params={"id": f"in.({ids_str})", "select": "id,email,name"},
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


def clear_all_sessions():
    """Delete every row from the sessions table.

    Called once at startup so every redeploy forces all users to re-login.
    Clears the in-process cache too so no stale entries survive.
    """
    global _session_cache
    _session_cache = {}
    try:
        # Supabase REST: DELETE without a filter requires the special header
        resp = requests.delete(
            _url(),
            headers={**_hdrs(), "Prefer": "return=minimal"},
            # Match ALL rows — Supabase requires at least one filter; use id neq ''
            params={"id": "neq."},
            timeout=10,
        )
        if resp.ok or resp.status_code == 404:
            logger.info("Startup: cleared all sessions (force re-login after redeploy).")
        else:
            logger.warning("Startup: session clear returned %s — %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Startup: clear_all_sessions failed: %s", exc)


# ---------------------------------------------------------------------------
# Flask session interface
# ---------------------------------------------------------------------------

class SupabaseSessionInterface(SessionInterface):

    @staticmethod
    def _req_path() -> str:
        try:
            import flask
            return flask.request.path
        except Exception:
            return ""

    def open_session(self, app, request):
        sid = request.cookies.get(SESSION_COOKIE_NAME)
        if not sid:
            return SupabaseSession(new=True)

        req_path = request.path
        is_dash = req_path.startswith("/_dash")

        # ── Fast path: serve /_dash* requests from in-process cache ──────────
        # Avoids a Supabase round-trip on every Dash callback (which can be
        # 10-20 per page load). Cache TTL is 45 seconds; page loads always bypass.
        if is_dash:
            cached = _cache_get(sid)
            if cached:
                try:
                    exp = datetime.fromisoformat(cached["expires_at"])
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) < exp:
                        return SupabaseSession(cached["data"], sid=sid, new=False)
                except Exception:
                    pass  # fall through to DB lookup

        # ── Full DB lookup (page loads and cache misses) ──────────────────────
        row = _fetch(sid)
        if not row:
            _cache_invalidate(sid)
            return SupabaseSession(new=True)

        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        except Exception:
            return SupabaseSession(new=True)

        if datetime.now(timezone.utc) > exp:
            _delete(sid)
            _cache_invalidate(sid)
            return SupabaseSession(new=True)

        try:
            data = json.loads(row.get("data") or "{}")
        except Exception:
            data = {}

        # Update cache on every DB hit
        _cache_set(sid, data, row["expires_at"])

        sess = SupabaseSession(data, sid=sid, new=False)

        # Extend TTL on every page load (not /_dash* callbacks).
        # This makes the 30-min timeout a true IDLE timeout:
        # any page load resets the clock; inactivity for 30 min = logout.
        if not is_dash:
            sess.modified = True  # triggers save_session → extends expires_at to now+30min

        return sess

    def save_session(self, app, session, response):
        req_path = self._req_path()

        # Skip /api/ endpoints entirely (no cookies needed there)
        if req_path.startswith("/api/"):
            return

        is_dash = req_path.startswith("/_dash")

        # For Dash internals, only write to DB if session data actually changed.
        # This prevents a Supabase write on every callback (the main performance fix).
        if is_dash and not session.modified:
            return

        # Empty session with no changes — nothing to persist
        if not session and not session.modified:
            return

        # Always use 30-min idle TTL regardless of remember flag.
        # Sessions persist across browser restarts (cookie has 30-min expiry)
        # but expire after 30 minutes of inactivity (no page load).
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_TTL_SECONDS)

        try:
            import flask
            ip = flask.request.remote_addr or ""
            ua = flask.request.headers.get("User-Agent", "")
        except Exception:
            ip, ua = "", ""

        _save(session.sid, dict(session), expires_at, False, ip, ua)

        # Keep cache in sync after write
        _cache_set(session.sid, dict(session), expires_at.isoformat())

        # Cookie expiry = 30 min from now so it survives browser restarts
        # within the active window but auto-clears when session expires.
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session.sid,
            expires=expires_at,
            httponly=True,
            secure=bool(os.environ.get("RENDER")),
            samesite="Lax",
            path="/",
        )
