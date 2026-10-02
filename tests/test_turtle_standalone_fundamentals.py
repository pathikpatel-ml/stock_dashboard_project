"""
Unit tests for modules/turtle/standalone_fundamentals.py -- the TTM Net Profit scraper
(screener.in's ``/consolidated/`` company page; module name is historical).

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

# A company with no subsidiaries still returns 200 OK for its /consolidated/ URL -- screener.in
# renders the full row-label shell but every data cell is empty (nothing to consolidate).
# Verified live against the real ABBOTINDIA page during development.
EMPTY_CONSOLIDATED_HTML = """
<html><body>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th></tr>
<tr><td>Sales+</td></tr>
<tr><td>Net Profit+</td></tr>
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


# ---------------------------------------------------------------------------
# _has_usable_data / consolidated-empty-shell -> standalone fallback (2026-08-19)
# ---------------------------------------------------------------------------
def test_has_usable_data_true_when_ttm_profit_present():
    assert sf._has_usable_data({"ttm_net_profit": 10.0, "ttm_net_sales": None,
                                 "annual_net_profit": [], "annual_net_sales": []}) is True


def test_has_usable_data_true_when_only_ttm_sales_present():
    assert sf._has_usable_data({"ttm_net_profit": None, "ttm_net_sales": 10.0,
                                 "annual_net_profit": [], "annual_net_sales": []}) is True


def test_has_usable_data_false_when_all_fields_empty():
    assert sf._has_usable_data({"ttm_net_profit": None, "ttm_net_sales": None,
                                 "annual_net_profit": [], "annual_net_sales": []}) is False


def test_has_usable_data_false_for_none_or_empty():
    assert sf._has_usable_data(None) is False
    assert sf._has_usable_data({}) is False


def test_fetch_pl_falls_back_from_empty_consolidated_shell_to_standalone():
    # A company with no subsidiaries (e.g. real ABBOTINDIA) -- /consolidated/ loads fine (200)
    # but has an empty data shell; must fall back to that SAME slug's standalone URL rather
    # than treating the empty shell as "success" or jumping straight to the search API.
    # Insertion order matters here: the /consolidated/ key must be checked before the shorter
    # standalone key, since the standalone URL is itself a string-prefix of the consolidated
    # one (see _FakeMultiUrlSession's startswith routing).
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/ABBOTINDIA/consolidated/": _FakeResponse(200, EMPTY_CONSOLIDATED_HTML),
        "https://www.screener.in/company/ABBOTINDIA/": _FakeResponse(200, REGULAR_COMPANY_HTML),
    })
    result = sf.fetch_profit_and_loss(
        "ABBOTINDIA", session=session, retries=1, pause=0, use_search_fallback=False
    )
    assert result["ttm_net_profit"] == 106.0
    assert not any("search" in url for url, _ in session.requests)


# ---------------------------------------------------------------------------
# parse_sector_classification / fetch_profit_and_loss sector merge (2026-09)
# ---------------------------------------------------------------------------
PEER_COMPARISON_HTML = """
<html><body>
<p class="sub">
  <a href="/market/IN03/" title="Broad Sector">Energy</a>
  <a href="/market/IN03/IN0301/" title="Sector">Oil, Gas &amp; Consumable Fuels</a>
  <a href="/market/IN03/IN0301/IN030103/" title="Broad Industry">Petroleum Products</a>
  <a href="/market/IN03/IN0301/IN030103/IN030103001/" title="Industry">Refineries &amp; Marketing</a>
</p>
</body></html>
"""

REGULAR_COMPANY_WITH_SECTOR_HTML = REGULAR_COMPANY_HTML.replace("</body>", PEER_COMPARISON_HTML + "</body>")


def test_parse_sector_classification_all_four_tiers():
    assert sf.parse_sector_classification(PEER_COMPARISON_HTML) == {
        "broad_sector": "Energy",
        "sector": "Oil, Gas & Consumable Fuels",
        "broad_industry": "Petroleum Products",
        "industry": "Refineries & Marketing",
    }


