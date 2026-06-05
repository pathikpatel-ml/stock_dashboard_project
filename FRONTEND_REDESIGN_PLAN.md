# Frontend Redesign Plan — Stock Signal Dashboard
**Status:** Approved. Start Phase 1.  
**Reviewed by:** 3 rounds of cross-AI critique. Final verdict: ship-ready at ~95%.  
**Constraint:** Zero changes to any API call, Supabase schema, broker integration, or Dash callback data logic. CSS/markup/presentation layer only (with minor callback output additions in Phase 4).

---

## Context: What exists today

- **Framework:** Dash (Python) + Dash Bootstrap Components + Flask
- **Theme:** Inconsistent — login page is dark (`#1e293b`), dashboard is light (`#f0f2f5`). Jarring.
- **Font:** Inter everywhere — the most generic font in existence
- **Mobile:** Horizontal tab bar overflows on small screens. V20 DataTable requires left/right scroll. Unusable.
- **Tabs:** `dcc.Tabs` with `value="tab-v20"` | `"tab-breakout"` | `"tab-kite-settings"` | `"tab-admin"`
- **Assets folder:** `dashboard.css`, `login.css`, `enhanced_styles.css`, `custom_styles.css`
- **Key IDs:** `strategy-tabs`, `refresh-v20-live-data-button`, `kite-settings-loaded` (already a dcc.Store)

---

## Locked Design Decisions

### Colour tokens (final — do not change)

```css
:root {
  /* Backgrounds */
  --bg-base:      #0c0c10;   /* near-black — the page */
  --bg-surface:   #14141a;   /* cards */
  --bg-elevated:  #1c1c25;   /* modals, dropdowns, tooltips */
  --border:       #2c2c38;
  --border-focus: #4c4c60;

  /* Accents */
  --accent:       #e8a000;   /* amber — brand colour, unique in Indian fintech */
  --accent-dim:   #a06800;
  --bullish:      #10d9aa;   /* teal-green — NOT Zerodha's #22c55e, NOT Tailwind emerald */
  --bearish:      #ff5a6e;   /* salmon-red — NOT alarm-red, pairs with amber */

  /* Text */
  --text-primary: #f0f0f8;
  --text-muted:   #9090c0;   /* WCAG AA safe on all surfaces — don't go lower */
  --text-dim:     #5858a0;

  /* Spacing (4-multiple rhythm — do not deviate) */
  --sp-1:  4px;
  --sp-2:  8px;
  --sp-3:  12px;
  --sp-4:  16px;
  --sp-6:  24px;
  --sp-8:  32px;

  /* Border radius */
  --r-sm:  6px;
  --r-md:  10px;
  --r-lg:  16px;

  /* Typography */
  --font-ui:   'Onest', sans-serif;
  --font-mono: 'IBM Plex Mono', monospace;
}
```

**Why these colours (context for future sessions):**
- Amber replaces blue: every Indian trading app (Zerodha, Groww, Sensibull) uses blue. Amber is unclaimed.
- `#10d9aa` is NOT `#22c55e` (Zerodha) or `#34d399` (Tailwind emerald-400). It's deliberately off-key.
- `#ff5a6e` is soft/warm, not alarm-red. Palette coherence beats trader-psychology here. A/B test later if needed.
- `--text-muted: #9090c0` was specifically chosen after WCAG contrast check. The original plan had `#7070a0` which failed at small text sizes.

### Typography (final)

```
Google Fonts URL (add to app.index_string):
  Onest variable:    ?family=Onest:wght@100..900&display=swap
  IBM Plex Mono:     ?family=IBM+Plex+Mono:wght@400;600&display=swap
```

- **`Onest`** (2023, variable font, one file for all weights, ~25kb) — for all UI chrome, labels, headings
- **`IBM Plex Mono`** (400 + 600 weights ONLY — do not load all 14 weights) — for all prices, percentages, numbers
- Total font payload: ~50-55kb. Acceptable for Dash.
- `font-variant-numeric: tabular-nums` on every numeric element so prices don't jitter during updates

