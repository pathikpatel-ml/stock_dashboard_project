# Production Hardening Plan — Stock Signal Dashboard

**Started:** 2026-06-03  
**Author:** Solution Architect review + implementation  
**Status:** 🟡 In Progress

> This file is the single source of truth for all in-flight production improvements.
> Any agent picking up this work should read this file first and update the relevant
> section status as each item is completed.

---

## Areas of Work

| # | Area | Status | Commit |
|---|------|--------|--------|
| 1 | Startup latency fix | ✅ Done | see commit |
| 2 | Server-side sessions | ✅ Done | see commit |
| 3 | Notification flows | ✅ Done | see commit |
| 4 | Zerodha settings UX redesign | ✅ Done | see commit |
| 5 | Per-user GTT scheduling | ✅ Done | see commit |

---

## Area 1 — Startup Latency Fix

### Root Cause
`process_v20_signals()` downloads live prices via yfinance for ~800 stocks in chunks of 50
at **import time** (synchronous, blocking). This holds the WSGI process for 60–90 seconds.
GitHub Actions compensates with `sleep 90` confirming the bug.

### Fix
1. **`data_manager.py`**: Add `_startup_done`, `_startup_loading` flags.
   `start_background_load()` starts `load_and_process_data_on_startup()` in a daemon thread.
   `is_ready()` / `is_loading()` helpers for callers.

2. **`app.py`**: Replace blocking call with `data_manager.start_background_load()`.
   Add `/api/ready` endpoint returning `{"status": "ready"|"loading"}`.
   Remove the old `data_manager.load_and_process_data_on_startup()` line.

3. **`modules/v20_layout.py`**: Add `dcc.Interval(id="startup-data-poll", interval=8000)`.

4. **`modules/v20_callbacks.py`**: Add `startup-data-poll` as Input.
   Show "Fetching live prices..." spinner when `data_manager.is_loading()`.
   Separate callback disables the poll interval once `_startup_done=True`.

5. **`.github/workflows/daily_gtt_trigger.yml`**: Replace `sleep 90` with
   a polling loop hitting `/api/ready` every 10s (max 3-minute wait).

### Files Changed
- `data_manager.py`
- `app.py`
- `modules/v20_layout.py`
- `modules/v20_callbacks.py`
- `.github/workflows/daily_gtt_trigger.yml`

---

## Area 2 — Server-Side Sessions

### Root Cause
Flask default sessions are client-side signed cookies. Three issues:
1. `enforce_session_timeout` only runs on non-`/_dash*` paths — heavy Dash callback
   activity (which all hits `/_dash-update-component`) never refreshes `last_active`.
   After 30 min of callback use without a page reload, the next full page load logs you out.
2. Session cookie is a "session cookie" (expires on browser close). Flask-Login's remember
   cookie should re-authenticate, but the `last_active` check in the Flask session is gone
   after browser close, making behaviour unreliable.
3. Admin has no visibility into active sessions.

### Fix
1. **`database/sessions` table** (run in Supabase SQL editor):
   ```sql
   CREATE TABLE sessions (
       id           TEXT        PRIMARY KEY,
       user_id      INTEGER     REFERENCES users(id) ON DELETE CASCADE,
       data         JSONB       NOT NULL DEFAULT '{}',
       created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       last_active  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       expires_at   TIMESTAMPTZ NOT NULL,
       remember_me  BOOLEAN     NOT NULL DEFAULT FALSE,
       ip_address   TEXT,
       user_agent   TEXT
   );
   CREATE INDEX sessions_user_id_idx ON sessions(user_id);
   CREATE INDEX sessions_expires_at_idx ON sessions(expires_at);
   ```

2. **`modules/auth/session_store.py`** (new): Custom `SupabaseSessionInterface`
   extending Flask's `SessionInterface`. Session ID (UUID) in cookie only.
   30-min TTL for normal sessions, 7-day TTL for remember-me. Survives restarts.

3. **`app.py`**: Register `SupabaseSessionInterface`. Remove `enforce_session_timeout`.

4. **`modules/admin/layout.py` + `callbacks.py`**: Add "Active Sessions" section
   showing all sessions with user, IP, last-active, expires — with revoke button.

5. **`database/schema.sql`** + **`.env.example`**: Update to reflect new table.

