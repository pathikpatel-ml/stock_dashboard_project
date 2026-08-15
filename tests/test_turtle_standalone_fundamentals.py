"""
Unit tests for modules/turtle/standalone_fundamentals.py -- the standalone TTM Net Profit
scraper (screener.in's default, non-consolidated company page).

HTML fixtures below are minimal but structurally faithful to the real page (verified by hand
against real screener.in output for both a regular company and a bank during development):
an <h2>Profit & Loss</h2> inside a <section>, containing a <table> whose header row lists
period labels ending in "TTM", and a "Net Profit+" row. No live network in these tests.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import standalone_fundamentals as sf

REGULAR_COMPANY_HTML = """
<html><body>
<section>
<h2>Quarterly Results</h2>
<table><tr><td>irrelevant</td></tr></table>
</section>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th><th>TTM</th></tr>
<tr><td>Sales+</td><td>382</td><td>477</td><td>703</td><td>702</td></tr>
<tr><td>Net Profit+</td><td>104</td><td>130</td><td>97</td><td>106</td></tr>
<tr><td>EPS in Rs</td><td>16.29</td><td>20.37</td><td>15.23</td><td>16.58</td></tr>
</table>
</section>
</body></html>
"""

BANK_HTML = """
<html><body>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th><th>Mar 2024</th><th>Mar 2025</th><th>Mar 2026</th><th>TTM</th></tr>
<tr><td>Revenue+</td><td>142,891</td><td>163,264</td><td>169,946</td><td>172,670</td></tr>
<tr><td>Net Profit+</td><td>40,888</td><td>47,227</td><td>50,147</td><td>52,183</td></tr>
</table>
</section>
</body></html>
"""

NEGATIVE_PROFIT_HTML = """
<html><body>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th><th>Mar 2025</th><th>TTM</th></tr>
<tr><td>Sales+</td><td>100</td><td>90</td></tr>
<tr><td>Net Profit+</td><td>-4</td><td>-12</td></tr>
</table>
</section>
</body></html>
"""

NO_PL_SECTION_HTML = "<html><body><section><h2>Balance Sheet</h2><table></table></section></body></html>"

NO_TABLE_IN_SECTION_HTML = "<html><body><section><h2>Profit & Loss</h2></section></body></html>"

NO_TTM_COLUMN_HTML = """
<html><body>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr>
<tr><td>Net Profit+</td><td>104</td><td>130</td></tr>
</table>
</section>
</body></html>
"""

NO_NET_PROFIT_ROW_HTML = """
<html><body>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th><th>Mar 2025</th><th>TTM</th></tr>
<tr><td>Sales+</td><td>100</td><td>90</td></tr>
</table>
</section>
</body></html>
"""

EMPTY_TTM_CELL_HTML = """
<html><body>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th><th>Mar 2025</th><th>TTM</th></tr>
<tr><td>Net Profit+</td><td>130</td><td></td></tr>
</table>
</section>
</body></html>
"""


# ---------------------------------------------------------------------------
# parse_ttm_net_profit
# ---------------------------------------------------------------------------
def test_parse_regular_company():
    assert sf.parse_ttm_net_profit(REGULAR_COMPANY_HTML) == 106.0


def test_parse_bank_with_comma_formatted_numbers():
    # Banks use "Revenue+" instead of "Sales+" for the top line -- irrelevant here since we
    # only read the "Net Profit" row, but the comma-formatted numbers ("52,183") must parse.
    assert sf.parse_ttm_net_profit(BANK_HTML) == 52183.0


def test_parse_negative_ttm_profit():
    assert sf.parse_ttm_net_profit(NEGATIVE_PROFIT_HTML) == -12.0


def test_parse_missing_profit_and_loss_section_returns_none():
    assert sf.parse_ttm_net_profit(NO_PL_SECTION_HTML) is None


def test_parse_missing_table_returns_none():
    assert sf.parse_ttm_net_profit(NO_TABLE_IN_SECTION_HTML) is None


def test_parse_missing_ttm_column_returns_none():
    assert sf.parse_ttm_net_profit(NO_TTM_COLUMN_HTML) is None


def test_parse_missing_net_profit_row_returns_none():
    assert sf.parse_ttm_net_profit(NO_NET_PROFIT_ROW_HTML) is None


def test_parse_empty_ttm_cell_returns_none():
    assert sf.parse_ttm_net_profit(EMPTY_TTM_CELL_HTML) is None


def test_parse_garbage_html_never_raises():
    assert sf.parse_ttm_net_profit("<html><body>not a real page</body></html>") is None
    assert sf.parse_ttm_net_profit("") is None


# ---------------------------------------------------------------------------
# fetch_ttm_net_profit -- network layer, stubbed with a fake session
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text
        self.content = text.encode()


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        if self.calls > len(self._responses):
            return self._responses[-1]
        return self._responses[self.calls - 1]

    def close(self):
        pass


def test_fetch_success_first_try():
    session = _FakeSession([_FakeResponse(200, REGULAR_COMPANY_HTML)])
    assert sf.fetch_ttm_net_profit("DEEPINDS", session=session, retries=3, pause=0) == 106.0
    assert session.calls == 1


def test_fetch_retries_then_succeeds():
    session = _FakeSession([_FakeResponse(503, ""), _FakeResponse(200, REGULAR_COMPANY_HTML)])
    assert sf.fetch_ttm_net_profit("DEEPINDS", session=session, retries=3, pause=0) == 106.0
    assert session.calls == 2


def test_fetch_gives_up_after_retries_exhausted():
    session = _FakeSession([_FakeResponse(503, "")])
    assert sf.fetch_ttm_net_profit("DEEPINDS", session=session, retries=2, pause=0) is None
    assert session.calls == 2


def test_fetch_page_loads_but_no_data_does_not_retry():
    # 200 OK but the page structure doesn't match (e.g. a delisted/unusual security) --
    # retrying won't fix a structural mismatch, so this should return immediately.
    session = _FakeSession([_FakeResponse(200, NO_PL_SECTION_HTML)])
    assert sf.fetch_ttm_net_profit("WEIRDCO", session=session, retries=3, pause=0) is None
    assert session.calls == 1


def test_fetch_network_exception_is_caught_and_retried():
    class _RaisingSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("simulated")
            return _FakeResponse(200, REGULAR_COMPANY_HTML)

        def close(self):
            pass

    session = _RaisingSession()
    assert sf.fetch_ttm_net_profit("DEEPINDS", session=session, retries=3, pause=0) == 106.0
    assert session.calls == 2


# ---------------------------------------------------------------------------
# parse_profit_and_loss -- full TTM + annual series for both Net Profit and Sales/Revenue
# ---------------------------------------------------------------------------
def test_parse_pl_regular_company():
    result = sf.parse_profit_and_loss(REGULAR_COMPANY_HTML)
    assert result == {
        "ttm_net_profit": 106.0,
        "annual_net_profit": [104.0, 130.0, 97.0],
        "ttm_net_sales": 702.0,
        "annual_net_sales": [382.0, 477.0, 703.0],
    }


def test_parse_pl_bank_uses_revenue_label_and_comma_numbers():
    result = sf.parse_profit_and_loss(BANK_HTML)
    assert result == {
        "ttm_net_profit": 52183.0,
        "annual_net_profit": [40888.0, 47227.0, 50147.0],
        "ttm_net_sales": 172670.0,
        "annual_net_sales": [142891.0, 163264.0, 169946.0],
    }


def test_parse_pl_missing_section_returns_none():
    assert sf.parse_profit_and_loss(NO_PL_SECTION_HTML) is None


def test_parse_pl_missing_table_returns_none():
    assert sf.parse_profit_and_loss(NO_TABLE_IN_SECTION_HTML) is None


def test_parse_pl_no_ttm_column_degrades_ttm_to_none_keeps_annual():
    result = sf.parse_profit_and_loss(NO_TTM_COLUMN_HTML)
    assert result["ttm_net_profit"] is None
    assert result["annual_net_profit"] == [104.0, 130.0]
    assert result["ttm_net_sales"] is None
    assert result["annual_net_sales"] == []


def test_parse_pl_no_net_profit_row_degrades_profit_only():
    result = sf.parse_profit_and_loss(NO_NET_PROFIT_ROW_HTML)
    assert result["ttm_net_profit"] is None
    assert result["annual_net_profit"] == []
    assert result["ttm_net_sales"] == 90.0
    assert result["annual_net_sales"] == [100.0]


def test_parse_pl_empty_ttm_cell_returns_none_for_that_field():
    result = sf.parse_profit_and_loss(EMPTY_TTM_CELL_HTML)
    assert result["ttm_net_profit"] is None
    assert result["annual_net_profit"] == [130.0]


def test_parse_pl_garbage_html_never_raises():
    assert sf.parse_profit_and_loss("<html><body>not a real page</body></html>") is None
    assert sf.parse_profit_and_loss("") is None


# ---------------------------------------------------------------------------
# resolve_screener_slug / fetch_profit_and_loss -- search-API slug fallback, no live network
# ---------------------------------------------------------------------------
class _FakeJsonResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else []

    def json(self):
        return self._json_data


class _FakeMultiUrlSession:
    """Routes .get(url, ...) to a canned response by URL prefix -- lets a single fake session
    stand in for both company-page and search-API calls in one fetch_profit_and_loss run."""
    def __init__(self, url_responses):
        self._url_responses = url_responses
        self.requests = []

    def get(self, url, timeout=None, params=None):
        self.requests.append((url, params))
        for prefix, resp in self._url_responses.items():
            if url.startswith(prefix):
                return resp
        raise AssertionError(f"Unexpected URL in test: {url}")

    def close(self):
        pass


def test_resolve_screener_slug_parses_slug_from_search_result():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/api/company/search/": _FakeJsonResponse(
            200, [{"id": 1274894, "name": "Eternal Ltd", "url": "/company/ETERNAL/consolidated/"}]
        ),
    })
    assert sf.resolve_screener_slug("ZOMATO", session=session) == "ETERNAL"


def test_resolve_screener_slug_empty_results_returns_none():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/api/company/search/": _FakeJsonResponse(200, []),
    })
    assert sf.resolve_screener_slug("NOTAREALTICKER", session=session) is None


def test_resolve_screener_slug_non_200_returns_none():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/api/company/search/": _FakeJsonResponse(503, []),
    })
    assert sf.resolve_screener_slug("X", session=session) is None


def test_fetch_pl_direct_symbol_success_never_calls_search():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/RELIANCE/": _FakeResponse(200, REGULAR_COMPANY_HTML),
    })
    result = sf.fetch_profit_and_loss("RELIANCE", session=session, retries=2, pause=0)
    assert result["ttm_net_profit"] == 106.0
    assert not any("search" in url for url, _ in session.requests)


def test_fetch_pl_falls_back_to_search_resolved_slug():
    # ZOMATO's direct page has no usable P&L data (simulates a renamed/delisted-old-symbol
    # page) -- must fall back to the search API, resolve ETERNAL, and retry against that.
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/ZOMATO/": _FakeResponse(200, NO_PL_SECTION_HTML),
        "https://www.screener.in/api/company/search/": _FakeJsonResponse(
            200, [{"id": 1274894, "name": "Eternal Ltd", "url": "/company/ETERNAL/consolidated/"}]
        ),
        "https://www.screener.in/company/ETERNAL/": _FakeResponse(200, REGULAR_COMPANY_HTML),
    })
    result = sf.fetch_profit_and_loss("ZOMATO", session=session, retries=2, pause=0)
    assert result["ttm_net_profit"] == 106.0


def test_fetch_pl_returns_none_when_direct_and_fallback_both_fail():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/FAKESYM/": _FakeResponse(200, NO_PL_SECTION_HTML),
        "https://www.screener.in/api/company/search/": _FakeJsonResponse(200, []),
    })
    assert sf.fetch_profit_and_loss("FAKESYM", session=session, retries=1, pause=0) is None


def test_fetch_pl_search_fallback_disabled_skips_search_call():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/FAKESYM/": _FakeResponse(200, NO_PL_SECTION_HTML),
    })
    result = sf.fetch_profit_and_loss(
        "FAKESYM", session=session, retries=1, pause=0, use_search_fallback=False
    )
    assert result is None
    assert not any("search" in url for url, _ in session.requests)
