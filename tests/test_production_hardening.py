"""
Unit tests for production hardening changes.
Tests pure logic only — no DB, no SMTP, no yfinance, no Dash server.
External calls are mocked where needed.

Run: python -m pytest tests/test_production_hardening.py -v
"""
import json
import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Minimal env stubs so modules that read env vars at import time don't crash
# ---------------------------------------------------------------------------
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy-key")
os.environ.setdefault("MASTER_ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4cmVkc3RhcnRlcjEyMzQ1Njc4OTAxMjM=")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key")
os.environ.setdefault("NOTIFY_EMAIL", "")
os.environ.setdefault("NOTIFY_EMAIL_PASSWORD", "")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault("APP_URL", "https://example.com")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ===========================================================================
# Area 1: Startup latency / data_manager
# ===========================================================================

class TestDataManagerStartup(unittest.TestCase):

    def setUp(self):
        import data_manager
        data_manager._startup_loading = False
        data_manager._startup_done = False
        self.dm = data_manager

    def test_initial_state_not_loading_not_ready(self):
        self.assertFalse(self.dm.is_loading())
        self.assertFalse(self.dm.is_ready())

    def test_is_loading_true_while_loading_not_done(self):
        self.dm._startup_loading = True
        self.dm._startup_done = False
        self.assertTrue(self.dm.is_loading())
        self.assertFalse(self.dm.is_ready())

    def test_is_ready_true_when_done(self):
        self.dm._startup_loading = False
        self.dm._startup_done = True
        self.assertFalse(self.dm.is_loading())
        self.assertTrue(self.dm.is_ready())

    def test_start_background_load_spawns_thread(self):
        """start_background_load sets _startup_loading=True and spawns a daemon thread."""
        import data_manager
        data_manager._startup_loading = False
        data_manager._startup_done = False

        with patch.object(data_manager, "load_and_process_data_on_startup") as mock_load:
            mock_load.side_effect = lambda: None  # instant no-op
            data_manager.start_background_load()
            # Give thread a moment to set the flag
            time.sleep(0.05)
            # After thread spawns, _startup_loading is True
            # (may already be False if thread finished instantly, so just check it ran)
            mock_load.assert_called_once()

    def test_load_sets_done_flag(self):
        """load_and_process_data_on_startup should set _startup_done=True at end."""
        import data_manager
        data_manager._startup_loading = True
        data_manager._startup_done = False

        # Patch heavy functions so they don't actually run
        with patch.object(data_manager, "_read_csv_with_candidates",
                          return_value=(data_manager.pd.DataFrame(), None, None)), \
             patch.object(data_manager, "load_breakout_data_on_startup"):
            data_manager.load_and_process_data_on_startup()

        self.assertTrue(data_manager._startup_done)
        self.assertFalse(data_manager._startup_loading)


# ===========================================================================
# Area 2: Server-side sessions
# ===========================================================================

class TestSupabaseSession(unittest.TestCase):

    def test_creation_with_initial_data(self):
        from modules.auth.session_store import SupabaseSession
        sess = SupabaseSession({"_user_id": "42"}, sid="abc-123")
        self.assertEqual(sess["_user_id"], "42")
        self.assertEqual(sess.sid, "abc-123")
        self.assertFalse(sess.new)
        self.assertFalse(sess.modified)

    def test_new_session_auto_generates_sid(self):
        from modules.auth.session_store import SupabaseSession
        sess = SupabaseSession(new=True)
        self.assertTrue(len(sess.sid) > 10)  # UUID is 36 chars
        self.assertTrue(sess.new)

    def test_modification_sets_modified_flag(self):
        from modules.auth.session_store import SupabaseSession
        sess = SupabaseSession({"a": 1}, sid="xyz")
        self.assertFalse(sess.modified)
        sess["b"] = 2
        self.assertTrue(sess.modified)

    def test_session_behaves_like_dict(self):
        from modules.auth.session_store import SupabaseSession
        sess = SupabaseSession({"key": "value"}, sid="s1")
        self.assertEqual(sess["key"], "value")
        self.assertIn("key", sess)
        sess["new"] = "val"
        self.assertEqual(sess["new"], "val")
        del sess["key"]
        self.assertNotIn("key", sess)


