#!/usr/bin/env python
# coding: utf-8
"""
validate_screening_data.py

Compares every metric in Master_company_market_trend_analysis.csv against
live Screener.in data and flags discrepancies that could flip V20 pass/fail.

Output: output/validation_report_YYYYMMDD_HHMM.csv
        output/validation_summary_YYYYMMDD_HHMM.txt
"""

import os
import re
import sys
import time
import traceback
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV      = os.path.join(REPO_BASE_PATH, "Master_company_market_trend_analysis.csv")
OUTPUT_DIR      = os.path.join(REPO_BASE_PATH, "output")
DELAY_SECONDS   = 2.0   # polite delay between screener.in requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# V20 screening thresholds (from apply_screening_criteria in stock_screener.py)
V20_NET_PROFIT_MIN   = 200   # Cr  (non-bank)
V20_ROCE_MIN         = 20    # %   (non-bank)
V20_PUBLIC_HOLD_MAX  = 30    # %
V20_BANK_NP_MIN      = 1000  # Cr
V20_BANK_ROE_MIN     = 10    # %


# ---------------------------------------------------------------------------
# Screener.in parsing helpers
# ---------------------------------------------------------------------------

def _parse_number(text):
    """Strip %, commas, Cr., ₹ and return float or None."""
    if text is None:
        return None
    clean = re.sub(r"[%,₹]", "", str(text)).replace("Cr.", "").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def _fetch_page(symbol, session):
    url = f"https://www.screener.in/company/{symbol}/"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            return BeautifulSoup(resp.content, "html.parser")
        print(f"    [{symbol}] HTTP {resp.status_code} from Screener.in")
        return None
    except Exception as exc:
        print(f"    [{symbol}] Fetch error: {exc}")
        return None


def _extract_key_ratios(soup):
    """
    Parse the top-level key metrics ul (Market Cap, ROCE, ROE, …).
    Returns dict with lowercase keys.
    """
    ratios = {}
    for ul in soup.find_all("ul"):
        text = ul.get_text()
        if "ROCE" in text and "ROE" in text:
            for li in ul.find_all("li"):
                spans = li.find_all("span")
                if len(spans) >= 2:
                    name  = spans[0].get_text(strip=True).rstrip("?").lower()
                    value = _parse_number(spans[-1].get_text(strip=True))
                    if value is not None:
                        ratios[name] = value
            break   # only need the first matching ul
    return ratios


def _extract_public_holding(soup):
    """
    Return the LATEST quarter's Public holding % from the shareholding table.
    Columns are ordered oldest → newest, so we take the LAST data column.
    """
    section = soup.find("section", id="shareholding")
    if not section:
        return None
    for table in section.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower().rstrip("+")
            if label == "public":
                # last data column = most recent quarter
                for cell in reversed(cells[1:]):
                    val = _parse_number(cell.get_text(strip=True))
                    if val is not None and 0 < val <= 100:
                        return val
    return None


def _extract_net_profit_ttm(soup):
    """
    Return the TTM (trailing twelve months) net profit in crores from the P&L table.
    Screener.in shows TTM in the last column of the profit-loss section.
    """
    section = soup.find("section", id="profit-loss")
    if not section:
        return None
    for table in section.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()
            if "net profit" in label or "profit after tax" in label:
                for cell in reversed(cells[1:]):
                    val = _parse_number(cell.get_text(strip=True))
                    if val is not None and val != 0:
                        return val
    return None


def _extract_balance_sheet_de(soup):
    """D/E = Borrowings / (Share Capital + Reserves) from balance-sheet section."""
    section = soup.find("section", id="balance-sheet")
    if not section:
        return None

    def latest_positive(cells):
        for cell in reversed(cells[1:]):
            val = _parse_number(cell.get_text(strip=True))
            if val is not None and val > 0:
                return val
        return None

    borrowings = share_capital = reserves = None
    for table in section.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower().strip()
            if "borrowing" in label and borrowings is None:
                borrowings = latest_positive(cells) or 0.0
            elif label in ("share capital", "equity share capital") and share_capital is None:
                share_capital = latest_positive(cells) or 0.0
            elif label in ("reserves", "reserves & surplus", "other equity") and reserves is None:
                reserves = latest_positive(cells) or 0.0

    equity = (share_capital or 0.0) + (reserves or 0.0)
    if equity > 0 and borrowings is not None:
        return round(borrowings / equity, 4)
    return None


def _extract_all(symbol, session):
    """Return dict of live metrics for symbol, or None on failure."""
    soup = _fetch_page(symbol, session)
    if soup is None:
        return None

    ratios         = _extract_key_ratios(soup)
    public_holding = _extract_public_holding(soup)
    net_profit     = _extract_net_profit_ttm(soup)
    debt_to_equity = _extract_balance_sheet_de(soup)

    return {
        "roce":           ratios.get("roce"),
        "roe":            ratios.get("roe"),
        "public_holding": public_holding,
        "net_profit":     net_profit,
        "debt_to_equity": debt_to_equity,
    }


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------

