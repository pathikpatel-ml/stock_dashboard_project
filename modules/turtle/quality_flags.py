"""
Pure functions for the Turtle Quant tab's fundamental quality/valuation flags.

2026-10-02 redesign (per explicit user request): the growth checks (Book Value/EPS/Sales
growth, ROE) no longer pass on an overall 10-year CAGR/average -- EVERY individual year in
the trailing window must clear the threshold. Added Quality of Turnover (Other Income / Total
Revenue < 10%) as a real, buildable red-flag condition. Added three category-aggregate flags
(Growth / Red Flag / Value) that the dashboard displays instead of the 21+ individual metrics.

Promoter PLEDGE % (same day, later): screener.in's free tier genuinely has no pledge data, but
NSE itself -- the primary regulatory source -- publishes it directly via
``modules/turtle/nse_shareholding.py``, keyed by the exact same NSE symbol already used
everywhere in this app (no Moneycontrol-style code-mapping project needed after all). Red Flag
now includes all 3 of the user's originally-requested conditions: Promoter Pledge, Quality of
Turnover, Interest Coverage.

ROE instead of ROCE (same day, later still): screener.in's free "Ratios" history table only has
ROCE% for non-financial companies and ONLY ROE% for banks/NBFCs (never both) -- using
screener.in's own row would have left ~2,000+ non-financial companies with no year-by-year ROE
history at all (only a single current-snapshot number exists for them elsewhere on the page).
Solved by deriving ROE ourselves, per year, from data already fetched for every company
regardless of type: ``roe_by_year()`` = Net Profit / (Equity Capital + Reserves) -- both already
parsed for the Book Value Growth and EPS Growth checks. No new network fetch, works uniformly
for every company, verified by hand against RELIANCE's real data (8-13% across 2015-2026,
consistent with its known real-world ROE range). ``parse_ratios_history``/screener.in's ROCE row
is no longer used anywhere in this pipeline.

Computed from screener.in's per-symbol annual history
(modules/turtle/standalone_fundamentals.py's parse_balance_sheet_history/
parse_cash_flow_history/parse_pl_history_extra) plus NSE's own promoter-holding/pledge data
(modules/turtle/nse_shareholding.py) plus historical stock prices (for the three valuation-ratio
checks).

All "10 years" mean "however many trailing annual columns screener.in actually has, capped at
10" -- fewer than MIN_YEARS_FOR_GROWTH usable years -> None (insufficient data), never a
guessed/short-window number. Promoter holding is scoped to NSE's own real history window
(~5.5 years back to ~Dec 2021 -- confirmed live, NSE's digitized archive for this disclosure
type simply starts there), not the originally-asked 10 years (no free 10-year promoter-holding
source exists anywhere, confirmed from multiple angles).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# The snake_case field names compute_all() returns -- shared here so callers (
# modules/turtle/screener.py::build_fundamentals_lookup, modules/turtlequant/screener.py's
# fundamentals-merge loop) don't each hardcode their own copy of this list. The individual
# metric fields (everything before the last 5) are kept for debugging/export even though the
# dashboard only displays the 3 trailing category-aggregate flags.
QUALITY_FIELD_NAMES = [
    "book_value_cagr_10y", "book_value_growth_flag", "eps_cagr_10y", "eps_growth_flag",
    "roe_avg_10y", "roe_flag", "sales_cagr_10y", "sales_growth_flag",
    "promoter_holding_change_3y", "promoter_holding_flag",
    "promoter_pledge_pct", "promoter_pledge_flag",
    "interest_coverage", "interest_coverage_flag",
    "quality_of_turnover_pct", "quality_of_turnover_flag",
    "pb_current", "pb_5y_avg", "pb_flag",
    "ps_current", "ps_5y_avg", "ps_flag",
    "pcf_current", "pcf_5y_avg", "pcf_flag",
    "growth_category_flag", "red_flag_category_flag", "value_category_flag",
]

MAX_YEARS_FOR_GROWTH = 10
MIN_YEARS_FOR_GROWTH = 5  # fewer usable annual columns than this -> None, not a shaky number

GROWTH_THRESHOLD_PCT = 10.0
ROE_THRESHOLD_PCT = 10.0
INTEREST_COVERAGE_THRESHOLD = 5.0
QUALITY_OF_TURNOVER_THRESHOLD_PCT = 10.0
PROMOTER_PLEDGE_THRESHOLD_PCT = 1.0
PROMOTER_HOLDING_DECLINE_TOLERANCE_PCT = 5.0

Series = Tuple[Optional[List[str]], List[float]]  # (periods, values), as the parsers return


def _values_only(series: Optional[Series]) -> List[float]:
    if series is None:
        return []
    _periods, values = series
    return list(values)


def cagr(series: Optional[Series], max_years: int = MAX_YEARS_FOR_GROWTH,
         min_years: int = MIN_YEARS_FOR_GROWTH) -> Optional[float]:
    """Compound annual growth rate (%) of the LAST ``max_years+1`` annual columns (i.e. up to
    ``max_years`` year-over-year periods), oldest to newest. None if fewer than ``min_years``
    usable years exist, either the start OR end value isn't strictly positive (CAGR is
    undefined/meaningless for a loss-making or zero base/latest year -- e.g. EPS swinging from
    positive 10 years ago to negative today has no real growth RATE; naively computing
    ``(negative/positive) ** (1/years)`` in Python returns a COMPLEX number for a fractional
    exponent of a negative base, not a sensible float -- confirmed live, this crashed the real
    production run on a real loss-making company's EPS history before this guard was added),
    or any value is missing.
    """
    values = _values_only(series)
    if len(values) < min_years + 1:
        return None
    window = values[-(max_years + 1):]
    start, end = window[0], window[-1]
    years = len(window) - 1
    if start is None or end is None or start <= 0 or end <= 0 or years <= 0:
        return None
    return (((end / start) ** (1.0 / years)) - 1.0) * 100.0


def average(series: Optional[Series], max_years: int = MAX_YEARS_FOR_GROWTH,
            min_years: int = MIN_YEARS_FOR_GROWTH) -> Optional[float]:
    """Plain average of the last ``max_years`` annual values. None if fewer than ``min_years``
    usable years exist."""
    values = _values_only(series)
    if len(values) < min_years:
        return None
    window = values[-max_years:]
    return sum(window) / len(window)


def yoy_growth_values(series: Optional[Series], max_years: int = MAX_YEARS_FOR_GROWTH,
                       min_years: int = MIN_YEARS_FOR_GROWTH) -> Optional[List[float]]:
    """Year-over-year %% growth for each consecutive pair in the trailing ``max_years + 1`` raw
    annual values (same windowing as ``cagr()``) -- i.e. up to ``max_years`` growth figures, one
    per year. None if fewer than ``min_years + 1`` raw values exist, or any base value in the
    window is non-positive (a growth RATE is undefined from a zero/negative base -- same
    reasoning as ``cagr()``'s start/end guard, applied per-year here instead of start/end only).
    """
    values = _values_only(series)
    if len(values) < min_years + 1:
        return None
    window = values[-(max_years + 1):]
    growth = []
    for i in range(len(window) - 1):
        base, nxt = window[i], window[i + 1]
        if base is None or nxt is None or base <= 0:
            return None
        growth.append((nxt / base - 1.0) * 100.0)
    return growth


def level_values(series: Optional[Series], max_years: int = MAX_YEARS_FOR_GROWTH,
                  min_years: int = MIN_YEARS_FOR_GROWTH) -> Optional[List[float]]:
    """The trailing ``max_years`` raw annual values as-is (no growth computation) -- used for
    ROE, where each year's own VALUE (not its growth) must clear the threshold. None if fewer
    than ``min_years`` usable years exist."""
    values = _values_only(series)
    if len(values) < min_years:
        return None
    return values[-max_years:]


def roe_by_year(net_profit: Optional[Series], book_value: Optional[Series]) -> Optional[Series]:
    """Derived ROE (%%) per year = Net Profit / (Equity Capital + Reserves) -- NOT screener.in's
    own "ROCE %%"/"ROE %%" row (see module docstring for why: that row is ROCE for non-financial
    companies and ROE for banks/NBFCs, never both, so using it directly would leave most
    companies with no year-by-year ROE history at all). Both inputs are already parsed/derived
    for other checks (EPS growth, Book Value growth), so this needs no new data. Only periods
    present in BOTH series are kept; a zero/missing book value for a period is skipped (division
    undefined). None if either input is missing."""
    if net_profit is None or book_value is None:
        return None
    np_periods, np_values = net_profit
    bv_by_period = dict(zip(*book_value))
    periods, values = [], []
    for period, profit in zip(np_periods, np_values):
        bv = bv_by_period.get(period)
        if bv is None or bv == 0 or profit is None:
            continue
        periods.append(period)
        values.append((profit / bv) * 100.0)
    return (periods, values) if periods else None


def all_years_above_threshold(values: Optional[List[float]], threshold: float) -> Optional[bool]:
    """True only if EVERY value in ``values`` exceeds ``threshold`` (2026-10-02 redesign: a
    single weak year fails the whole metric, not just an overall average/CAGR). None if
    ``values`` itself is None (insufficient underlying data -- propagated from
    yoy_growth_values()/level_values()'s own None-for-insufficient-data contract)."""
    if values is None:
        return None
    return all(v is not None and v > threshold for v in values)


def interest_coverage(profit_before_tax: Optional[Series], interest: Optional[Series]) -> Optional[float]:
    """Latest available year's (Profit before tax + Interest) / Interest. If the latest year's
    Interest is 0 (no debt), there is nothing to "cover" -- treated as infinite/automatically
    fine, returned as None here (undefined ratio) with interest_coverage_flag() below turning
    that specific None-because-zero-interest case into True (an explicit assumption, not a
    silent one -- see that function's docstring).
    """
    pbt_values = _values_only(profit_before_tax)
    interest_values = _values_only(interest)
    if not pbt_values or not interest_values:
        return None
    pbt_latest, interest_latest = pbt_values[-1], interest_values[-1]
    if pbt_latest is None or interest_latest is None:
        return None
    if interest_latest == 0:
        return None  # undefined ratio -- see interest_coverage_flag's zero-interest handling
    return (pbt_latest + interest_latest) / interest_latest


def interest_coverage_flag(
    coverage: Optional[float], interest: Optional[Series], threshold: float = INTEREST_COVERAGE_THRESHOLD,
) -> Optional[bool]:
    """True if coverage > threshold. Special case (explicit assumption, confirmed in the plan):
    if the latest year's Interest is exactly 0 (no debt), there's no interest burden to cover
    at all -- treated as automatically True rather than "insufficient data", since a genuinely
    debt-free company shouldn't fail a debt-servicing-safety check for having no debt.
    """
    interest_values = _values_only(interest)
    if coverage is None:
        if interest_values and interest_values[-1] == 0:
            return True
        return None
    return coverage > threshold


def promoter_holding_flag(
    promoter_pct: Optional[Series], decline_tolerance_pct: float = PROMOTER_HOLDING_DECLINE_TOLERANCE_PCT,
) -> Optional[bool]:
    """True if the latest quarter's promoter holding % is constant/increasing vs. the OLDEST
    available quarter, OR has declined by at most ``decline_tolerance_pct`` percentage points
    (2026-10-02, per the user's own instruction: a small decline -- e.g. a promoter trimming
    stake slightly for personal liquidity/tax reasons -- isn't treated as a real red flag, only
    a decline of more than 5 points is) -- whatever real window the caller's data source
    provides (NSE's own ~5.5-year history, preferred as of 2026-10-02; screener.in's ~3-year
    history as a fallback if NSE's fetch failed -- see compute_all()). Only compares the two
    endpoints, not every quarter in between.

    If the CURRENT (latest) promoter holding is exactly 0 -- the company genuinely has no
    promoter group right now (confirmed live: ICICIBANK/ITC/L&T show a flat 0 every quarter;
    HDFCBANK shows a real transition from ~25.8% to 0 after its 2023 merger with HDFC Ltd, its
    former promoter) -- this is treated as an automatic pass BEFORE the tolerance check above
    (a 25+ point drop to zero would otherwise fail the 5-point tolerance): there is no promoter
    left to have decreased its holding, so the condition is trivially fulfilled, mirroring
    interest_coverage_flag's zero-debt auto-pass.

    None if fewer than 2 quarters of data exist at all.
    """
    values = _values_only(promoter_pct)
    if len(values) < 2:
        return None
    if values[-1] == 0:
        return True
    return (values[0] - values[-1]) <= decline_tolerance_pct


def promoter_holding_change(promoter_pct: Optional[Series]) -> Optional[float]:
    """Percentage-point change from the oldest available quarter (~3 years back) to the
    latest -- the underlying value shown alongside promoter_holding_flag."""
    values = _values_only(promoter_pct)
    if len(values) < 2:
        return None
    return values[-1] - values[0]


def promoter_pledge_flag(
    pledge_pct: Optional[float], threshold: float = PROMOTER_PLEDGE_THRESHOLD_PCT,
) -> Optional[bool]:
    """True if promoter-pledge %% (of the promoter's OWN holding -- see
    modules/turtle/nse_shareholding.py's module docstring for the exact definition and why it's
    NOT the same as "%% of total shares") is below ``threshold``. None only if the pledge %%
    itself couldn't be determined at all (a real NSE fetch failure) -- a genuine 0%% (no pledge
    disclosure on file) is a normal input here, not a missing-data case."""
    if pledge_pct is None:
        return None
    return pledge_pct < threshold


def shares_outstanding_by_year(net_profit: Optional[Series], eps: Optional[Series]) -> Dict[str, float]:
    """Derives shares outstanding (in the SAME units as net_profit, i.e. crore-of-shares if
    net_profit is in Rs Crore) for each period, as ``net_profit / eps`` -- avoids needing to
    separately parse Face Value or Market Cap (neither directly gives a clean per-year series).
    Keyed by period label so it can be joined against other per-period series. Skips any period
    where eps is None/0 or the period isn't present in net_profit's own period list (guards
    against the two rows having slightly different column sets, e.g. one row missing a cell).
    """
    if net_profit is None or eps is None:
        return {}
    np_periods, np_values = net_profit
    eps_periods, eps_values = eps
    if not np_periods or not eps_periods:
        return {}
    eps_by_period = dict(zip(eps_periods, eps_values))
    result = {}
    for period, profit in zip(np_periods, np_values):
        e = eps_by_period.get(period)
        if e is None or e == 0 or profit is None:
            continue
        result[period] = profit / e
    return result


def per_share_by_year(total_by_period: Optional[Series], shares_by_period: Dict[str, float]) -> Dict[str, float]:
    """(period -> per-share value), dividing a total-basis series (book value, sales, CFO --
    whatever's in ``total_by_period``, same Rs Crore convention as shares_outstanding_by_year's
    input) by that period's derived share count. Periods missing a share-count entry are
    skipped, not zero-filled."""
    if total_by_period is None:
        return {}
    periods, values = total_by_period
    result = {}
    for period, value in zip(periods, values):
        shares = shares_by_period.get(period)
        if shares is None or shares == 0 or value is None:
            continue
        result[period] = value / shares
    return result


def valuation_ratio_by_year(
    per_share_by_period: Dict[str, float], price_by_period: Dict[str, float],
) -> Dict[str, float]:
    """(period -> price / per_share_value) -- e.g. Price-to-Book for that period, given that
    period's derived per-share book value and that period's actual (or nearest available)
    year-end stock price. Periods missing either side are skipped."""
    result = {}
    for period, per_share in per_share_by_period.items():
        price = price_by_period.get(period)
        if price is None or per_share == 0:
            continue
        result[period] = price / per_share
    return result


def valuation_flag(five_year_avg_ratio: Optional[float], current_ratio: Optional[float]) -> Optional[bool]:
    """True if the stock is CHEAPER than its own 5-year-average valuation (avg ratio > current
    ratio) -- e.g. current P/B below its own 5-year average P/B. None if either side is missing.
    """
    if five_year_avg_ratio is None or current_ratio is None:
        return None
    return five_year_avg_ratio > current_ratio


def quality_of_turnover(other_income: Optional[Series], sales: Optional[Series]) -> Optional[float]:
    """Latest common year's Other Income / (Sales + Other Income), as a percentage -- how much
    of total revenue is non-operating (the user's own definition, 2026-10-02). None if either
    series is missing, or they share no common period, or total revenue is zero."""
    if other_income is None or sales is None:
        return None
    oi_periods, oi_values = other_income
    sales_by_period = dict(zip(*sales))
    for period, oi in zip(reversed(oi_periods), reversed(oi_values)):
        s = sales_by_period.get(period)
        if s is None or oi is None:
            continue
        total_revenue = s + oi
        if total_revenue == 0:
            return None
        return (oi / total_revenue) * 100.0
    return None


def quality_of_turnover_flag(
    qot_pct: Optional[float], threshold: float = QUALITY_OF_TURNOVER_THRESHOLD_PCT,
) -> Optional[bool]:
    if qot_pct is None:
        return None
    return qot_pct < threshold


def _all_true(*flags: Optional[bool]) -> bool:
    """True only if every flag is exactly True -- a None (insufficient data) or False both
    count as "not fulfilled", matching the user's own framing for the 3 dashboard categories
    ("No" if ANY condition is not fulfilled, 2026-10-02). Never returns None -- the dashboard
    only has a Yes/No state, no third "unknown" bucket."""
    return all(f is True for f in flags)


def growth_category_flag(
    book_value_growth_flag: Optional[bool], eps_growth_flag: Optional[bool],
    roe_flag: Optional[bool], sales_growth_flag: Optional[bool],
    promoter_holding_flag: Optional[bool],
) -> bool:
    return _all_true(book_value_growth_flag, eps_growth_flag, roe_flag, sales_growth_flag, promoter_holding_flag)


def red_flag_category_flag(
    promoter_pledge_flag: Optional[bool], quality_of_turnover_flag: Optional[bool],
    interest_coverage_flag: Optional[bool],
) -> bool:
    """All 3 of the user's originally-requested Red Flag conditions, now all genuinely buildable
    (2026-10-02): Promoter Pledge was initially excluded -- screener.in's free tier has no pledge
    data at all -- but NSE itself (the primary regulatory source) publishes it directly, keyed by
    the same NSE symbol already used everywhere in this app (see
    modules/turtle/nse_shareholding.py::fetch_promoter_pledge_pct). No separate
    Moneycontrol-code mapping project was needed after all."""
    return _all_true(promoter_pledge_flag, quality_of_turnover_flag, interest_coverage_flag)


def value_category_flag(pb_flag: Optional[bool], ps_flag: Optional[bool], pcf_flag: Optional[bool]) -> bool:
    return _all_true(pb_flag, ps_flag, pcf_flag)


def _combine_totals(a: Optional[Series], b: Optional[Series]) -> Optional[Series]:
    """Sums two period-aligned series period-by-period (e.g. Equity Capital + Reserves = total
    book value) -- only periods present in BOTH inputs are kept, so a period missing from
    either side is dropped rather than silently treated as zero."""
    if a is None or b is None:
        return None
    a_periods, a_values = a
    b_by_period = dict(zip(*b))
    periods, values = [], []
    for period, value in zip(a_periods, a_values):
        other = b_by_period.get(period)
        if other is None:
            continue
        periods.append(period)
        values.append(value + other)
    return (periods, values) if periods else None


def _current_valuation_ratio(per_share_by_period: Dict[str, float], current_price: Optional[float]) -> Optional[float]:
    """current_price / the LATEST period's per-share value -- "current" valuation computed the
    same derivation-method way as every historical year, for a fair comparison against the
    5-year average (see module docstring)."""
    if not per_share_by_period or current_price is None:
        return None
    latest_period = list(per_share_by_period.keys())[-1]
    per_share = per_share_by_period[latest_period]
    if not per_share:
        return None
    return current_price / per_share


def compute_all(fetch_result: dict, year_end_prices: Dict[str, float], current_price: Optional[float]) -> dict:
    """Ties every quality-flag function above together into the final scalar columns
    ``generate_turtle_fundamentals.py`` writes to ``turtle_fundamentals`` -- one call per
    symbol, given that symbol's raw ``standalone_fundamentals.fetch_profit_and_loss()`` result
    (which carries ``balance_sheet``/``cash_flow``/``pl_extra``/``promoter_holding`` -- see that
    function's docstring), ``nse_promoter_holding``/``pledge_pct`` merged in by the caller
    (see ``modules/turtle/nse_shareholding.py``), plus a period-label -> stock-price mapping for
    the valuation-ratio checks (the caller fetches these via yfinance; this module stays
    pure/I/O-free) and today's live current price.

    2026-10-02: Book Value/EPS/Sales growth and ROE now require EVERY individual year in the
    trailing window to clear the threshold (not just the overall CAGR/average) -- the CAGR/
    average numeric fields are still computed and returned (useful for debugging/export) but no
    longer determine their own flag. Adds Quality of Turnover (a real red-flag check) and three
    category-aggregate flags (Growth/Red Flag/Value) -- the only 3 fields the dashboard
    actually displays. Every value is independently None-safe -- a missing section for one
    metric never prevents the others from computing.
    """
    balance_sheet = fetch_result.get("balance_sheet") or {}
    cash_flow = fetch_result.get("cash_flow") or {}
    pl_extra = fetch_result.get("pl_extra") or {}
    promoter_holding = fetch_result.get("promoter_holding") or {}

    book_value = _combine_totals(balance_sheet.get("equity_capital"), balance_sheet.get("reserves"))
    sales = pl_extra.get("sales")
    eps = pl_extra.get("eps")
    net_profit = pl_extra.get("net_profit")
    interest = pl_extra.get("interest")
    pbt = pl_extra.get("profit_before_tax")
    other_income = pl_extra.get("other_income")
    # Derived (not screener.in's own row) -- see module docstring for why: screener.in's "Ratios"
    # history has ROCE for non-financial companies and ROE for banks/NBFCs, never both.
    roe = roe_by_year(net_profit, book_value)
    cfo = cash_flow.get("cfo")
    # NSE's own promoter-holding history (2026-10-02) is preferred over screener.in's -- longer
    # window (~5.5 years back to ~Dec 2021, vs screener.in's ~3) and the primary regulatory
    # source, not a secondary scrape. Falls back to screener.in's series only if the NSE fetch
    # itself failed for this symbol (see generate_turtle_fundamentals.py's fetch_one()).
    promoter_pct = fetch_result.get("nse_promoter_holding") or promoter_holding.get("promoter_pct")
    # Pledge is NOT computed here -- it's filled in by a separate post-processing pass in
    # generate_turtle_fundamentals.py (screener.in's own login-gated screening query covers the
    # whole universe in ~55 paginated requests, far more efficient than a per-symbol fetch; see
    # modules/turtle/screener_in_login.py). ``fetch_result`` simply won't have this key during
    # the main per-symbol pass, so pledge_pct/flag/red_flag_category_flag all correctly compute
    # as None/False here and get overwritten afterward once the real value is known.
    pledge_pct = fetch_result.get("pledge_pct")

    book_value_cagr_10y = cagr(book_value)
    eps_cagr_10y = cagr(eps)
    sales_cagr_10y = cagr(sales)
    roe_avg_10y = average(roe)
    coverage = interest_coverage(pbt, interest)

    book_value_growth_flag = all_years_above_threshold(yoy_growth_values(book_value), GROWTH_THRESHOLD_PCT)
    eps_growth_flag = all_years_above_threshold(yoy_growth_values(eps), GROWTH_THRESHOLD_PCT)
    sales_growth_flag = all_years_above_threshold(yoy_growth_values(sales), GROWTH_THRESHOLD_PCT)
    roe_flag_value = all_years_above_threshold(level_values(roe), ROE_THRESHOLD_PCT)
    promoter_flag = promoter_holding_flag(promoter_pct)
    pledge_flag = promoter_pledge_flag(pledge_pct)
    interest_flag = interest_coverage_flag(coverage, interest)
    qot_pct = quality_of_turnover(other_income, sales)
    qot_flag = quality_of_turnover_flag(qot_pct)

    shares = shares_outstanding_by_year(net_profit, eps)
    book_value_per_share = per_share_by_year(book_value, shares)
    sales_per_share = per_share_by_year(sales, shares)
    cfo_per_share = per_share_by_year(cfo, shares)

    pb_by_year = valuation_ratio_by_year(book_value_per_share, year_end_prices)
    ps_by_year = valuation_ratio_by_year(sales_per_share, year_end_prices)
    pcf_by_year = valuation_ratio_by_year(cfo_per_share, year_end_prices)

    pb_5y_avg = average((list(pb_by_year.keys()), list(pb_by_year.values())), max_years=5, min_years=3) \
        if pb_by_year else None
    ps_5y_avg = average((list(ps_by_year.keys()), list(ps_by_year.values())), max_years=5, min_years=3) \
        if ps_by_year else None
    pcf_5y_avg = average((list(pcf_by_year.keys()), list(pcf_by_year.values())), max_years=5, min_years=3) \
        if pcf_by_year else None

    pb_current = _current_valuation_ratio(book_value_per_share, current_price)
    ps_current = _current_valuation_ratio(sales_per_share, current_price)
    pcf_current = _current_valuation_ratio(cfo_per_share, current_price)

    pb_flag = valuation_flag(pb_5y_avg, pb_current)
    ps_flag = valuation_flag(ps_5y_avg, ps_current)
    pcf_flag = valuation_flag(pcf_5y_avg, pcf_current)

    return {
        "book_value_cagr_10y": book_value_cagr_10y,
        "book_value_growth_flag": book_value_growth_flag,
        "eps_cagr_10y": eps_cagr_10y,
        "eps_growth_flag": eps_growth_flag,
        "roe_avg_10y": roe_avg_10y,
        "roe_flag": roe_flag_value,
        "sales_cagr_10y": sales_cagr_10y,
        "sales_growth_flag": sales_growth_flag,
        "promoter_holding_change_3y": promoter_holding_change(promoter_pct),
        "promoter_holding_flag": promoter_flag,
        "promoter_pledge_pct": pledge_pct,
        "promoter_pledge_flag": pledge_flag,
        "interest_coverage": coverage,
        "interest_coverage_flag": interest_flag,
        "quality_of_turnover_pct": qot_pct,
        "quality_of_turnover_flag": qot_flag,
        "pb_current": pb_current,
        "pb_5y_avg": pb_5y_avg,
        "pb_flag": pb_flag,
        "ps_current": ps_current,
        "ps_5y_avg": ps_5y_avg,
        "ps_flag": ps_flag,
        "pcf_current": pcf_current,
        "pcf_5y_avg": pcf_5y_avg,
        "pcf_flag": pcf_flag,
        "growth_category_flag": growth_category_flag(
            book_value_growth_flag, eps_growth_flag, roe_flag_value, sales_growth_flag, promoter_flag,
        ),
        "red_flag_category_flag": red_flag_category_flag(pledge_flag, qot_flag, interest_flag),
        "value_category_flag": value_category_flag(pb_flag, ps_flag, pcf_flag),
    }