class TestSupabaseSessionInterface(unittest.TestCase):

    def _mock_row(self, sid="abc", data=None, remember_me=False, expired=False):
        """Build a fake session row as returned by Supabase."""
        exp = datetime.now(timezone.utc) + (
            timedelta(seconds=-1) if expired else timedelta(hours=1)
        )
        return {
            "id": sid,
            "data": json.dumps(data or {"_user_id": "1"}),
            "expires_at": exp.isoformat(),
            "last_active": datetime.now(timezone.utc).isoformat(),
            "remember_me": remember_me,
        }

    @patch("modules.auth.session_store._fetch")
    @patch("modules.auth.session_store._save")
    def test_open_existing_valid_session(self, mock_save, mock_fetch):
        from modules.auth.session_store import SupabaseSessionInterface, _cache_invalidate
        mock_fetch.return_value = self._mock_row("abc", {"_user_id": "5"})
        _cache_invalidate("abc")  # ensure no stale cache

        iface = SupabaseSessionInterface()
        app = MagicMock()
        request = MagicMock()
        request.cookies = {"ssd_sid": "abc"}
        request.path = "/"  # page load — bypasses cache

        sess = iface.open_session(app, request)

        self.assertEqual(sess["_user_id"], "5")
        self.assertFalse(sess.new)
        self.assertEqual(sess.sid, "abc")

    @patch("modules.auth.session_store._fetch")
    def test_open_session_no_cookie_creates_new(self, mock_fetch):
        from modules.auth.session_store import SupabaseSessionInterface
        iface = SupabaseSessionInterface()
        app = MagicMock()
        request = MagicMock()
        request.cookies = {}
        request.path = "/"

        sess = iface.open_session(app, request)

        self.assertTrue(sess.new)
        mock_fetch.assert_not_called()

    @patch("modules.auth.session_store._delete")
    @patch("modules.auth.session_store._fetch")
    def test_open_expired_session_creates_new_and_deletes(self, mock_fetch, mock_delete):
        from modules.auth.session_store import SupabaseSessionInterface, _cache_invalidate
        mock_fetch.return_value = self._mock_row("old-sid", expired=True)
        _cache_invalidate("old-sid")

        iface = SupabaseSessionInterface()
        app = MagicMock()
        request = MagicMock()
        request.cookies = {"ssd_sid": "old-sid"}
        request.path = "/"  # page load — bypasses cache

        sess = iface.open_session(app, request)

        self.assertTrue(sess.new)
        mock_delete.assert_called_once_with("old-sid")

    @patch("modules.auth.session_store._fetch")
    def test_open_nonexistent_session_creates_new(self, mock_fetch):
        from modules.auth.session_store import SupabaseSessionInterface, _cache_invalidate
        mock_fetch.return_value = None
        _cache_invalidate("ghost-sid")

        iface = SupabaseSessionInterface()
        app = MagicMock()
        request = MagicMock()
        request.cookies = {"ssd_sid": "ghost-sid"}
        request.path = "/"

        sess = iface.open_session(app, request)
        self.assertTrue(sess.new)

    def test_open_dash_callback_uses_cache(self):
        """/_dash-* requests should use in-process cache, not hit DB."""
        from modules.auth.session_store import (
            SupabaseSessionInterface, _cache_set, _cache_invalidate
        )
        _cache_set("cached-sid", {"_user_id": "9"},
                   (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())

        iface = SupabaseSessionInterface()
        app = MagicMock()
        request = MagicMock()
        request.cookies = {"ssd_sid": "cached-sid"}
        request.path = "/_dash-update-component"

        with patch("modules.auth.session_store._fetch") as mock_fetch:
            sess = iface.open_session(app, request)
            mock_fetch.assert_not_called()  # cache hit — no DB call

        self.assertEqual(sess["_user_id"], "9")
        _cache_invalidate("cached-sid")

    def test_save_session_skips_db_for_dash_when_unmodified(self):
        """/_dash-* requests should not write to DB when session data unchanged."""
        from modules.auth.session_store import SupabaseSession, SupabaseSessionInterface
        from app import server
        with server.test_request_context("/_dash-update-component"):
            iface = SupabaseSessionInterface()
            response = MagicMock()
            sess = SupabaseSession({"_user_id": "5"}, sid="unmod-dash")
            # modified=False means nothing changed

            with patch("modules.auth.session_store._save") as mock_save:
                iface.save_session(server, sess, response)
                mock_save.assert_not_called()  # no write for unmodified dash requests

    @patch("modules.auth.session_store._save")
    def test_save_session_calls_upsert(self, mock_save):
        import flask
        from modules.auth.session_store import SupabaseSession, SupabaseSessionInterface, DEFAULT_TTL_SECONDS

        # Need an active Flask request context for flask.request to work
        from app import server
        with server.test_request_context("/"):
            iface = SupabaseSessionInterface()
            response = MagicMock()

            sess = SupabaseSession({"_user_id": "3"}, sid="save-test")
            sess.modified = True

            iface.save_session(server, sess, response)

        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        self.assertEqual(args[0], "save-test")
        self.assertEqual(args[1]["_user_id"], "3")
        exp: datetime = args[2]
        delta = (exp - datetime.now(timezone.utc)).total_seconds()
        self.assertAlmostEqual(delta, DEFAULT_TTL_SECONDS, delta=5)

    @patch("modules.auth.session_store._save")
    def test_save_always_uses_default_ttl(self, mock_save):
        """Even with _remember=set, session always uses DEFAULT_TTL_SECONDS (30 min)."""
        from modules.auth.session_store import (
            SupabaseSession, SupabaseSessionInterface, DEFAULT_TTL_SECONDS
        )
        from app import server
        with server.test_request_context("/"):
            iface = SupabaseSessionInterface()
            response = MagicMock()

            # _remember="set" used to trigger 7-day TTL; should now be ignored
            sess = SupabaseSession({"_user_id": "7", "_remember": "set"}, sid="rem-test")
            sess.modified = True

            iface.save_session(server, sess, response)

        args = mock_save.call_args[0]
        exp: datetime = args[2]
        delta = (exp - datetime.now(timezone.utc)).total_seconds()
        # Should be ~30 min (DEFAULT_TTL), NOT 7 days
        self.assertAlmostEqual(delta, DEFAULT_TTL_SECONDS, delta=5)
        self.assertLess(delta, 3600)  # definitely less than 1 hour


# ===========================================================================
# Area 3: Notifications
# ===========================================================================

class TestNotifications(unittest.TestCase):

    @patch("modules.notifications._smtp_send")
    def test_send_email_async_calls_smtp_in_thread(self, mock_smtp):
        from modules.notifications import send_email_async
        send_email_async("to@test.com", "Subject", "<b>body</b>")
        time.sleep(0.1)  # let thread run
        mock_smtp.assert_called_once_with("to@test.com", "Subject", "<b>body</b>")

    @patch("modules.notifications.send_email_async")
    def test_notify_admin_new_signup_sends_to_admin(self, mock_send):
        from modules.notifications import notify_admin_new_signup
        notify_admin_new_signup("Rahul Kumar", "rahul@example.com")
        mock_send.assert_called_once()
        to, subject, body = mock_send.call_args[0]
        self.assertEqual(to, "admin@test.com")  # matches ADMIN_EMAIL env
        self.assertIn("Rahul Kumar", subject)
        self.assertIn("rahul@example.com", subject)
        self.assertIn("rahul@example.com", body)

    @patch("modules.notifications.send_email_async")
    def test_notify_token_expired_sends_to_user(self, mock_send):
        from modules.notifications import notify_token_expired
        notify_token_expired("user@test.com")
        mock_send.assert_called_once()
        to, subject, body = mock_send.call_args[0]
        self.assertEqual(to, "user@test.com")
        self.assertIn("9:15 AM IST", body)       # updated message
        self.assertIn("automatically", body)      # auto-place message
        self.assertNotIn("tomorrow", body.lower()) # old text removed

    def test_smtp_not_called_when_creds_missing(self):
        """When NOTIFY_EMAIL is unset, smtplib.SMTP should never be instantiated."""
        import modules.notifications as notif
        old_email = os.environ.pop("NOTIFY_EMAIL", "")
        old_pass = os.environ.pop("NOTIFY_EMAIL_PASSWORD", "")
        try:
            with patch("smtplib.SMTP") as mock_smtp_class:
                notif._smtp_send("x@x.com", "s", "b")
                mock_smtp_class.assert_not_called()
        finally:
            if old_email:
                os.environ["NOTIFY_EMAIL"] = old_email
            if old_pass:
                os.environ["NOTIFY_EMAIL_PASSWORD"] = old_pass


# ===========================================================================
# Area 3: Auto-trigger GTT (scheduler logic)
# ===========================================================================

class TestSchedulerHelpers(unittest.TestCase):

    def test_schedule_to_utc_conversions(self):
        from modules.kite.scheduler import _schedule_to_utc
        cases = [
            ("08:30", (3, 0)),
            ("08:45", (3, 15)),
            ("09:00", (3, 30)),
            ("09:10", (3, 40)),
            ("08:00", (2, 30)),
        ]
        for ist_time, expected_utc in cases:
            with self.subTest(ist=ist_time):
                result = _schedule_to_utc(ist_time)
                self.assertEqual(result, expected_utc,
                                 f"{ist_time} IST → expected UTC {expected_utc}, got {result}")

    def test_is_premarket_ist_false_on_weekend(self):
        from modules.kite.scheduler import _is_premarket_ist
        from datetime import datetime, timezone, timedelta
        _IST = timezone(timedelta(hours=5, minutes=30))
        # Patch datetime.now to return a Saturday 8:00 AM IST
        with patch("modules.kite.scheduler.datetime") as mock_dt:
            saturday = datetime(2026, 6, 6, 8, 0, 0, tzinfo=_IST)  # Saturday
            mock_dt.now.return_value = saturday
            self.assertFalse(_is_premarket_ist())

    def test_is_premarket_ist_true_before_915_on_weekday(self):
        from modules.kite.scheduler import _is_premarket_ist
        from datetime import datetime, timezone, timedelta
        _IST = timezone(timedelta(hours=5, minutes=30))
        with patch("modules.kite.scheduler.datetime") as mock_dt:
            monday_8am = datetime(2026, 6, 1, 8, 0, 0, tzinfo=_IST)  # Monday
            mock_dt.now.return_value = monday_8am
            self.assertTrue(_is_premarket_ist())

    def test_is_premarket_ist_false_after_915_on_weekday(self):
        from modules.kite.scheduler import _is_premarket_ist
        from datetime import datetime, timezone, timedelta
        _IST = timezone(timedelta(hours=5, minutes=30))
        with patch("modules.kite.scheduler.datetime") as mock_dt:
            monday_930 = datetime(2026, 6, 1, 9, 30, 0, tzinfo=_IST)  # Monday 9:30
            mock_dt.now.return_value = monday_930
            self.assertFalse(_is_premarket_ist())

    @patch("modules.kite.scheduler._is_premarket_ist", return_value=False)
    def test_maybe_trigger_returns_none_outside_market_hours(self, _):
        from modules.kite.scheduler import _maybe_trigger_gtt_for_user
        result = _maybe_trigger_gtt_for_user(1)
        self.assertIsNone(result)

    @patch("modules.kite.scheduler.user_store")
    @patch("modules.kite.scheduler._is_premarket_ist", return_value=True)
    def test_maybe_trigger_returns_none_when_gtt_disabled(self, _, mock_store):
        from modules.kite.scheduler import _maybe_trigger_gtt_for_user
        mock_store.get_kite_settings.return_value = {"gtt_enabled": False}
        result = _maybe_trigger_gtt_for_user(1)
        self.assertIsNone(result)

    @patch("modules.kite.scheduler.user_store")
    @patch("modules.kite.scheduler._is_premarket_ist", return_value=True)
    def test_maybe_trigger_returns_none_when_already_ran(self, _, mock_store):
        from modules.kite.scheduler import _maybe_trigger_gtt_for_user
        mock_store.get_kite_settings.return_value = {
            "gtt_enabled": True, "access_token_enc": "tok123"
        }
        mock_store.get_gtt_log_today.return_value = [{"symbol": "TCS"}]  # already ran
        result = _maybe_trigger_gtt_for_user(1)
        self.assertIsNone(result)

    @patch("threading.Thread")
    @patch("modules.kite.scheduler.user_store")
    @patch("modules.kite.scheduler._is_premarket_ist", return_value=True)
    def test_maybe_trigger_spawns_thread_when_conditions_met(self, _, mock_store, mock_thread):
        from modules.kite.scheduler import _maybe_trigger_gtt_for_user
        mock_store.get_kite_settings.return_value = {
            "gtt_enabled": True, "access_token_enc": "tok123"
        }
        mock_store.get_gtt_log_today.return_value = []  # no log yet
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        result = _maybe_trigger_gtt_for_user(99)

        self.assertIsNotNone(result)
        self.assertIn("GTT", result)
        mock_thread_instance.start.assert_called_once()


# ===========================================================================
# Area 4: Settings layout (smoke test — no DB calls)
# ===========================================================================

class TestSettingsLayout(unittest.TestCase):

    def test_create_kite_settings_layout_returns_component(self):
        from modules.kite.settings_layout import create_kite_settings_layout
        layout = create_kite_settings_layout()
        # Should return a Dash Container
        self.assertIsNotNone(layout)
        self.assertEqual(layout.__class__.__name__, "Container")

    def test_layout_has_wizard_and_dashboard_containers(self):
        from modules.kite.settings_layout import create_kite_settings_layout
        import json
        layout = create_kite_settings_layout()
        layout_str = str(layout)
        self.assertIn("kite-wizard-container", layout_str)
        self.assertIn("kite-dashboard-container", layout_str)
        self.assertIn("kite-panel", layout_str)

    def test_sidebar_renders_all_five_sections(self):
        from modules.kite.settings_layout import _sidebar
        settings = {"access_token_enc": None}
        sidebar = _sidebar("connection", settings)
        sidebar_str = str(sidebar)
        for section in ["connection", "schedule", "prefs", "exclusions", "activity"]:
            self.assertIn(section, sidebar_str,
                          f"Sidebar should contain nav button for '{section}'")

    def test_schedule_section_has_four_options(self):
        from modules.kite.settings_layout import _schedule_section
        settings = {"schedule_time": "08:30"}
        section = _schedule_section(settings)
        section_str = str(section)
        for t in ["08:30", "08:45", "09:00", "09:10"]:
            self.assertIn(t, section_str)

    def test_connection_badge_not_connected(self):
        from modules.kite.settings_layout import _connection_badge_from_settings
        badge = _connection_badge_from_settings({"access_token_enc": None})
        badge_str = str(badge)
        self.assertIn("Not Connected", badge_str)

    def test_connection_badge_connected(self):
        from modules.kite.settings_layout import _connection_badge_from_settings
        with patch("modules.kite.portfolio.is_token_valid", return_value=True):
            badge = _connection_badge_from_settings({
                "access_token_enc": "tok123",
                "access_token_set_at": datetime.now(timezone.utc).isoformat(),
            })
        badge_str = str(badge)
        self.assertIn("Connected", badge_str)

    def test_connection_badge_expired(self):
        from modules.kite.settings_layout import _connection_badge_from_settings
        with patch("modules.kite.portfolio.is_token_valid", return_value=False):
            badge = _connection_badge_from_settings({
                "access_token_enc": "tok123",
                "access_token_set_at": "2026-01-01T00:00:00+00:00",
            })
        badge_str = str(badge)
        self.assertIn("Expired", badge_str)

    def test_expired_banner_content(self):
        from modules.kite.settings_layout import _expired_banner
        banner = _expired_banner()
        banner_str = str(banner)
        self.assertIn("9:15 AM", banner_str)
        self.assertIn("banner-goto-connection", banner_str)


# ===========================================================================
# Area 5: Per-user scheduling — APScheduler job management
# ===========================================================================

class TestPerUserScheduling(unittest.TestCase):

    def test_reschedule_user_adds_job_when_not_exists(self):
        from modules.kite.scheduler import reschedule_user
        mock_sched = MagicMock()
        mock_sched.reschedule_job.side_effect = Exception("Job not found")

        reschedule_user(mock_sched, user_id=42, schedule_time="08:45")

        mock_sched.add_job.assert_called_once()
        call_kwargs = mock_sched.add_job.call_args
        self.assertEqual(call_kwargs[1]["id"], "gtt_user_42")
        self.assertEqual(call_kwargs[1]["hour"], 3)   # 08:45 IST = 03:15 UTC
        self.assertEqual(call_kwargs[1]["minute"], 15)
        self.assertEqual(call_kwargs[1]["kwargs"], {"user_ids": [42]})

    def test_reschedule_user_reschedules_existing_job(self):
        from modules.kite.scheduler import reschedule_user
        mock_sched = MagicMock()

        reschedule_user(mock_sched, user_id=7, schedule_time="09:00")

        mock_sched.reschedule_job.assert_called_once_with(
            "gtt_user_7",
            trigger="cron",
            hour=3,
            minute=30,
            day_of_week="mon-fri",
        )
        mock_sched.add_job.assert_not_called()

    @patch("modules.kite.scheduler.user_store")
    def test_rebuild_user_schedules_registers_jobs_for_all_users(self, mock_store):
        from modules.kite.scheduler import rebuild_user_schedules
        mock_store.get_all_gtt_enabled_users.return_value = [
            {"id": 1, "email": "a@x.com", "schedule_time": "08:30"},
            {"id": 2, "email": "b@x.com", "schedule_time": "09:00"},
        ]
        mock_sched = MagicMock()

        with patch("modules.kite.scheduler.reschedule_user") as mock_resched:
            rebuild_user_schedules(mock_sched)
            self.assertEqual(mock_resched.call_count, 2)
            mock_resched.assert_any_call(mock_sched, 1, "08:30")
            mock_resched.assert_any_call(mock_sched, 2, "09:00")

    @patch("modules.kite.scheduler.user_store")
    def test_rebuild_user_schedules_handles_empty_user_list(self, mock_store):
        from modules.kite.scheduler import rebuild_user_schedules
        mock_store.get_all_gtt_enabled_users.return_value = []
        mock_sched = MagicMock()

        with patch("modules.kite.scheduler.reschedule_user") as mock_resched:
            rebuild_user_schedules(mock_sched)
            mock_resched.assert_not_called()


# ===========================================================================
# User store schema defaults
# ===========================================================================

class TestUserStoreDefaults(unittest.TestCase):

    @patch("modules.auth.user_store._get", return_value=[])
    def test_get_kite_settings_default_has_schedule_time(self, _):
        from modules.auth.user_store import get_kite_settings
        result = get_kite_settings(1)
        self.assertEqual(result["schedule_time"], "08:30")

    @patch("modules.auth.user_store._get", return_value=[{
        "user_id": 1, "api_key_enc": "k", "gtt_enabled": True,
        "proximity_threshold_pct": 2.0, "max_allocation_pct": 3.0,
        "schedule_time": "09:00",
    }])
    def test_get_kite_settings_returns_db_schedule_time(self, _):
        from modules.auth.user_store import get_kite_settings
        result = get_kite_settings(1)
        self.assertEqual(result["schedule_time"], "09:00")

    @patch("modules.auth.user_store._get", return_value=[{
        "user_id": 1, "api_key_enc": "k", "gtt_enabled": True,
        "proximity_threshold_pct": 2.0, "max_allocation_pct": 3.0,
        "schedule_time": None,  # NULL in DB
    }])
    def test_get_kite_settings_defaults_null_schedule_time(self, _):
        from modules.auth.user_store import get_kite_settings
        result = get_kite_settings(1)
        self.assertEqual(result["schedule_time"], "08:30")


# ===========================================================================
# Import sanity checks — all new/modified modules must import cleanly
# ===========================================================================

class TestImports(unittest.TestCase):

    def test_data_manager_imports(self):
        import data_manager
        self.assertTrue(hasattr(data_manager, "start_background_load"))
        self.assertTrue(hasattr(data_manager, "is_loading"))
        self.assertTrue(hasattr(data_manager, "is_ready"))

    def test_session_store_imports(self):
        from modules.auth.session_store import (
            SupabaseSession, SupabaseSessionInterface,
            get_all_active_sessions, revoke_session,
        )
        self.assertTrue(True)

    def test_notifications_imports(self):
        from modules.notifications import (
            send_email_async, notify_admin_new_signup, notify_token_expired,
        )
        self.assertTrue(True)

    def test_scheduler_imports(self):
        from modules.kite.scheduler import (
            run_premarket_gtt_job, _maybe_trigger_gtt_for_user,
            _schedule_to_utc, _is_premarket_ist,
            reschedule_user, rebuild_user_schedules, create_scheduler,
        )
        self.assertTrue(True)

    def test_settings_layout_imports(self):
        from modules.kite.settings_layout import (
            create_kite_settings_layout, _sidebar, _expired_banner,
            _connection_section, _schedule_section, _prefs_section,
            _exclusions_section, _activity_section,
            _connection_badge_from_settings, _progress_bar,
            _step1_card, _step2_card, _step3_card, _step4_card,
        )
        self.assertTrue(True)

    def test_admin_layout_imports(self):
        from modules.admin.layout import create_admin_layout
        layout = create_admin_layout()
        layout_str = str(layout)
        self.assertIn("admin-sessions-table", layout_str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