**Why NOT:** Inter (too generic), Syne (too editorial/magazine-y), Figtree (becoming the new Space Grotesk), Space Grotesk (explicitly banned), Geist (not on Google Fonts — Vercel proprietary), JetBrains Mono for UI chrome (too VS Code).

### Killed features (do not revisit without strong reason)

- **Page-tint market ambience** (`--bg-base` shifting #0c0c10 → #0d0c14 for pre-market) — killed because the 2-digit RGB shift is invisible on real Android phones in daylight. Replaced by expressive market-status chip only. Good kill.
- **Three-font stack** — killed. Two fonts only.
- **Bold/dramatic animations** — killed. Subtle only: 50ms stagger, 200ms fade, badge pulse. Trading apps should feel precise, not anxious.

---

## Phase 1 — CSS Foundation
**Scope:** CSS rewrite + font swap + PWA meta. **Zero markup changes. Zero callback changes.**  
**Deploy first. Live with it 24-48 hours on real phone before Phase 2.**

### Files to change in Phase 1

| File | Action |
|------|--------|
| `assets/dashboard.css` | Full rewrite using CSS tokens above |
| `assets/login.css` | Align to same dark theme + tokens |
| `assets/enhanced_styles.css` | Merge into dashboard.css, delete file |
| `assets/custom_styles.css` | Just imports — keep as-is or delete |
| `app.py` | Add font preconnects + PWA meta to `app.index_string` |
| `assets/manifest.json` | New file, ~200 bytes |

### Phase 1 checklist (every item must ship together)

- [ ] CSS custom properties defined on `:root` (full token set above)
- [ ] All hardcoded hex values replaced with tokens
- [ ] Login + dashboard unified to dark theme
- [ ] Font swap: `Onest` + `IBM Plex Mono`
- [ ] `font-variant-numeric: tabular-nums` on every price/percentage element
- [ ] All "Rs." replaced with ₹ glyph in Python layout files
- [ ] WCAG pass: verify no text below `--text-muted: #9090c0` on dark backgrounds
- [ ] `prefers-reduced-motion` wrapping **every** `@keyframes` block:
  ```css
  @media (prefers-reduced-motion: no-preference) {
    @keyframes fadeIn { ... }
    /* all animations here */
  }
  ```
- [ ] `:focus-visible` global rule (keyboard accessibility, matches brand):
  ```css
  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 4px;
  }
  ```
- [ ] Spacing scale uses 4-multiple only (`--sp-1` through `--sp-8`)
- [ ] PWA meta in `app.index_string`:
  ```html
  <meta name="theme-color" content="#0c0c10">
  <meta name="mobile-web-app-capable" content="yes">  <!-- NOT apple-mobile-web-app-capable, that's deprecated -->
  <link rel="manifest" href="/assets/manifest.json">
  ```
- [ ] `assets/manifest.json`:
  ```json
  {
    "name": "Stock Signal Dashboard",
    "short_name": "Signals",
    "display": "standalone",
    "background_color": "#0c0c10",
    "theme_color": "#0c0c10",
    "start_url": "/",
    "icons": [{"src": "/assets/favicon.ico", "sizes": "any"}]
  }
  ```
- [ ] Font preconnects in `app.index_string` (before font `<link>` tags):
  ```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  ```

---

## Phase 2 — Mobile Layout + Information Architecture
**Scope:** Bottom nav, signal cards, sticky header, summary strip, filter chips, safe areas.  
**Everything behind `@media (max-width: 768px)` — desktop untouched.**

### Files to change in Phase 2

| File | Action |
|------|--------|
| `assets/mobile.css` | New file — all mobile-only rules |
| `assets/market_state.js` | New file — market status chip logic + NSE holiday calendar |
| `app.py` | Add bottom nav HTML, summary strip HTML, 2 new Dash callbacks |
| `modules/v20_callbacks.py` | Add extra outputs: `signal-count` store, `v20-mobile-cards` div |

### 2a. Viewport + iOS safe areas (non-negotiable)

```css
.app-container  { min-height: 100dvh; }   /* dvh not vh — iOS Safari URL bar fix */
.bottom-nav     { padding-bottom: env(safe-area-inset-bottom, 16px); }
.sticky-header  { padding-top: env(safe-area-inset-top, 0px); }
```

**Why `100dvh` not `100vh`:** On iOS Safari, `100vh` is the full height including the URL bar. The URL bar hides/shows on scroll, making `100vh` elements jump. `100dvh` is the actual visible viewport — stable.

### 2b. Bottom navigation

Add this HTML in `app.py` → `_main_dashboard_layout()`, **outside and below** the `dcc.Tabs` component:

```python
html.Div(id="bottom-nav", className="bottom-nav mobile-only", children=[
    html.Button([html.I(className="fas fa-chart-line"), html.Span("Signals"),
                 html.Span(id="signal-count-badge", className="nav-badge")],
                id={"type": "bottom-nav-btn", "tab": "tab-v20"}, n_clicks=0,
                className="bottom-nav-item"),
    html.Button([html.I(className="fas fa-rocket"), html.Span("Breakout")],
                id={"type": "bottom-nav-btn", "tab": "tab-breakout"}, n_clicks=0,
                className="bottom-nav-item"),
    html.Button([html.I(className="fas fa-robot"), html.Span("Auto")],
                id={"type": "bottom-nav-btn", "tab": "tab-kite-settings"}, n_clicks=0,
                className="bottom-nav-item"),
    # Admin tab: only shown to admin users — use conditional in _main_dashboard_layout
    # html.Button([...], id={"type": "bottom-nav-btn", "tab": "tab-admin"}, ...) if is_admin else html.Div()
])
```

Callback in `app.py`:
```python
@app.callback(
    Output("strategy-tabs", "value", allow_duplicate=True),
    Input({"type": "bottom-nav-btn", "tab": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def bottom_nav_click(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered or not any(n for n in n_clicks_list if n):
        raise dash.exceptions.PreventUpdate
    import json
    id_dict = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
    return id_dict["tab"]
```

CSS:
```css
@media (max-width: 768px) {
  /* Hide Dash tabs on mobile */
  #strategy-tabs > .tab-container > .tabs-top { display: none !important; }

  .bottom-nav {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    height: 56px;
    background: var(--bg-surface);
    border-top: 1px solid var(--border);
    display: flex;
    z-index: 1000;
  }

  .bottom-nav-item {
    flex: 1;
    min-height: 48px;       /* 48px tap target */
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    border: none;
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-ui);
    font-size: 10px;
    cursor: pointer;
    position: relative;
  }

  .bottom-nav-item.active {
    color: var(--accent);
  }

  .bottom-nav-item.active::before {
    content: '';
    position: absolute;
    top: 0; left: 50%;
    transform: translateX(-50%);
    width: 24px; height: 2px;
    background: var(--accent);
    border-radius: 0 0 2px 2px;
  }

  /* Signal count badge — cap at 99+ */
  .nav-badge {
    position: absolute;
    top: 6px; right: calc(50% - 20px);
    background: var(--accent);
    color: #000;
    font-size: 9px;
    font-weight: 700;
    padding: 1px 4px;
    border-radius: 8px;
    min-width: 16px;
    text-align: center;
  }

  /* Sticky header with backdrop blur — with graceful fallback */
  .sticky-header {
    position: sticky;
    top: 0;
    height: 52px;
    background: rgba(12, 12, 16, 0.92);   /* fallback for no backdrop-filter */
    border-bottom: 1px solid var(--border);
    z-index: 999;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--sp-4);
  }

  @supports (backdrop-filter: blur(12px)) {
    .sticky-header {
      background: rgba(12, 12, 16, 0.6);
      backdrop-filter: blur(12px);
    }
  }

  /* Push content above bottom nav */
  .app-container {
    padding-bottom: calc(56px + env(safe-area-inset-bottom, 16px));
  }
}
```

### 2c. At-a-glance summary strip

Add below sticky header, above tab content (in `app.py`):

```python
html.Div(id="mobile-summary-strip", className="summary-strip mobile-only", children=[
    html.Div([
        html.Span(id="summary-signal-count", children="—", className="summary-number"),
        html.Span("SIGNALS", className="summary-label"),
    ], className="summary-chip"),
    html.Div([
        html.Span(id="summary-broker-status", children="—", className="summary-status"),
        html.Span("BROKER", className="summary-label"),
    ], className="summary-chip"),
    html.Div([
        html.Span(id="market-status-chip", children="—"),
    ], className="summary-chip"),
])
```

- `summary-signal-count`: fed by `dcc.Store('signal-count')` via clientside callback
- `summary-broker-status`: reads `dcc.Store('kite-settings-loaded')` which already exists
- `market-status-chip`: written by `assets/market_state.js`

### 2d. Market status chip + NSE holiday calendar

**File:** `assets/market_state.js` (Dash auto-loads all files in /assets)

```js
// REVIEW EACH DECEMBER — NSE publishes next year's holiday list in November.
// Source: https://www.nseindia.com/regulations/holiday-master
const NSE_HOLIDAYS_2026 = [
  '2026-01-26', // Republic Day
  '2026-03-02', // Mahashivratri
  '2026-03-25', // Holi
  '2026-03-30', // Id-Ul-Fitr (Ramzan)
  '2026-04-02', // Shri Ram Navami
  '2026-04-03', // Good Friday
  '2026-04-14', // Dr. Ambedkar Jayanti
  '2026-04-30', // Buddha Pournima
  '2026-06-27', // Bakri Id
  '2026-07-29', // Muharram
  '2026-08-15', // Independence Day
  '2026-08-26', // Ganesh Chaturthi
  '2026-10-02', // Gandhi Jayanti
  '2026-10-22', // Dussehra
  '2026-11-11', // Diwali (Laxmi Pujan)
  '2026-11-12', // Diwali (Balipratipada)
  '2026-11-25', // Guru Nanak Jayanti
  '2026-12-25', // Christmas
];

function getISTDate() {
  const now = new Date();
  // IST = UTC + 5:30
  const istOffset = 5 * 60 + 30;
  const istMs = now.getTime() + (istOffset + now.getTimezoneOffset()) * 60000;
  return new Date(istMs);
}

function isMarketOpen() {
  const ist = getISTDate();
  const day = ist.getDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;

  const dateStr = ist.toISOString().slice(0, 10);
  if (NSE_HOLIDAYS_2026.includes(dateStr)) return false;

  const h = ist.getHours(), m = ist.getMinutes();
  const totalMin = h * 60 + m;
  return totalMin >= 9 * 60 + 15 && totalMin < 15 * 60 + 30;
}

function isPreMarket() {
  const ist = getISTDate();
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;
  const dateStr = ist.toISOString().slice(0, 10);
  if (NSE_HOLIDAYS_2026.includes(dateStr)) return false;
  const totalMin = ist.getHours() * 60 + ist.getMinutes();
  return totalMin < 9 * 60 + 15;
}

function getMinutesToOpen() {
  const ist = getISTDate();
  const openMin = 9 * 60 + 15;
  const nowMin = ist.getHours() * 60 + ist.getMinutes();
  const diff = openMin - nowMin;
  const h = Math.floor(diff / 60);
  const m = diff % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function updateMarketChip() {
  const chip = document.getElementById('market-status-chip');
  if (!chip) return;

  if (isMarketOpen()) {
    chip.textContent = '● MARKET LIVE';
    chip.className = 'market-live';
  } else if (isPreMarket()) {
    chip.textContent = `🌅 Opens in ${getMinutesToOpen()}`;
    chip.className = 'market-pre';
  } else {
    chip.textContent = '○ Market closed';
    chip.className = 'market-closed';
  }
}

updateMarketChip();
setInterval(updateMarketChip, 30000); // update every 30s — not every 1s (no need)
```

### 2e. Signal cards (mobile only, V20 tab)

In `modules/v20_callbacks.py`, add a second output to the existing price-refresh callback:
```python
Output('v20-mobile-cards', 'children'),  # new output alongside existing ones
```

Signal card HTML structure (generated in Python):
```python
def _build_signal_card(row) -> html.Div:
    signal = row.get("Signal_Strength", "").upper()
    strength_map = {"STRONG BUY": 5, "BUY NOW": 4, "BUY": 3, "NEUTRAL": 2, "SELL": 1}
    strength = strength_map.get(signal, 2)
    icon = "↑" if strength >= 3 else ("→" if strength == 2 else "↓")
    is_bullish = strength >= 3

    proximity = row.get("Proximity to Buy (%)", 0)
    ltp = row.get("Latest Close Price", 0)
    target = row.get("Target Buy Price (Low)", 0)
    symbol = row.get("Symbol", "")

    # 5-segment strength meter (■ filled, □ empty)
    meter = "■" * strength + "□" * (5 - strength)

    return html.Div(className="signal-card", **{"data-symbol": symbol}, children=[
        # Header row
        html.Div(className="signal-card-header", children=[
            html.Span(symbol, className="signal-symbol"),
            html.Span([icon, " ", signal], className=f"signal-badge {'bullish' if is_bullish else 'bearish'}"),
        ]),
        # Price row
        html.Div(className="signal-card-prices", children=[
            html.Span(f"₹{ltp:,.2f}", className="signal-ltp"),
            html.Span(f"{proximity:+.1f}% to target", className="signal-proximity"),
        ]),
        # Strength meter
        html.Div(className="signal-card-meter", children=[
            html.Span(meter, className="meter-bar"),
            html.Span(f"Target ₹{target:,.2f}", className="signal-target"),
        ]),
    ])
```

**Note on Indian number formatting:** Use Python's `f"₹{value:,.2f}"` for now. For en-IN locale formatting (₹2,45,450 not ₹245,450), add a clientside_callback in Phase 3 that uses `Intl.NumberFormat('en-IN')` on rendered price spans.

**Touch targets in cards:**
```css
.signal-card {
  touch-action: pan-y;      /* prevent text-selection on long-press */
  min-height: 80px;
  padding: var(--sp-4);
}
```

### 2f. Filter + sort chips (mobile only)

```python
html.Div(id="mobile-filter-bar", className="filter-bar mobile-only", children=[
    dcc.Store(id="v20-mobile-filter", data={"strength": "all", "sort": "proximity"}),
    html.Button("All", id="filter-all-btn", n_clicks=0, className="filter-chip active"),
    html.Button("Strong Buy", id="filter-strong-btn", n_clicks=0, className="filter-chip"),
    html.Button("Buy", id="filter-buy-btn", n_clicks=0, className="filter-chip"),
    html.Div([
        html.Span("Sort:", className="sort-label"),
        dcc.Dropdown(
            id="mobile-sort-dropdown",
            options=[
                {"label": "Proximity", "value": "proximity"},
                {"label": "Symbol", "value": "symbol"},
                {"label": "Strength", "value": "strength"},
            ],
            value="proximity",
            clearable=False,
            style={"minWidth": "120px"},
        ),
    ], className="sort-control"),
])
```

Filtering + sorting is done client-side (JS) on the rendered cards — no new server callback needed.

---

## Phase 3 — State Polish

### Files to add in Phase 3

| File | Action |
|------|--------|
| `assets/offline.js` | New — offline banner |
| `app.py` | Add `dcc.Store('last-refresh-ts')`, `dcc.Interval('live-tick-interval')`, LIVE pill callback |
| `modules/v20_callbacks.py` | Add `Output('last-refresh-ts', 'data')` to existing refresh callback |

### 3a. Skeleton/shimmer loaders

```css
@media (prefers-reduced-motion: no-preference) {
  @keyframes shimmer {
    from { background-position: -200% 0; }
    to   { background-position:  200% 0; }
  }
}

.skeleton-card {
  background: linear-gradient(
    90deg,
    var(--bg-surface) 25%,
    var(--bg-elevated) 50%,
    var(--bg-surface) 75%
  );
  background-size: 200% 100%;
}

@media (prefers-reduced-motion: no-preference) {
  .skeleton-card { animation: shimmer 1.4s ease infinite; }
}
```

Show via `dcc.Loading` wrapper on `#v20-mobile-cards` — Dash adds `._dash-loading` class automatically, then CSS shows skeleton children while loading.

### 3b. Empty and error states

Create consistent empty state cards for:
- **No signals:** "No signals within threshold today. Expand proximity in V20 settings."
- **Market closed:** "Signals refresh Mon–Fri before 8:30 AM IST."
- **Broker not connected:** "Your broker token has expired." + link to Automation tab.
- **Load error:** "Couldn't load signals. Check your connection and try refreshing."

### 3c. Offline banner

```js
// assets/offline.js
function createBanner() {
  const b = document.createElement('div');
  b.id = 'offline-banner';
  b.style.cssText = 'position:fixed;top:0;left:0;right:0;background:var(--accent);color:#000;' +
    'text-align:center;padding:8px;font-size:13px;font-family:var(--font-ui);z-index:9999;' +
    'transform:translateY(-100%);transition:transform 0.2s';
  b.textContent = '● No internet — showing last known data';
  document.body.appendChild(b);
  return b;
}
const banner = createBanner();
window.addEventListener('offline', () => { banner.style.transform = 'translateY(0)'; });
window.addEventListener('online',  () => { banner.style.transform = 'translateY(-100%)'; });
```

### 3d. LIVE connection pill wiring

**In `app.py` layout** — add to the dcc.Store list:
```python
dcc.Store(id='last-refresh-ts', data=None),
dcc.Interval(id='live-tick-interval', interval=1000, n_intervals=0),
```

**In `modules/v20_callbacks.py`** — existing refresh callback gets one more output:
```python
Output('last-refresh-ts', 'data'),   # add alongside existing outputs
# In the callback body, return: int(datetime.now().timestamp() * 1000)
```

**In `app.py`** — clientside callback for the pill:
```python
app.clientside_callback(
    """
    function(n, ts) {
        if (!ts) return '● connecting';
        const diff = Math.round((Date.now() - ts) / 1000);
        if (diff < 10)  return '● LIVE · ' + diff + 's';
        if (diff < 30)  return '◑ ' + diff + 's ago';
        return '○ stale · ' + diff + 's';
    }
    """,
    Output('connection-pill', 'children'),
    Input('live-tick-interval', 'n_intervals'),
    State('last-refresh-ts', 'data'),
)
```

CSS for pill states:
```css
#connection-pill { font-family: var(--font-mono); font-size: 11px; }
/* The text content drives state — no extra class needed */
/* "● LIVE" → green via CSS attr selector on content is unreliable; use JS to add class */
```

---

## Phase 4 — Differentiators

### 4a. Inline sparklines (7-day price SVG)

**In `modules/v20_callbacks.py`**, inside existing callback that already calls `yf.download()`:

```python
def _sparkline_svg(closes: list) -> str:
    """Generate a minimal 60x20 SVG polyline from a list of close prices."""
    import math
    # Drop NaN values before processing
    closes = [c for c in closes if c and not math.isnan(c)]
    if len(closes) < 2:
        return ""
    mn, mx = min(closes), max(closes)
    if mx == mn:
        return ""
    w, h = 60, 20
    pts = []
    for i, c in enumerate(closes):
        x = round(i / (len(closes) - 1) * w, 1)
        y = round((1 - (c - mn) / (mx - mn)) * h, 1)
        pts.append(f"{x},{y}")
    color = "#10d9aa" if closes[-1] >= closes[0] else "#ff5a6e"
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
            f'</svg>')
```

Fetch the last 7 closes from the existing 6-month yfinance window (already downloaded for MACD). No new API call.

### 4b. Pull-to-refresh

```js
// assets/pull_refresh.js
// Triggers the existing refresh button when user pulls down from top of page.
// No Dash callback plumbing needed — Dash sees a button click, same as user clicking it.
let startY = 0, pulling = false;

document.addEventListener('touchstart', e => {
  startY = e.touches[0].clientY;
  pulling = window.scrollY === 0;
}, { passive: true });

document.addEventListener('touchend', e => {
  if (!pulling) return;
  const diff = e.changedTouches[0].clientY - startY;
  if (diff > 80) {
    document.getElementById('refresh-v20-live-data-button')?.click();
  }
  pulling = false;
}, { passive: true });

// Cancel on scroll (prevents accidental triggers while scrolling)
document.addEventListener('touchmove', () => { pulling = false; }, { passive: true });
```

**Visual feedback (add in Phase 4):** A 20-line CSS indicator that translates down with pull distance using `touchmove` delta. Without it, the gesture feels broken. Plan for it but it's not MVP.

### 4c. Long-press bottom sheet (View Details only — NO GTT creation)

**Why "no GTT creation":** Creating a GTT requires calling `user_store.upsert_*` and broker APIs. That is the data layer, which is out of scope per project constraints.

```js
// Part of a larger mobile-interactions.js
let longPressTimer = null;

document.addEventListener('touchstart', e => {
  const card = e.target.closest('.signal-card');
  if (!card) return;
  const symbol = card.dataset.symbol;
  longPressTimer = setTimeout(() => openDetailSheet(symbol), 300);
}, { passive: true });

document.addEventListener('touchend', () => {
  clearTimeout(longPressTimer);
}, { passive: true });

document.addEventListener('touchmove', () => {
  clearTimeout(longPressTimer);   // scroll cancels long-press
}, { passive: true });
```

CSS for bottom sheet:
```css
.detail-sheet {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  background: var(--bg-elevated);
  border-radius: var(--r-lg) var(--r-lg) 0 0;
  border-top: 1px solid var(--border);
  padding: var(--sp-6);
  padding-bottom: calc(var(--sp-6) + env(safe-area-inset-bottom, 16px));
  transform: translateY(100%);
  transition: transform 0.25s ease;
  z-index: 1100;
  max-height: 75dvh;
  overflow-y: auto;
  touch-action: pan-y;   /* important: allows scrolling inside sheet */
}

.detail-sheet.open { transform: translateY(0); }
```

---

## Implementation order and rules

1. **Always ship Phase N before starting Phase N+1.** Each phase is self-contained and reversible.
2. **Phase 1 is purely additive CSS.** If anything breaks visually, revert `dashboard.css` only.
3. **Never change a Dash callback ID.** Other parts of the app depend on IDs like `strategy-tabs`, `kite-settings-loaded` etc.
4. **Never import a JS library.** All JS is vanilla, loaded via `/assets/`. Dash auto-loads everything in that folder.
5. **Always wrap animations in `prefers-reduced-motion`.** No exceptions.
6. **NSE holiday list in `market_state.js` must be reviewed each December** — add the comment.
7. **Signal count badge caps at 99+.** If `count >= 100`, display `"99+"` not `"147"`.
8. **`font-variant-numeric: tabular-nums`** on every element that shows a price or percentage. No exceptions.

---

## What does NOT change (hard constraints)

| Category | Constraint |
|----------|-----------|
| Supabase schema | Zero changes |
| `user_store.py` | Zero changes |
| `scheduler.py` | Zero changes |
| `kite/`, `groww/` broker modules | Zero changes |
| Any `_get`, `_post`, `_patch`, `_upsert` call | Zero changes |
| Dash callback IDs | Zero changes — existing IDs are sacred |
| `dcc.Tabs` values (`tab-v20`, `tab-breakout`, etc.) | Zero changes — GitHub Actions and OAuth redirects depend on them |

---

## Quick reference: key existing IDs to know

```
strategy-tabs              — the main dcc.Tabs component
tab-v20                    — V20 tab value
tab-breakout               — Breakout tab value  
tab-kite-settings          — Broker Automation tab value
tab-admin                  — Admin tab value
refresh-v20-live-data-button — existing refresh button (pull-to-refresh .click()s this)
kite-settings-loaded       — existing dcc.Store (broker connected state)
kite-oauth-result          — existing dcc.Store
active-broker-store        — existing dcc.Store (zerodha/groww/null)
```

---

*Plan version: final. Last updated: 2026-06-06. Start with Phase 1.*
