"""
Unit tests for turtle_fundamentals_watchdog.py (2026-11-09) -- the hourly monitor/retrigger
script. modules.turtle.slice_status's own decision logic is tested separately in
test_turtle_slice_status.py; these tests cover this script's own glue: reading status, calling
the decision function, dispatching (or not), and exit codes. requests.post and
modules.turtle.slice_status are both stubbed -- no live network/DB.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import turtle_fundamentals_watchdog as wd


# ---------------------------------------------------------------------------
# trigger_workflow_dispatch
# ---------------------------------------------------------------------------
def test_trigger_workflow_dispatch_success(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 204
        text = ""

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(wd.requests, "post", fake_post)

    assert wd.trigger_workflow_dispatch(3, token="tok", repo="owner/repo") is True
    assert captured["url"] == "https://api.github.com/repos/owner/repo/actions/workflows/turtle_fundamentals.yml/dispatches"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["json"] == {"ref": "main", "inputs": {"day_of_week": "3"}}


def test_trigger_workflow_dispatch_non_204_returns_false(monkeypatch):
    class _Resp:
        status_code = 422
        text = "Unprocessable"

    monkeypatch.setattr(wd.requests, "post", lambda *a, **k: _Resp())
    assert wd.trigger_workflow_dispatch(3, token="tok", repo="owner/repo") is False


def test_trigger_workflow_dispatch_exception_returns_false(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(wd.requests, "post", boom)
    assert wd.trigger_workflow_dispatch(3, token="tok", repo="owner/repo") is False


# ---------------------------------------------------------------------------
# main() -- glue: read status -> decide -> dispatch (or not)
# ---------------------------------------------------------------------------
def test_main_nothing_to_trigger_does_not_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(wd.slice_status, "read_all_slice_status", lambda: {})
    monkeypatch.setattr(wd.slice_status, "decide_slices_to_trigger", lambda now, rows: [])
    calls = []
    monkeypatch.setattr(wd, "trigger_workflow_dispatch", lambda *a, **k: calls.append(a))

    monkeypatch.setattr(sys, "argv", ["turtle_fundamentals_watchdog.py"])
    wd.main()  # should return normally, no sys.exit

    assert calls == []
    assert "Nothing overdue" in capsys.readouterr().out


def test_main_dry_run_logs_but_does_not_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(wd.slice_status, "read_all_slice_status", lambda: {})
    monkeypatch.setattr(wd.slice_status, "decide_slices_to_trigger", lambda now, rows: [2, 4])
    calls = []
    monkeypatch.setattr(wd, "trigger_workflow_dispatch", lambda *a, **k: calls.append(a))

    monkeypatch.setattr(sys, "argv", ["turtle_fundamentals_watchdog.py", "--dry-run"])
    wd.main()

    assert calls == []
    out = capsys.readouterr().out
    assert "[2, 4]" in out
    assert "not actually dispatching" in out


def test_main_missing_token_exits_1(monkeypatch):
    monkeypatch.setattr(wd.slice_status, "read_all_slice_status", lambda: {})
    monkeypatch.setattr(wd.slice_status, "decide_slices_to_trigger", lambda now, rows: [0])
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    monkeypatch.setattr(sys, "argv", ["turtle_fundamentals_watchdog.py"])
    with pytest.raises(SystemExit) as exc:
        wd.main()
    assert exc.value.code == 1


def test_main_dispatches_each_overdue_slice_and_exits_0_on_success(monkeypatch):
    monkeypatch.setattr(wd.slice_status, "read_all_slice_status", lambda: {})
    monkeypatch.setattr(wd.slice_status, "decide_slices_to_trigger", lambda now, rows: [1, 5])
    dispatched = []

    def fake_trigger(day_of_week, token, repo):
        dispatched.append(day_of_week)
        return True

    monkeypatch.setattr(wd, "trigger_workflow_dispatch", fake_trigger)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    monkeypatch.setattr(sys, "argv", ["turtle_fundamentals_watchdog.py"])
    with pytest.raises(SystemExit) as exc:
        wd.main()

    assert exc.value.code == 0
    assert dispatched == [1, 5]


def test_main_exits_1_if_any_dispatch_fails(monkeypatch):
    monkeypatch.setattr(wd.slice_status, "read_all_slice_status", lambda: {})
    monkeypatch.setattr(wd.slice_status, "decide_slices_to_trigger", lambda now, rows: [1, 5])

    def fake_trigger(day_of_week, token, repo):
        return day_of_week != 5  # slice 5's dispatch fails

    monkeypatch.setattr(wd, "trigger_workflow_dispatch", fake_trigger)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    monkeypatch.setattr(sys, "argv", ["turtle_fundamentals_watchdog.py"])
    with pytest.raises(SystemExit) as exc:
        wd.main()

    assert exc.value.code == 1