def test_parse_sector_classification_missing_returns_none():
    assert sf.parse_sector_classification(REGULAR_COMPANY_HTML) is None
    assert sf.parse_sector_classification("") is None
    assert sf.parse_sector_classification("<html><body>not a real page</body></html>") is None


def test_fetch_pl_merges_sector_classification_from_same_page():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/RELIANCE/": _FakeResponse(200, REGULAR_COMPANY_WITH_SECTOR_HTML),
    })
    result = sf.fetch_profit_and_loss("RELIANCE", session=session, retries=2, pause=0)
    assert result["ttm_net_profit"] == 106.0
    assert result["broad_sector"] == "Energy"
    assert result["sector"] == "Oil, Gas & Consumable Fuels"
    assert result["broad_industry"] == "Petroleum Products"
    assert result["industry"] == "Refineries & Marketing"


def test_fetch_pl_returns_sector_only_when_no_usable_financials_anywhere():
    # No usable P&L on any candidate/URL, but a sector classification was found along the way --
    # should still return that, not None, so a company's sector isn't lost just because its
    # financials page happened to be an empty shell.
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/FAKESYM/": _FakeResponse(
            200, NO_PL_SECTION_HTML.replace("</body>", PEER_COMPARISON_HTML + "</body>")
        ),
        "https://www.screener.in/api/company/search/": _FakeJsonResponse(200, []),
    })
    result = sf.fetch_profit_and_loss("FAKESYM", session=session, retries=1, pause=0)
    assert result["ttm_net_profit"] is None
    assert result["broad_sector"] == "Energy"


def test_fetch_pl_returns_none_when_no_financials_and_no_sector():
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/FAKESYM/": _FakeResponse(200, NO_PL_SECTION_HTML),
        "https://www.screener.in/api/company/search/": _FakeJsonResponse(200, []),
    })
    assert sf.fetch_profit_and_loss("FAKESYM", session=session, retries=1, pause=0) is None


def test_fetch_pl_prefers_real_consolidated_data_when_available():
    # The opposite case: a company that DOES have real consolidated data must use it, not
    # fall through to standalone -- the standalone mock is deliberately a different (wrong)
    # fixture here, so the test fails loudly if the fallback fires when it shouldn't.
    session = _FakeMultiUrlSession({
        "https://www.screener.in/company/RELIANCE/consolidated/": _FakeResponse(200, REGULAR_COMPANY_HTML),
        "https://www.screener.in/company/RELIANCE/": _FakeResponse(200, BANK_HTML),
    })
    result = sf.fetch_profit_and_loss(
        "RELIANCE", session=session, retries=1, pause=0, use_search_fallback=False
    )
    assert result["ttm_net_profit"] == 106.0  # REGULAR_COMPANY_HTML's value, not BANK_HTML's


# ---------------------------------------------------------------------------
# Balance Sheet / Ratios / Cash Flows / promoter holding history (2026-10-01, quality flags)
# ---------------------------------------------------------------------------
BALANCE_SHEET_HTML = """
<html><body>
<section>
<h2>Balance Sheet</h2>
<table>
<tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th></tr>
<tr><td>Equity Capital</td><td>100</td><td>100</td><td>100</td></tr>
<tr><td>Reserves</td><td>5000</td><td>5500</td><td>6000</td></tr>
<tr><td>Total Liabilities</td><td>10000</td><td>11000</td><td>12000</td></tr>
</table>
</section>
</body></html>
"""

RATIOS_HTML = """
<html><body>
<section>
<h2>Ratios</h2>
<table>
<tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th></tr>
<tr><td>Debtor Days</td><td>30</td><td>28</td><td>25</td></tr>
<tr><td>ROCE %</td><td>9%</td><td>10%</td><td>11%</td></tr>
</table>
</section>
</body></html>
"""

CASH_FLOW_HTML = """
<html><body>
<section>
<h2>Cash Flows</h2>
<table>
<tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th></tr>
<tr><td>Cash from Operating Activity+</td><td>800</td><td>900</td><td>1000</td></tr>
<tr><td>Net Cash Flow</td><td>50</td><td>60</td><td>70</td></tr>
</table>
</section>
</body></html>
"""