### Session TTL Rules
- `remember=True` login: 7-day TTL, sliding window (extended on each request)
- Normal login: 30-minute idle timeout
- Expiry checked in `open_session`; expired sessions deleted + new session created

### Files Changed
- `modules/auth/session_store.py` (new)
- `app.py`
- `modules/admin/layout.py`
- `modules/admin/callbacks.py`
- `database/schema.sql`
- `.env.example`

---

## Area 3 — Notification Flows

### What's Being Built
1. **Admin signup notification**: Email to ADMIN_EMAIL when a new user submits `/signup`.
2. **Token expiry email update**: Current email says "reconnect before 8 AM so *tomorrow's*
   job runs." With auto-trigger now live, the email should say "reconnect before 9:15 AM —
   orders will be placed automatically today."
3. **Auto-trigger GTT on reconnect**: After successful OAuth, if `gtt_enabled=True` AND
   current IST time < 9:15 AM AND no GTT log today → run GTT job for this user in background
   thread. Also fires when user enables GTT in Preferences for the first time.
4. **Second GitHub Actions safety-net cron** at 9:05 AM IST.

### Files Changed
- `modules/notifications.py` (new) — shared async SMTP helper
- `modules/auth/signup.py` — call `notify_admin_new_signup` after user creation
- `modules/kite/scheduler.py` — add `user_ids` filter, import from notifications
- `modules/kite/settings_callbacks.py` — add `_maybe_trigger_gtt_for_user` helper
- `.github/workflows/daily_gtt_trigger.yml` — add 9:05 AM safety-net cron
- `.env.example` — add APP_URL

---

## Area 4 — Zerodha Settings UX Redesign

### Problems
1. Returning users see Step 1 ("Create Kite developer account") — irrelevant after first setup.
2. Token expired while user is on Preferences page → no visible warning.
3. GTT Activity Log shows/hides inconsistently (conditionally rendered div).
4. No per-user schedule control.

### Design: Two-Mode Layout

**Condition for wizard mode**: `api_key_enc IS NULL` (first-time user)
**Condition for dashboard mode**: `api_key_enc IS NOT NULL` (returning user)

Both containers exist in the DOM. A callback toggles CSS `display` based on settings.

