"""
Pure functions for the Turtle Quant tab's fundamental quality/valuation flags (2026-10-01).

Nine flags, requested by the user, computed from screener.in's per-symbol annual history
(modules/turtle/standalone_fundamentals.py's parse_balance_sheet_history/parse_ratios_history/
parse_cash_flow_history/parse_pl_history_extra/parse_promoter_holding_history) plus historical
stock prices (for the three valuation-ratio checks). Two originally-requested criteria are
deliberately NOT here: "quality turnover" (undefined -- the user will describe it later) and
promoter PLEDGE % (confirmed live: no free data source exists on screener.in for this at all).

All "10 years" mean "however many trailing annual columns screener.in actually has, capped at
10" -- fewer than MIN_YEARS_FOR_GROWTH usable years -> None (insufficient data), never a
guessed/short-window number. Promoter holding is scoped to the real ~3-year (12-quarter)
window screener.in's free shareholding table actually provides, not the originally-asked
10 years (confirmed with the user 2026-10-01 -- no free 10-year promoter-holding source exists).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# The 21 snake_case field names compute_all() returns -- shared here so callers (
# modules/turtle/screener.py::build_fundamentals_lookup, modules/turtlequant/screener.py's
# fundamentals-merge loop) don't each hardcode their own copy of this list.
QUALITY_FIELD_NAMES = [
    "book_value_cagr_10y", "book_value_growth_flag", "eps_cagr_10y", "eps_growth_flag",
    "roce_avg_10y", "roce_flag", "sales_cagr_10y", "sales_growth_flag",
    "promoter_holding_change_3y", "promoter_holding_flag",
    "interest_coverage", "interest_coverage_flag",
    "pb_current", "pb_5y_avg", "pb_flag",
    "ps_current", "ps_5y_avg", "ps_flag",
    "pcf_current", "pcf_5y_avg", "pcf_flag",
]

MAX_YEARS_FOR_GROWTH = 10
MIN_YEARS_FOR_GROWTH = 5  # fewer usable annual columns than this -> None, not a shaky number

GROWTH_THRESHOLD_PCT = 10.0
ROCE_THRESHOLD_PCT = 10.0
INTEREST_COVERAGE_THRESHOLD = 5.0

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
    usable years exist, the start value isn't strictly positive (CAGR is undefined/meaningless
    for a loss-making or zero base year), or any value is missing.
    """
    values = _values_only(series)
    if len(values) < min_years + 1:
        return None
    window = values[-(max_years + 1):]
    start, end = window[0], window[-1]
    years = len(window) - 1
    if start is None or end is None or start <= 0 or years <= 0:
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


def growth_flag(cagr_pct: Optional[float], threshold_pct: float = GROWTH_THRESHOLD_PCT) -> Optional[bool]:
    if cagr_pct is None:
        return None
    return cagr_pct > threshold_pct


def roce_flag(roce_avg_pct: Optional[float], threshold_pct: float = ROCE_THRESHOLD_PCT) -> Optional[bool]:
    if roce_avg_pct is None:
        return None
    return roce_avg_pct > threshold_pct


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


def promoter_holding_flag(promoter_pct: Optional[Series]) -> Optional[bool]:
    """True if the latest quarter's promoter holding % is >= what it was ~12 quarters (~3
    years) ago -- the real window screener.in's free shareholding table actually provides
    (confirmed live 2026-10-01: only ~3 years of quarterly columns, not the originally-asked
    10 years). None if fewer than 2 quarters of data exist at all.
    """
    values = _values_only(promoter_pct)
    if len(values) < 2:
        return None
    return values[-1] >= values[0]


def promoter_holding_change(promoter_pct: Optional[Series]) -> Optional[float]:
    """Percentage-point change from the oldest available quarter (~3 years back) to the
    latest -- the underlying value shown alongside promoter_holding_flag."""
    values = _values_only(promoter_pct)
    if len(values) < 2:
        return None
    return values[-1] - values[0]


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
    (which now carries ``balance_sheet``/``ratios``/``cash_flow``/``pl_extra``/
    ``promoter_holding`` -- see that function's docstring) plus a period-label -> stock-price
    mapping for the valuation-ratio checks (the caller fetches these via yfinance; this module
    stays pure/I/O-free) and today's live current price.

    Returns a flat dict of the 21 columns (9 flags + their 12 underlying numeric values --
    interest coverage and the 3 promoter-holding-window fields don't have a separate "flag +
    value" pair beyond what's already named). Every value is independently None-safe -- a
    missing section for one metric never prevents the others from computing.
    """
    balance_sheet = fetch_result.get("balance_sheet") or {}
    ratios = fetch_result.get("ratios") or {}
    cash_flow = fetch_result.get("cash_flow") or {}
    pl_extra = fetch_result.get("pl_extra") or {}
    promoter_holding = fetch_result.get("promoter_holding") or {}

    book_value = _combine_totals(balance_sheet.get("equity_capital"), balance_sheet.get("reserves"))
    sales = pl_extra.get("sales")
    eps = pl_extra.get("eps")
    net_profit = pl_extra.get("net_profit")
    interest = pl_extra.get("interest")
    pbt = pl_extra.get("profit_before_tax")
    roce = ratios.get("roce_pct")
    cfo = cash_flow.get("cfo")
    promoter_pct = promoter_holding.get("promoter_pct")

    book_value_cagr_10y = cagr(book_value)
    eps_cagr_10y = cagr(eps)
    sales_cagr_10y = cagr(sales)
    roce_avg_10y = average(roce)
    coverage = interest_coverage(pbt, interest)

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

    return {
        "book_value_cagr_10y": book_value_cagr_10y,
        "book_value_growth_flag": growth_flag(book_value_cagr_10y),
        "eps_cagr_10y": eps_cagr_10y,
        "eps_growth_flag": growth_flag(eps_cagr_10y),
        "roce_avg_10y": roce_avg_10y,
        "roce_flag": roce_flag(roce_avg_10y),
        "sales_cagr_10y": sales_cagr_10y,
        "sales_growth_flag": growth_flag(sales_cagr_10y),
        "promoter_holding_change_3y": promoter_holding_change(promoter_pct),
        "promoter_holding_flag": promoter_holding_flag(promoter_pct),
        "interest_coverage": coverage,
        "interest_coverage_flag": interest_coverage_flag(coverage, interest),
        "pb_current": pb_current,
        "pb_5y_avg": pb_5y_avg,
        "pb_flag": valuation_flag(pb_5y_avg, pb_current),
        "ps_current": ps_current,
        "ps_5y_avg": ps_5y_avg,
        "ps_flag": valuation_flag(ps_5y_avg, ps_current),
        "pcf_current": pcf_current,
        "pcf_5y_avg": pcf_5y_avg,
        "pcf_flag": valuation_flag(pcf_5y_avg, pcf_current),
    }
