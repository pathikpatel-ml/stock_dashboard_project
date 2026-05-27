#!/usr/bin/env python
"""
Daily NSE Bhav Copy delivery-volume downloader for the Multi-Year Breakout strategy.

Downloads the NSE "Security-wise Deliverable Position" file for recent trading days, parses
the EQ rows, stores one parsed file per date under ``data/delivery/``, then rebuilds the
consolidated volume-weighted monthly store ``data/delivery/delivery_monthly.csv``.

Usage
-----
    python download_delivery_data.py                 # incremental: last 5 calendar days
    python download_delivery_data.py --backfill-days 120   # initial backfill (~90 trading days)
    python download_delivery_data.py --date 2026-05-26     # a single specific date

Run daily after 15:30 IST. The monthly aggregate needs the breakout month plus the prior
2-3 months of history (doc §3.4), so an initial backfill of ~90 trading days is recommended.
"""
import argparse
import os
from datetime import date, datetime, timedelta

from modules.breakout import delivery_data as dd


def _trading_days(end: date, n_calendar_days: int):
    """Yield candidate weekday dates from oldest to newest (NSE holidays handled by download miss)."""
    days = [end - timedelta(days=i) for i in range(n_calendar_days)]
    return [d for d in sorted(days) if d.weekday() < 5]  # Mon-Fri


def main():
    ap = argparse.ArgumentParser(description="Download NSE delivery bhav copy")
    ap.add_argument("--backfill-days", type=int, default=5, help="calendar days back to fetch")
    ap.add_argument("--date", type=str, default=None, help="single date YYYY-MM-DD")
    args = ap.parse_args()

    os.makedirs(dd.DELIVERY_DIR, exist_ok=True)

    if args.date:
        targets = [datetime.strptime(args.date, "%Y-%m-%d").date()]
    else:
        targets = _trading_days(date.today(), args.backfill_days)

    fetched = 0
    for d in targets:
        out_path = os.path.join(dd.DELIVERY_DIR, dd.DAILY_FILE_TEMPLATE.format(date_str=d.strftime("%Y%m%d")))
        if os.path.exists(out_path):
            continue  # already have this day
        raw = dd.download_bhavcopy(d)
        if raw is None:
            print(f"  {d}: unavailable (holiday/not published) — skipped")
            continue
        parsed = dd.parse_delivery(raw, series="EQ")
        if parsed.empty:
            print(f"  {d}: no EQ rows parsed — skipped")
            continue
        dd.save_daily(parsed, d)
        fetched += 1
        print(f"  {d}: saved {len(parsed)} EQ rows")

    # Rebuild the consolidated monthly store from every daily file on disk.
    all_daily = dd.load_all_daily()
    monthly = dd.update_monthly_store(all_daily)
    print(
        f"Done. New daily files: {fetched}. Monthly store rows: {len(monthly)} "
        f"({all_daily['Symbol'].nunique() if not all_daily.empty else 0} symbols)."
    )


if __name__ == "__main__":
    main()
