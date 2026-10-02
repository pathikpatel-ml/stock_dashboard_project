"""
Unit tests for modules/turtle/screener_in_login.py. No live network: a fake session stands in
for screener.in's login + custom-query pages, matching tests/test_nse_shareholding.py's style.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import screener_in_login as sil

LOGIN_PAGE_HTML = '<form><input name="csrfmiddlewaretoken" value="tok123"></form>'
LOGIN_SUCCESS_HTML = '<html><body>Welcome <a href="/logout/">Logout</a></body></html>'
LOGIN_FAILURE_HTML = '<html><body><li class="error">Invalid credentials</li></body></html>'

_HEADER_ROW = (
    "<tr><th>S.No.</th><th>Company</th><th>Mar CapRs.Cr.</th><th>Pledged%</th></tr>"
)


def _page_html(rows, href_suffix="/"):
    """rows: list of (identifier, mcap, pledge_pct). ``identifier`` can be either a numeric BSE
    code or an NSE symbol -- real company-name links use both forms inconsistently (see module
    docstring); ``href_suffix`` lets a test build the "/consolidated/" symbol-style link."""
    trs = "".join(
        f'<tr><td>{i+1}.</td><td><a href="/company/{code}{href_suffix}">Company {code}</a></td>'
        f'<td>{mcap}</td><td>{pledge}</td></tr>'
        for i, (code, mcap, pledge) in enumerate(rows)
    )
    return f"<table>{_HEADER_ROW}<tbody>{trs}</tbody></table>"


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _FakeSession:
    """``query_to_html`` maps a substring that must appear in the request's ``query`` param to
    the HTML to return -- lets tests simulate different responses depending on the cursor
    constraint actually sent, without needing a real URL/query parser."""

    def __init__(self, login_ok=True, query_to_html=None, default_html=None):
        self.login_ok = login_ok
        self.query_to_html = query_to_html or {}
        self.default_html = default_html if default_html is not None else _page_html([])
        self.headers = {}
        self.get_calls = []
        self.post_calls = []

    def get(self, url, timeout=None):
        self.get_calls.append(url)
        if "login" in url:
            return _FakeResponse(text=LOGIN_PAGE_HTML)
        for needle, html in self.query_to_html.items():
            if needle in url:
                return _FakeResponse(text=html)
        return _FakeResponse(text=self.default_html)

    def post(self, url, data=None, timeout=None):
        self.post_calls.append((url, data))
        return _FakeResponse(text=LOGIN_SUCCESS_HTML if self.login_ok else LOGIN_FAILURE_HTML)


def test_login_success():
    session = _FakeSession(login_ok=True)
    assert sil.login(session, "user@example.com", "pw") is True
    assert session.post_calls[0][1]["csrfmiddlewaretoken"] == "tok123"


def test_login_failure():
    session = _FakeSession(login_ok=False)
    assert sil.login(session, "user@example.com", "wrongpw") is False


def test_first_request_has_no_cursor_constraint():
    session = _FakeSession(default_html=_page_html([("500325", 175550.71, 2.70)]))
    sil._fetch_cursor_page(session, None)
    url = session.get_calls[-1]
    query = re.search(r"query=([^&]+)", url).group(1)
    assert "Market+Capitalization+%3C" not in query  # no "< cursor" constraint on the first page


def test_subsequent_request_includes_cursor_constraint():
    session = _FakeSession(default_html=_page_html([]))
    sil._fetch_cursor_page(session, 12345.6)
    url = session.get_calls[-1]
    assert "12345.6" in urllib_unquote(url)


def urllib_unquote(s):
    import urllib.parse
    return urllib.parse.unquote_plus(s)


def test_fetch_cursor_page_returns_pairs_and_next_cursor():
    html = _page_html([("500325", 175550.71, 2.70), ("500180", 106834.45, 0.0)])
    session = _FakeSession(default_html=html)
    pairs, next_cursor = sil._fetch_cursor_page(session, None)
    assert pairs == [("500325", 2.70), ("500180", 0.0)]
    assert next_cursor == 106834.45  # the smallest market cap seen -- next page's cursor


def test_fetch_cursor_page_handles_nse_symbol_style_links():
    # Real bug found live: Reliance Industries -- the FIRST result when sorted by market cap --
    # links as "/company/RELIANCE/consolidated/", not a numeric BSE code. An earlier regex only
    # matched the numeric form and silently dropped every row using this one.
    html = _page_html([("RELIANCE", 1580194.11, 0.0)], href_suffix="/consolidated/")
    session = _FakeSession(default_html=html)
    pairs, next_cursor = sil._fetch_cursor_page(session, None)
    assert pairs == [("RELIANCE", 0.0)]


def test_fetch_cursor_page_handles_mixed_link_formats_on_same_page():
    # Real pages mix both forms -- large/well-known companies by symbol, others by BSE code.
    trs = (
        '<tr><td>1.</td><td><a href="/company/RELIANCE/consolidated/">Reliance</a></td>'
        '<td>1580194.11</td><td>0.00</td></tr>'
        '<tr><td>2.</td><td><a href="/company/523222/">SRM Energy</a></td>'
        '<td>23.74</td><td>0.00</td></tr>'
    )
    html = f"<table>{_HEADER_ROW}<tbody>{trs}</tbody></table>"
    session = _FakeSession(default_html=html)
    pairs, next_cursor = sil._fetch_cursor_page(session, None)
    assert pairs == [("RELIANCE", 0.0), ("523222", 0.0)]


def test_fetch_cursor_page_skips_rows_with_unparseable_values():
    html = """
    <table><tr><th>S.No.</th><th>Company</th><th>Mar CapRs.Cr.</th><th>Pledged%</th></tr>
    <tbody>
      <tr><td>1.</td><td><a href="/company/500325/">RIL</a></td><td>175550.71</td><td>N/A</td></tr>
      <tr><td>2.</td><td><a href="/company/500180/">HDFC Bank</a></td><td>106834.45</td><td>0.00</td></tr>
    </tbody></table>
    """
    session = _FakeSession(default_html=html)
    pairs, next_cursor = sil._fetch_cursor_page(session, None)
    assert pairs == [("500180", 0.0)]
    assert next_cursor == 106834.45  # mcap still tracked even for the row with bad pledge data


def test_fetch_cursor_page_none_when_no_table():
    session = _FakeSession(default_html="<html><body>no table</body></html>")
    pairs, next_cursor = sil._fetch_cursor_page(session, None)
    assert pairs == []
    assert next_cursor is None


def test_fetch_all_pledge_data_single_short_page_stops():
    # Fewer than PAGE_SIZE rows -- the genuine end of the result set.
    html = _page_html([("500325", 175550.71, 2.70), ("500180", 106834.45, 0.0)])
    session = _FakeSession(default_html=html)
    result = sil.fetch_all_pledge_data(session, pause=0)
    assert result == {"500325": 2.70, "500180": 0.0}


def test_fetch_all_pledge_data_walks_cursor_across_pages(monkeypatch):
    monkeypatch.setattr(sil, "PAGE_SIZE", 2)
    page1 = _page_html([("500325", 175550.71, 2.70), ("500180", 106834.45, 0.0)])
    page2 = _page_html([("532667", 50000.0, 59.37)])  # short page -- end of results
    session = _FakeSession(query_to_html={"106834.45": page2}, default_html=page1)
    result = sil.fetch_all_pledge_data(session, pause=0)
    assert result == {"500325": 2.70, "500180": 0.0, "532667": 59.37}


def test_fetch_all_pledge_data_stops_on_empty_or_failed_page():
    session = _FakeSession(default_html="<html><body>no table</body></html>")
    result = sil.fetch_all_pledge_data(session, pause=0)
    assert result == {}


def test_fetch_all_pledge_data_respects_max_iterations_safety_cap(monkeypatch):
    monkeypatch.setattr(sil, "PAGE_SIZE", 1)
    # Every page is exactly a full page (1 row), so without the cap this would loop forever --
    # confirm it stops after exactly max_iterations requests (the fake always returns the same
    # single row regardless of cursor, so the result dict itself can't distinguish iteration
    # count here -- the call count is the real assertion).
    session = _FakeSession(default_html=_page_html([("500325", 100.0, 1.0)]))
    sil.fetch_all_pledge_data(session, max_iterations=3, pause=0)
    assert len(session.get_calls) == 3
