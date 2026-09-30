"""
Per-stock LLM deep-research for the Turtle Quant tab's admin-only "Analyze" button.

Three sequential studies -- Management Quality, Business Quality, Price & Final Decision --
using the user's own verbatim prompt text (2026-09-30). Report 3 explicitly depends on reports
1 and 2's actual findings ("Using the findings from the management and business studies..."),
so it's built by appending both prior reports' full text as reference material in its own
prompt -- NOT a multi-turn conversation (OpenRouter's chat/completions is stateless per call, so
a multi-turn thread would just resend the same text anyway), and NOT as assistant-role turns
(that risks the model treating prior reports as its own draft to revise rather than material to
synthesize against).

Model: STOCK_ANALYSIS_MODEL, default "openrouter/free" (2026-10-01, the account has no paid
credit -- see .env.example for the real trade-off this means: free-tier models are weaker and
typically don't do real web search grounding, so citations will usually come back empty and
claims are less reliably sourced than a paid, search-capable model like perplexity/sonar-pro
would give for this "cite every claim" style of prompt. Originally built against sonar-pro,
switched after confirming live the account is free-tier only (OpenRouter's /auth/key endpoint:
is_free_tier=true) -- swap STOCK_ANALYSIS_MODEL back once the account has credit.

No LangChain/LangGraph -- plain ``requests`` (already a dependency) against OpenRouter's
OpenAI-compatible endpoint.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from . import analysis_store

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "openrouter/free"


def current_model() -> str:
    """The model STOCK_ANALYSIS_MODEL currently resolves to -- shared by _call_openrouter's
    default and by callers (callbacks.py's start-analysis handler) that need to record, up
    front, exactly which model a run will use (see analysis_store.start_analysis's ``model``
    param -- recorded per-row so the UI's fabrication-risk warning stays accurate even after
    this setting is later changed)."""
    return os.environ.get("STOCK_ANALYSIS_MODEL", _DEFAULT_MODEL)


def _call_openrouter(prompt: str, model: Optional[str] = None, timeout: int = 150) -> tuple[str, list]:
    """One OpenRouter chat/completions call. Returns (content, citations) -- Perplexity's
    citations live in a top-level ``citations`` field on the response, NOT inside
    ``choices[0].message.content``, so they're extracted separately here or the sourcing would
    silently be lost. Raises on any failure (network, timeout, non-200, malformed response) --
    callers (run_full_analysis) are responsible for catching this and calling
    analysis_store.mark_error, never let it propagate uncaught out of a background thread.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set.")
    model = model or current_model()

    resp = requests.post(
        _OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {data}")
    content = choices[0].get("message", {}).get("content", "")
    citations = data.get("citations") or []
    return content, citations


def build_management_prompt(company_ticker: str) -> str:
    return f"""Act as a forensic equity analyst who values honesty over optimism. Study the
management of {company_ticker}. Use only primary or
verifiable sources: BSE/NSE filings, concall transcripts, annual reports,
SEBI/MCA/court records, and credible news. Cite the source and date for every
claim. If you cannot find or verify something, write "NOT FOUND", never guess.
Separate proven findings from mere allegations.

PART A - PROMISE VS DELIVERY (concalls)
Read the last 3 concalls at minimum, ideally the last 8-12 quarters, plus the
annual report chairman/MD letters. Build a table:
Date | What management promised (revenue, margin, capex, debt, new product,
capacity, timeline) | Actual result | Status (Delivered / Partly / Missed /
Went quiet) | Any excuse given.
Then answer: Do they set achievable targets or keep moving the goalposts? Do
they answer hard questions directly or dodge them? Do they admit mistakes? Do
they change the story every year? Give an overall Promise-Kept %.

PART B - LEGAL / FRAUD / REGULATORY RED FLAGS
Search for and list, with dates and status: SEBI orders or show-cause notices;
NSE/BSE penalties or delayed filings; ED, CBI, Income Tax, GST, DRI or customs
cases; MCA/NCLT/NCLAT cases; High Court/Supreme Court cases against the
company, promoters or directors; disqualified directors; auditor resignation,
qualified opinion or "emphasis of matter"; restated financials; whistleblower
complaints; short-seller or forensic reports; rating downgrades; promoter
pledge; promoter selling; related-party transactions or loans to promoter
entities; unusual CFO/CFS/auditor churn; delayed results.
Rate each finding: Low / Medium / Severe. Any confirmed fraud or serious
governance finding means stop and say "AVOID".

PART C - CEO / MD / PROMOTER TRACK RECORD
For the CEO, MD and key promoters: age, tenure, education, past companies and
roles, and how those companies performed while they were in charge (growth,
ROCE, debt, fate of shareholders). Any past failures, exits or controversies?
Also cover: capital allocation record (acquisitions, capex, dividends,
buybacks; did they create value or waste it?), salary versus profit,
insider buying and selling, promoter holding trend, succession plan, and
dependence on a single person.

OUTPUT
1. One-page scorecard, 0-10 each: Honesty/transparency, Promise-keeping,
Capital allocation, Track record, Governance/legal cleanliness, Alignment
with minority shareholders.
2. Top 5 red flags and top 5 positives, each with source.
3. Verdict: Trustworthy / Acceptable with watch-points / Avoid, and the single
fact that would most change your view."""


def build_business_prompt(company_ticker: str) -> str:
    return f"""Act as a long-term business analyst in the style of Buffett, Fisher and
Raamdeo Agrawal. Study the business of {company_ticker}. Use the
last 10 years of financials, annual reports and the last 8-12 concall
transcripts. Cite sources and dates. Write "NOT FOUND" instead of guessing,
and separate facts from your opinion.

1. WHAT IT DOES
Sector and industry. Products/services in plain language. Revenue split by
product, segment and geography. Who pays the company, and why they buy.
Is the product a must-have or nice-to-have? One-time or repeat purchase?

2. INDUSTRY
Market size, growth rate, cyclicality, competition, the company's market share
and whether it is rising or falling, regulation, and disruption risk.

3. MOAT AND PRICING POWER
Can it raise prices above inflation without losing customers? Test with numbers:
gross and operating margin stability over 10 years, ROCE (is it above 15-20%
for years?), margins versus peers, market-share trend. Name the moat source
(brand, switching cost, scale/cost advantage, licence, patent, distribution,
network effect), or say plainly that there is none.

4. SUPPLIERS AND CUSTOMERS
Top suppliers and raw-material dependence, and whether cost increases can be
passed on. Top 5/top 10 customer share of revenue, contract terms,
customer bargaining power, and how easily customers can switch. Include
payable days and receivable days.

5. FINANCIAL RED FLAGS
Check and flag each: cumulative operating cash flow versus profit over 5
years; debtor days and inventory days rising; debt and interest cover; other
income as a share of profit; recurring "exceptional" items; capitalised
expenses; contingent liabilities; related-party dealings; low tax rate;
dilution; ROCE/ROE falling; margin volatility; ROE below the cost of equity
(about 13%).

6. FUTURE GROWTH (from concalls)
What management says about growth: revenue, margin, capex, capacity, order
book, new products, geographies, with timelines. What drives it: volume,
price, or new business? How much has past guidance been met? Estimate the
growth runway in years, with the reason. For sanity, note that very high
growth (above 25% a year) has rarely lasted more than 5-6 years. Give bear,
base and bull cases for the next 3-5 years with the assumptions written out.

OUTPUT
Scorecard 0-10 for: Business quality, Moat, Financial safety, Cash conversion,
Growth runway. List the 5 biggest risks, a "what would make me wrong" list,
and a verdict: Great / Good / Average / Avoid."""


def build_price_prompt(company_ticker: str, management_report: str, business_report: str) -> str:
    return f"""Using the findings from the management and business studies for {company_ticker}:
1. Find price, EPS (TTM), ROE, ROCE, book value, P/E, P/B, PEG and payback
   ratio. Use the 3-year expected profit growth from concalls or analyst
   estimates, and state clearly where a number is your assumption.
2. Check ROE against the cost of equity (about 13%). If ROE is lower, growth
   does not create value.
3. Compare P/E with its own 10-year range and with peers. Point out if current
   profit is unusually high or low versus its average, because P/E can mislead.
4. Give intrinsic value as a low-base-high range, and a buy-below price with a
   30% margin of safety.
5. Final memo: Avoid / Watchlist / Deep-dive / Consider buying, the triggers to
   watch quarterly, and the exact events that would make you sell.

=== MANAGEMENT QUALITY REPORT (verbatim, for reference) ===
{management_report}

=== BUSINESS QUALITY REPORT (verbatim, for reference) ===
{business_report}"""


def run_full_analysis(symbol: str, company: str) -> None:
    """Thread target for the 'Analyze' button -- runs the 3 studies sequentially, saving each
    stage's result as it completes (this IS the heartbeat analysis_store.is_stale relies on).

    The ENTIRE body is wrapped in try/except: a bare threading.Thread swallows uncaught
    exceptions (just a stderr traceback), which would leave the DB row stuck at status='running'
    forever if a failure weren't caught and turned into mark_error here.
    """
    company_ticker = f"{company} (NSE: {symbol})"
    try:
        management_report, management_citations = _call_openrouter(
            build_management_prompt(company_ticker)
        )
        analysis_store.save_stage(symbol, "management_report", management_report, management_citations)

        business_report, business_citations = _call_openrouter(
            build_business_prompt(company_ticker)
        )
        analysis_store.save_stage(symbol, "business_report", business_report, business_citations)

        price_report, price_citations = _call_openrouter(
            build_price_prompt(company_ticker, management_report, business_report)
        )
        analysis_store.save_stage(symbol, "price_report", price_report, price_citations)

        analysis_store.mark_done(symbol)
    except Exception as exc:
        analysis_store.mark_error(symbol, str(exc))