STATUS_THRESHOLDS = {
    # metric: (warning_pct, critical_pct)
    "Public Holding (%)": (5, 15),
    "ROCE (%)":           (15, 35),
    "ROE (%)":            (15, 35),
    "Net Profit (Cr)":    (20, 40),
    "Debt to Equity":     (30, 60),
}


def _status(metric, our, live):
    """Return OK / WARNING / CRITICAL based on relative difference."""
    if our is None or live is None:
        return "MISSING_DATA"
    if our == 0 and live == 0:
        return "OK"
    denom = max(abs(our), abs(live), 0.001)
    rel = abs(live - our) / denom * 100
    warn_t, crit_t = STATUS_THRESHOLDS.get(metric, (15, 35))
    if rel < warn_t:
        return "OK"
    if rel < crit_t:
        return "WARNING"
    return "CRITICAL"


def _v20_impact(metric, our, live, is_bank):
    """
    Check whether the data error would change whether the stock passes
    the V20 screening filter for this metric.
    Returns 'FILTER_FLIP' / 'NO_CHANGE' / 'N/A'
    """
    if our is None or live is None:
        return "UNKNOWN"

    if metric == "Public Holding (%)":
        our_pass  = our  < V20_PUBLIC_HOLD_MAX
        live_pass = live < V20_PUBLIC_HOLD_MAX
    elif metric == "ROCE (%)" and not is_bank:
        our_pass  = our  > V20_ROCE_MIN
        live_pass = live > V20_ROCE_MIN
    elif metric == "ROE (%)" and is_bank:
        our_pass  = our  > V20_BANK_ROE_MIN
        live_pass = live > V20_BANK_ROE_MIN
    elif metric == "Net Profit (Cr)":
        threshold = V20_BANK_NP_MIN if is_bank else V20_NET_PROFIT_MIN
        our_pass  = our  > threshold
        live_pass = live > threshold
    else:
        return "N/A"

    return "FILTER_FLIP" if our_pass != live_pass else "NO_CHANGE"


