"""
Shared hard-timeout wrapper for requests.Session.get() calls in the Turtle Strategy pipeline.

requests' own ``timeout=`` parameter only bounds gaps between received bytes, not total
request duration -- a server that trickles back even a little data periodically keeps
resetting that inactivity clock forever, so the request never raises and never returns.
Confirmed live (2026-10-11): a screener.in/NSE request got stuck exactly this way and froze a
full-universe batch run for ~19 hours straight (both on GitHub Actions and run locally,
ruling out a runner-specific network issue), well past its own ``timeout=20``. Mirrors the
background-thread-plus-hard-join pattern already used for yfinance calls in
modules/breakout/data_feed.py -- a stuck request is abandoned (Python can't force-kill a
thread) rather than allowed to block the caller indefinitely.
"""
from __future__ import annotations

import threading
from typing import Optional

import requests

HARD_TIMEOUT_SECONDS = 30


def get_with_hard_timeout(
    session: requests.Session, url: str, params: Optional[dict] = None,
    timeout: int = 20, hard_timeout: float = HARD_TIMEOUT_SECONDS,
) -> Optional[requests.Response]:
    """``session.get(url, params=params, timeout=timeout)``, run on a background daemon thread
    so a stuck request can never block the caller for more than ``hard_timeout`` seconds.
    Returns None on ANY failure -- a real exception, or the hard-timeout ceiling being hit --
    the same contract every caller already treats a network failure with."""
    result_holder: dict = {}

    def _do_get():
        try:
            # Only pass params= when actually given -- keeps the call shape identical to a
            # plain session.get(url, timeout=...) for the common (no-params) case, matching
            # what every existing caller/test mock already expects.
            kwargs = {"timeout": timeout}
            if params is not None:
                kwargs["params"] = params
            result_holder["resp"] = session.get(url, **kwargs)
        except Exception:
            result_holder["resp"] = None

    thread = threading.Thread(target=_do_get, daemon=True)
    thread.start()
    thread.join(timeout=hard_timeout)
    if thread.is_alive():
        return None  # still running -- abandon it (daemon thread), treat as unavailable
    return result_holder.get("resp")