PL_EXTRA_HTML = """
<html><body>
<section>
<h2>Profit & Loss</h2>
<table>
<tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th><th>TTM</th></tr>
<tr><td>Sales+</td><td>1500</td><td>1700</td><td>1900</td><td>1950</td></tr>
<tr><td>Other Income+</td><td>80</td><td>90</td><td>100</td><td>105</td></tr>
<tr><td>Interest</td><td>50</td><td>60</td><td>70</td><td>75</td></tr>
<tr><td>Profit before tax</td><td>300</td><td>350</td><td>400</td><td>410</td></tr>
<tr><td>Net Profit+</td><td>200</td><td>230</td><td>260</td><td>270</td></tr>
<tr><td>EPS in Rs</td><td>20</td><td>23</td><td>26</td><td>27</td></tr>
</table>
</section>
</body></html>
"""

PROMOTER_HOLDING_HTML = """
<html><body>
<section>
<h2>Shareholding Pattern</h2>
<table>
<tr><th></th><th>Sep 2024</th><th>Dec 2024</th><th>Mar 2025</th></tr>
<tr><td><button>Promoters&nbsp;<span class="blue-icon">+</span></button></td><td>45.00%</td><td>45.50%</td><td>46.00%</td></tr>
<tr><td>Public+</td><td>55.00%</td><td>54.50%</td><td>54.00%</td></tr>
</table>
</section>
</body></html>
"""


def test_parse_balance_sheet_history_excludes_ttm_not_present_and_aligns_periods():
    result = sf.parse_balance_sheet_history(BALANCE_SHEET_HTML)
    assert result["equity_capital"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [100.0, 100.0, 100.0])
    assert result["reserves"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [5000.0, 5500.0, 6000.0])


def test_parse_balance_sheet_history_missing_section_returns_none():
    assert sf.parse_balance_sheet_history("<html><body>not a real page</body></html>") is None


def test_parse_balance_sheet_history_found_but_empty_degrades_gracefully():
    # The section heading exists but the table has no matching rows -- degrades to None values
    # per-key, not an overall None (mirrors parse_profit_and_loss's row-missing behaviour).
    html = "<html><body><section><h2>Balance Sheet</h2><table></table></section></body></html>"
    result = sf.parse_balance_sheet_history(html)
    assert result == {"equity_capital": None, "reserves": None}


def test_parse_ratios_history_strips_percent_sign():
    result = sf.parse_ratios_history(RATIOS_HTML)
    assert result["roce_pct"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [9.0, 10.0, 11.0])


def test_parse_ratios_history_missing_roce_row_returns_none():
    html = "<html><body><section><h2>Ratios</h2><table><tr><td>Debtor Days</td></tr></table></section></body></html>"
    assert sf.parse_ratios_history(html) is None


def test_parse_cash_flow_history_strips_plus_suffix():
    result = sf.parse_cash_flow_history(CASH_FLOW_HTML)
    assert result["cfo"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [800.0, 900.0, 1000.0])


def test_parse_pl_history_extra_excludes_ttm_and_gets_all_rows():
    result = sf.parse_pl_history_extra(PL_EXTRA_HTML)
    assert result["interest"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [50.0, 60.0, 70.0])
    assert result["profit_before_tax"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [300.0, 350.0, 400.0])
    assert result["eps"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [20.0, 23.0, 26.0])
    assert result["sales"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [1500.0, 1700.0, 1900.0])
    assert result["net_profit"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [200.0, 230.0, 260.0])
    assert result["other_income"] == (["Mar 2023", "Mar 2024", "Mar 2025"], [80.0, 90.0, 100.0])


def test_parse_pl_history_extra_missing_section_returns_none():
    assert sf.parse_pl_history_extra(NO_PL_SECTION_HTML) is None


def test_parse_promoter_holding_history_handles_button_label_and_percent():
    result = sf.parse_promoter_holding_history(PROMOTER_HOLDING_HTML)
    assert result["promoter_pct"] == (["Sep 2024", "Dec 2024", "Mar 2025"], [45.0, 45.5, 46.0])


def test_parse_promoter_holding_history_missing_section_returns_none():
    assert sf.parse_promoter_holding_history(NO_PL_SECTION_HTML) is None