def compare_stock(symbol, stored_row, live_data, is_bank):
    """
    Return list of row dicts — one per metric.
    """
    mapping = [
        ("Public Holding (%)", stored_row.get("Public Holding (%)"),  live_data.get("public_holding")),
        ("ROCE (%)",           stored_row.get("ROCE (%)"),            live_data.get("roce")),
        ("ROE (%)",            stored_row.get("ROE (%)"),             live_data.get("roe")),
        ("Net Profit (Cr)",    stored_row.get("Net Profit (Cr)"),     live_data.get("net_profit")),
        ("Debt to Equity",     stored_row.get("Debt to Equity"),      live_data.get("debt_to_equity")),
    ]

    rows = []
    for metric, our_val, live_val in mapping:
        try:
            our  = float(our_val)  if our_val  not in (None, "", "nan", "N/A") else None
            live = float(live_val) if live_val not in (None, "", "nan", "N/A") else None
        except (ValueError, TypeError):
            our = live = None

        abs_diff = round(live - our, 4) if (our is not None and live is not None) else None
        denom = max(abs(our), 0.001) if our else 0.001
        rel_diff = round(abs(live - our) / denom * 100, 1) if (our is not None and live is not None) else None

        rows.append({
            "Symbol":        symbol,
            "Is_Bank":       is_bank,
            "Metric":        metric,
            "Our_Value":     round(our, 4)  if our  is not None else "N/A",
            "Live_Value":    round(live, 4) if live is not None else "N/A",
            "Abs_Diff":      abs_diff,
            "Rel_Diff_%":    rel_diff,
            "Status":        _status(metric, our, live),
            "V20_Impact":    _v20_impact(metric, our, live, is_bank),
        })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_validation(sample_only=False, sample_n=10):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(MASTER_CSV):
        print(f"ERROR: {MASTER_CSV} not found. Run weekly screening first.")
        sys.exit(1)

    master_df = pd.read_csv(MASTER_CSV)
    if sample_only:
        master_df = master_df.head(sample_n)
        print(f"SAMPLE MODE: validating first {sample_n} stocks only.")

    total = len(master_df)
    print(f"Validating {total} stocks from {MASTER_CSV} ...")
    print(f"Using {DELAY_SECONDS}s delay between requests.\n")

    session = requests.Session()
    session.headers.update(HEADERS)

    all_rows   = []
    failed_syms = []

    for i, (_, stored_row) in enumerate(master_df.iterrows(), 1):
        symbol  = str(stored_row.get("Symbol", "")).upper().strip()
        is_bank = bool(stored_row.get("Is Bank/Finance", False))
        if not symbol:
            continue

        sys.stdout.write(f"\r[{i:3d}/{total}] {symbol:<15} ")
        sys.stdout.flush()

        live_data = _extract_all(symbol, session)
        if live_data is None:
            failed_syms.append(symbol)
            all_rows.append({
                "Symbol": symbol, "Is_Bank": is_bank,
                "Metric": "ALL", "Our_Value": "N/A", "Live_Value": "FETCH_FAILED",
                "Abs_Diff": None, "Rel_Diff_%": None,
                "Status": "FETCH_ERROR", "V20_Impact": "UNKNOWN",
            })
        else:
            rows = compare_stock(symbol, stored_row.to_dict(), live_data, is_bank)
            all_rows.extend(rows)

        time.sleep(DELAY_SECONDS)

    print("\n")  # newline after progress

    report_df = pd.DataFrame(all_rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    report_path  = os.path.join(OUTPUT_DIR, f"validation_report_{ts}.csv")
    summary_path = os.path.join(OUTPUT_DIR, f"validation_summary_{ts}.txt")
    report_df.to_csv(report_path, index=False)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    lines = []
    lines.append("=" * 60)
    lines.append("V20 SCREENING DATA VALIDATION REPORT")
    lines.append(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Stocks checked : {total}")
    lines.append(f"Failed fetches : {len(failed_syms)}")
    lines.append("=" * 60)

    status_counts = report_df["Status"].value_counts()
    lines.append("\n--- Status breakdown (all metrics combined) ---")
    for status, cnt in status_counts.items():
        lines.append(f"  {status:<20} {cnt}")

    # Per-metric summary
    lines.append("\n--- Per-metric accuracy ---")
    for metric in ["Public Holding (%)", "ROCE (%)", "ROE (%)", "Net Profit (Cr)", "Debt to Equity"]:
        sub = report_df[report_df["Metric"] == metric]
        if sub.empty:
            continue
        ok  = (sub["Status"] == "OK").sum()
        warn= (sub["Status"] == "WARNING").sum()
        crit= (sub["Status"] == "CRITICAL").sum()
        miss= (sub["Status"] == "MISSING_DATA").sum()
        lines.append(f"  {metric:<25}  OK={ok}  WARN={warn}  CRIT={crit}  MISS={miss}")

    # Filter flips — most critical
    flips = report_df[report_df["V20_Impact"] == "FILTER_FLIP"].copy()
    lines.append(f"\n--- FILTER FLIPS (data error changes pass/fail) : {len(flips)} ---")
    if not flips.empty:
        for _, r in flips.iterrows():
            lines.append(
                f"  {r['Symbol']:<15} {r['Metric']:<25} "
                f"Stored={r['Our_Value']}  Live={r['Live_Value']}"
            )
    else:
        lines.append("  None found.")

    # Worst ROCE discrepancies
    roce_df = report_df[report_df["Metric"] == "ROCE (%)"].copy()
    roce_df["Rel_Diff_%"] = pd.to_numeric(roce_df["Rel_Diff_%"], errors="coerce")
    worst_roce = roce_df.dropna(subset=["Rel_Diff_%"]).nlargest(10, "Rel_Diff_%")
    lines.append("\n--- Top 10 ROCE discrepancies ---")
    for _, r in worst_roce.iterrows():
        lines.append(
            f"  {r['Symbol']:<15} Stored={r['Our_Value']:<10} "
            f"Live={r['Live_Value']:<10} Diff={r['Rel_Diff_%']:.1f}%"
        )

    # Worst Public Holding discrepancies
    ph_df = report_df[report_df["Metric"] == "Public Holding (%)"].copy()
    ph_df["Rel_Diff_%"] = pd.to_numeric(ph_df["Rel_Diff_%"], errors="coerce")
    worst_ph = ph_df.dropna(subset=["Rel_Diff_%"]).nlargest(10, "Rel_Diff_%")
    lines.append("\n--- Top 10 Public Holding discrepancies ---")
    for _, r in worst_ph.iterrows():
        lines.append(
            f"  {r['Symbol']:<15} Stored={r['Our_Value']:<10} "
            f"Live={r['Live_Value']:<10} Diff={r['Rel_Diff_%']:.1f}%"
        )

    if failed_syms:
        lines.append(f"\n--- Symbols that failed to fetch ---")
        lines.append("  " + ", ".join(failed_syms))

    lines.append(f"\nFull report: {report_path}")
    lines.append("=" * 60)

    summary_text = "\n".join(lines)
    print(summary_text)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)

    print(f"\nSummary saved: {summary_path}")
    print(f"Full CSV:      {report_path}")
    return report_df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0,
                        help="Validate only first N stocks (0 = all)")
    args = parser.parse_args()

    if args.sample > 0:
        run_validation(sample_only=True, sample_n=args.sample)
    else:
        run_validation(sample_only=False)
