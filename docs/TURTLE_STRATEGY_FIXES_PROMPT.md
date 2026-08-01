# Task: Turtle Strategy — review fixes (round 2)

Context: the Turtle Strategy tab is built and tested (see `docs/TURTLE_STRATEGY_PLAN.md`
and the round-1 work). A review surfaced four items. Fix all four, add/extend tests,
keep the locked decisions in `TURTLE_STRATEGY_PLAN.md §7` unchanged, and report back.

Nothing here changes the classifier or the ADD/HOLD/EXIT definitions — these are
accuracy and ops fixes. Do not silently alter a locked decision; if blocked, stop and flag.

---

## Fix 1 — Sector-RS self-inclusion (accuracy) [HIGH]

**Where:** `modules/turtle/screener.py::run_pipeline`, the sector basket calc
(`sector_rs_lookup = fetched_df.dropna(subset=["stock_rs"]).groupby("Sector")["stock_rs"].mean()`).

**Problem:** the equal-weight sector RS includes the stock itself, so each stock is
compared against a basket it belongs to. This biases small sectors and makes a
single-member sector structurally unable to outperform.

**Do:** compute a **leave-one-out** sector mean for each stock — the mean of the
sector's `stock_rs` values *excluding that stock's own value*. Suggested approach:
per sector, keep `sum` and `count` of non-null `stock_rs`; for each member,
`loo_mean = (sum - stock_rs) / (count - 1)` when `count > 1`, else `None`
(single-member sector → sector RS undefined → `outperformance_flag` receives `None`
and safely returns False, unchanged behaviour for that edge case).

**Tests:** add a case proving leave-one-out differs from naive mean (e.g. a 3-stock
sector where the top stock outperforms the other two but would *not* beat the naive
all-inclusive mean in a constructed case), and confirm single-member sector still
yields `Outperformance_Flag = False`.

---

## Fix 2 — ATH-price source: use live daily close consistently [HIGH]

**Where:** `modules/turtle/screener.py::run_pipeline` (ATH price calc) and the
`current_price` used for the ATH-price flag.

**Problem:** `historical_max_close` is the max of **monthly month-end** closes (understates
the true high), while the ATH-price flag's `current_price` comes from the **weekly CSV**
(stale up to ~5 trading days) and `stock_rs` uses the **live** yfinance daily close —
three inconsistent price sources for one decision.

**Do:**
- Use the **daily** series (already fetched for RS) for both: `live_close = daily["Close"].iloc[-1]`
  and `historical_max_close = daily["Close"].max()`. Since `DAILY_HISTORY_PERIOD = "2y"`,
  the daily max only covers 2 years — so take `historical_max_close = max(daily_close_max,
  monthly_close_max)` to keep full-history coverage while using daily granularity for the
  recent high.
- Feed `live_close` (not the CSV `Current_Price`) into `ath_price_flag`. Keep the CSV
  `Current_Price` for the displayed column and for `above_exit_flag` (MA200 is CSV-derived,
  so pairing it with CSV price stays internally consistent) — but add a short comment noting
  the deliberate split.
- If `daily` is missing/empty, fall back to the current monthly-only behaviour.

**Tests:** synthetic daily series where the live close equals a recent daily high that is
*above* the last month-end close → ATH flag True with daily source, and a case where daily
max (2y) is below an older monthly high → combined max still catches the older high.

---

## Fix 3 — Cron hardening (`.github/workflows/turtle_signals.yml`) [MEDIUM]

**Problems:** pushes without rebasing (can reject when the 10:30/10:05 jobs commit first);
no job timeout; ~2,365 sequential yfinance calls risk throttling.

**Do:**
- Before push, `git pull --rebase origin main` (mirror `weekly_stock_screening.yml`).
- Add `timeout-minutes: 90` to the job.
- Add a brief retry/backoff note or light pacing if not already handled in `data_feed`
  (don't over-engineer — a small sleep between symbols or reuse of the existing cache is fine).
- Keep `workflow_dispatch` and the "no changes" no-op guard.

---

## Fix 4 — Rename misleading param (`modules/nse_category_fetcher.py`) [TRIVIAL]

`merge_categories_maps(..., replace_prefixes=...)` does **exact-match**, not prefix-match.
Rename the parameter to `replace_tags` (update the docstring and callers) so the name
matches behaviour. No logic change.

---

## After the fixes

1. Run the full turtle test suite plus the four new/extended cases; confirm no regressions
   across the whole `pytest` run.
2. Re-run `generate_turtle_signals.py --limit 25` as a smoke test and confirm the schema
   and Signal distribution still look sane.
3. Report: files changed, what each fix does, new test names + results, and confirm the
   locked decisions and the classifier are untouched.
