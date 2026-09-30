"""
Unit tests for modules/turtlequant/stock_analysis.py -- prompt building (pure) and the
OpenRouter call wrapper (requests.post mocked, no live network/API cost).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtlequant import stock_analysis as sa


# ---------------------------------------------------------------------------
# Prompt building -- pure, no I/O
# ---------------------------------------------------------------------------
def test_build_management_prompt_fills_placeholder_and_keeps_verbatim_structure():
    prompt = sa.build_management_prompt("Reliance Industries (NSE: RELIANCE)")
    assert "Reliance Industries (NSE: RELIANCE)" in prompt
    assert "PART A - PROMISE VS DELIVERY" in prompt
    assert "PART B - LEGAL / FRAUD / REGULATORY RED FLAGS" in prompt
    assert "PART C - CEO / MD / PROMOTER TRACK RECORD" in prompt
    assert "AVOID" in prompt
    assert "[COMPANY NAME]" not in prompt  # placeholder actually replaced, not left literal


def test_build_business_prompt_fills_placeholder_and_keeps_verbatim_structure():
    prompt = sa.build_business_prompt("TCS (NSE: TCS)")
    assert "TCS (NSE: TCS)" in prompt
    assert "1. WHAT IT DOES" in prompt
    assert "3. MOAT AND PRICING POWER" in prompt
    assert "6. FUTURE GROWTH" in prompt
    assert "[TICKER]" not in prompt


def test_build_price_prompt_includes_both_prior_reports_as_reference():
    prompt = sa.build_price_prompt(
        "HDFC Bank (NSE: HDFCBANK)",
        management_report="MGMT REPORT UNIQUE MARKER 123",
        business_report="BIZ REPORT UNIQUE MARKER 456",
    )
    assert "HDFC Bank (NSE: HDFCBANK)" in prompt
    assert "MGMT REPORT UNIQUE MARKER 123" in prompt
    assert "BIZ REPORT UNIQUE MARKER 456" in prompt
    assert "=== MANAGEMENT QUALITY REPORT" in prompt
    assert "=== BUSINESS QUALITY REPORT" in prompt
    assert "margin of safety" in prompt


# ---------------------------------------------------------------------------
# _call_openrouter -- requests.post mocked
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_call_openrouter_extracts_content_and_citations(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(200, {
            "choices": [{"message": {"content": "the report text"}}],
            "citations": ["https://source-a.com", "https://source-b.com"],
        })

    monkeypatch.setattr(sa.requests, "post", fake_post)

    content, citations = sa._call_openrouter("a prompt", model="perplexity/sonar-pro")

    assert content == "the report text"
    assert citations == ["https://source-a.com", "https://source-b.com"]
    assert captured["url"] == sa._OPENROUTER_URL
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["json"]["model"] == "perplexity/sonar-pro"
    assert captured["json"]["messages"] == [{"role": "user", "content": "a prompt"}]


def test_call_openrouter_missing_citations_returns_empty_list(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(sa.requests, "post", lambda *a, **k: _FakeResponse(
        200, {"choices": [{"message": {"content": "text"}}]}
    ))
    content, citations = sa._call_openrouter("prompt")
    assert content == "text"
    assert citations == []


def test_call_openrouter_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        sa._call_openrouter("prompt")


def test_call_openrouter_raises_on_no_choices(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(sa.requests, "post", lambda *a, **k: _FakeResponse(200, {"choices": []}))
    with pytest.raises(RuntimeError, match="no choices"):
        sa._call_openrouter("prompt")


def test_call_openrouter_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setattr(sa.requests, "post", lambda *a, **k: _FakeResponse(500, {}))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        sa._call_openrouter("prompt")


# ---------------------------------------------------------------------------
# run_full_analysis -- the thread target; must never raise uncaught, always reaches
# analysis_store.mark_done or mark_error
# ---------------------------------------------------------------------------
def test_run_full_analysis_happy_path_calls_all_three_stages_and_marks_done(monkeypatch):
    calls = []
    monkeypatch.setattr(sa, "_call_openrouter", lambda prompt, **k: (f"report for: {prompt[:20]}", ["cite"]))
    monkeypatch.setattr(sa.analysis_store, "save_stage", lambda *a, **k: calls.append(("save_stage", a[1])))
    monkeypatch.setattr(sa.analysis_store, "mark_done", lambda symbol: calls.append(("mark_done", symbol)))
    monkeypatch.setattr(sa.analysis_store, "mark_error", lambda *a, **k: calls.append(("mark_error", a)))

    sa.run_full_analysis("RELIANCE", "Reliance Industries")

    stages = [c[1] for c in calls if c[0] == "save_stage"]
    assert stages == ["management_report", "business_report", "price_report"]
    assert ("mark_done", "RELIANCE") in calls
    assert not any(c[0] == "mark_error" for c in calls)


def test_run_full_analysis_never_raises_and_marks_error_on_failure(monkeypatch):
    def _boom(prompt, **k):
        raise RuntimeError("simulated OpenRouter failure")

    errors = []
    monkeypatch.setattr(sa, "_call_openrouter", _boom)
    monkeypatch.setattr(sa.analysis_store, "mark_error", lambda symbol, msg: errors.append((symbol, msg)))
    monkeypatch.setattr(sa.analysis_store, "mark_done", lambda symbol: pytest.fail("should not reach mark_done"))

    sa.run_full_analysis("TCS", "Tata Consultancy Services")  # must not raise

    assert errors == [("TCS", "simulated OpenRouter failure")]