**Dashboard mode layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  ⚠ Token expired — Reconnect now         [Reconnect →]     │  ← persistent (only when expired)
├──────────────────┬──────────────────────────────────────────┤
│  SIDEBAR         │  CONTENT PANEL                           │
│                  │                                          │
│  ● Connection ●  │  Active section rendered here           │
│  ○ Schedule      │  Updates when sidebar item clicked      │
│  ○ Preferences   │  or 30s interval fires                  │
│  ○ Exclusions    │                                          │
│  ○ Activity Log  │                                          │
└──────────────────┴──────────────────────────────────────────┘
```

**Persistent token banner**: Always above the two-pane layout if token is expired.
Click "Reconnect" → navigates to Connection section automatically.

**Activity Log section**: Always accessible as a sidebar item. Replaces the conditional
`wizard-test-run-section`. Same content (GTT log table + Run Now button).

### New/Changed Callbacks
- `render_kite_mode`: toggles wizard vs dashboard visibility
- `render_dashboard`: renders sidebar + content based on `kite-panel` store + interval
- `sidebar_nav` (pattern-matching): button clicks → update `kite-panel` store
- `save_schedule`: new, saves `schedule_time` + reschedules APScheduler job

All existing wizard callbacks (credential save, OAuth, exclusions, etc.) are preserved.

### Files Changed
- `modules/kite/settings_layout.py` (significant rewrite)
- `modules/kite/settings_callbacks.py` (add dashboard callbacks, preserve wizard callbacks)

---

## Area 5 — Per-User GTT Scheduling

### Current Problem
Two competing schedulers create a race:
- GitHub Actions calls `/api/run-gtt` at 8:00 AM IST (via the GH workflow)
- APScheduler fires `run_premarket_gtt_job()` at 8:30 AM IST (hardcoded for ALL users)

There's no per-user schedule control.

### Fix

**DB**: Add `schedule_time TEXT NOT NULL DEFAULT '08:30'` to `kite_settings`.
Migration: `ALTER TABLE kite_settings ADD COLUMN IF NOT EXISTS schedule_time TEXT NOT NULL DEFAULT '08:30';`

**APScheduler** (per-user jobs):
- `rebuild_user_schedules(sched)`: on startup, query all `gtt_enabled=True` users,
  register individual APScheduler job for each (job ID: `gtt_user_{user_id}`)
- `reschedule_user(sched, user_id, schedule_time)`: update a single user's job
  (called when user saves schedule preference)
- Remove the global `premarket_gtt` cron from `create_scheduler()`

**GitHub Actions new schedule** (3 cron entries):
```yaml
- cron: '25 2 * * 1-5'   # 7:55 AM IST — wake Render dyno
- cron: '55 2 * * 1-5'   # 8:25 AM IST — keep awake (Render sleeps after 15 min)
- cron: '35 3 * * 1-5'   # 9:05 AM IST — safety-net GTT run (idempotent)
```

The 7:55 AM and 8:25 AM jobs just hit `/api/health` (no GTT run).
The 9:05 AM job calls `/api/run-gtt` as a safety net (catches users whose APScheduler
job failed or Render crashed). Idempotent — already-placed GTTs return `skipped_exists`.

**Schedule options in UI** (Preferences section):
- 8:30 AM IST (default, recommended)
- 8:45 AM IST
- 9:00 AM IST
- 9:10 AM IST

### Files Changed
- `modules/auth/user_store.py` — add `schedule_time` to get/upsert
- `modules/kite/scheduler.py` — per-user jobs, `rebuild_user_schedules`, `reschedule_user`
- `modules/kite/settings_layout.py` — Schedule section content
- `modules/kite/settings_callbacks.py` — `save_schedule` callback
- `app.py` — call `rebuild_user_schedules` on startup
- `.github/workflows/daily_gtt_trigger.yml` — new cron entries + job structure
- `database/schema.sql` — add `schedule_time` column

---

## Supabase SQL Migrations Required

Run these in the Supabase SQL editor before or during deployment:

```sql
-- Area 2: Server-side sessions
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT        PRIMARY KEY,
    user_id      INTEGER     REFERENCES users(id) ON DELETE CASCADE,
    data         JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL,
    remember_me  BOOLEAN     NOT NULL DEFAULT FALSE,
    ip_address   TEXT,
    user_agent   TEXT
);
CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON sessions(expires_at);

-- Area 5: Per-user schedule time
ALTER TABLE kite_settings
    ADD COLUMN IF NOT EXISTS schedule_time TEXT NOT NULL DEFAULT '08:30';
```

---

## Environment Variables

New variables to add to Render:

| Variable | Value | Purpose |
|----------|-------|---------|
| `APP_URL` | `https://stock-dashboard-project.onrender.com` | Base URL for notification email links |

Existing variables (must already be set):
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FLASK_SECRET_KEY`, `MASTER_ENCRYPTION_KEY`,
`NOTIFY_EMAIL`, `NOTIFY_EMAIL_PASSWORD`, `GTT_TRIGGER_TOKEN`, `ADMIN_EMAIL`

---

## Verification Checklist

- [ ] App starts in < 5 seconds (login page loads immediately)
- [ ] V20 tab shows "Loading..." spinner, then data appears ~90s later
- [ ] GitHub Actions `/api/ready` polling replaces `sleep 90`
- [ ] Session persists across server restart (log in, restart server, still logged in)
- [ ] Session expires after 30 minutes of inactivity
- [ ] Remember-me session lasts 7 days
- [ ] Admin can view and revoke sessions in Admin panel
- [ ] Admin receives email within 30s of new signup
- [ ] Token expiry email says "reconnect before 9:15 AM — orders placed automatically"
- [ ] User reconnects → GTT job auto-triggers (visible in Activity Log)
- [ ] GTT job does NOT auto-trigger after 9:15 AM IST
- [ ] Returning user opens Zerodha Settings → sees sidebar dashboard (not wizard)
- [ ] Token expired banner visible on all sidebar sections
- [ ] Activity Log always visible as sidebar section
- [ ] User saves schedule preference → APScheduler job updated immediately
- [ ] Two GitHub Actions wake-up pings (7:55 AM, 8:25 AM IST)
- [ ] Safety-net cron at 9:05 AM IST runs without creating duplicate GTTs
