"""
Builds the public monthly pages under docs/fuel-price/ (one per pump-price
change, e.g. /fuel-price/october-2026/, plus a forecast page for the next one
and a history index at /fuel-price/) and rewrites docs/sitemap.xml to list them.

publish.py calls build() after writing docs/data/status.json, so new months
appear on their own; it can also be run by hand: `python month_pages.py`.
Nothing here feeds the prediction, and a failure never stops a publish.

Past months come from the CEF reports cached in data/bfp.db, so they are
CEF's own figures. The forecast page is a snapshot of status.json, refreshed
only when CEF publishes a new report (kept in data/month_pages_forecast.json),
so the pages don't change every hour. Files are only rewritten when their
content changes, and the sitemap's lastmod moves only for those.
"""
import datetime as dt
import html
import json
import re
from collections import OrderedDict
from pathlib import Path

import bfp_model as bm
import db

REPO_ROOT = Path(__file__).parent.parent
DOCS = REPO_ROOT / "docs"
OUT_DIR = DOCS / "fuel-price"
STATUS_PATH = DOCS / "data" / "status.json"
SITEMAP_PATH = DOCS / "sitemap.xml"
SNAPSHOT_PATH = REPO_ROOT / "data" / "month_pages_forecast.json"
SITE = "https://fuel.psyphin.co.za"

FUELS = ["petrol95", "petrol93", "diesel005", "diesel0005", "illpar"]
FUEL_NAMES = {
    "petrol95": "Petrol 95",
    "petrol93": "Petrol 93",
    "diesel005": "Diesel 0.05% sulphur",
    "diesel0005": "Diesel 0.005% sulphur",
    "illpar": "Illuminating paraffin",
}
# The same price rows the main page shows (docs/app.js PRICE_ROW_LABEL).
PRICE_KIND = {
    "petrol95": "Gauteng pump price",
    "petrol93": "Gauteng pump price",
    "diesel005": "wholesale price",
    "diesel0005": "wholesale price",
    "illpar": "national maximum retail price",
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CEF_URL = "https://cefgroup.co.za/daily-basic-fuel-price/"
DESC_MAX = 155


# ---------- formatting ----------

def esc(s) -> str:
    return html.escape(str(s), quote=True)


def d_long(d: dt.date) -> str:
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def d_short(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def month_name(d: dt.date) -> str:
    return f"{MONTHS[d.month - 1]} {d.year}"


def slug(d: dt.date) -> str:
    return f"{MONTHS[d.month - 1].lower()}-{d.year}"


def rand(c: float) -> str:
    return f"R{c / 100:.2f}"


def amount(c: float) -> str:
    """A change's size: 28c, R3.33."""
    c = abs(c)
    return f"{round(c)}c" if c < 99.5 else rand(c)


def change_words(c: float) -> str:
    """up R3.33 / down 28c / unchanged"""
    if abs(c) < 0.5:
        return "unchanged"
    return ("up " if c > 0 else "down ") + amount(c)


def about(c: float) -> str:
    """up about R1.37 / about unchanged"""
    return "about unchanged" if abs(c) < 0.5 else change_words(c).replace(" ", " about ", 1)


def signed(c: float) -> str:
    if abs(c) < 0.5:
        return "0c"
    return ("+" if c > 0 else "−") + amount(c)


def direction(c: float) -> str:
    return "flat" if abs(c) < 0.5 else ("increase" if c > 0 else "decrease")


def trim_desc(text: str) -> str:
    """Meta descriptions over DESC_MAX are cut back to their last full sentence."""
    while len(text) > DESC_MAX and ". " in text:
        text = text[: text.rstrip(".").rfind(". ") + 1]
    return text[:DESC_MAX]


# ---------- data ----------

def load_cycles() -> list:
    """CEF's cached reports grouped by the pump price in force (oldest first).
    Each cycle: effective date, the last report with every price (CEF sometimes
    corrects a price in a later report, so the last one wins), the last report
    (its period average is final once the next cycle exists) and the exchange
    rates seen, if the cache holds the whole review period."""
    reports = db.get_cached_reports(dt.date(2000, 1, 1), dt.date.today())
    groups = OrderedDict()
    for r in reports:
        groups.setdefault(r["pump_price_effective"], []).append(r)
    cycles = []
    for eff, rs in groups.items():
        priced = [r for r in rs if all(r.get("current_price", {}).get(f) is not None for f in FUELS)]
        if not priced:
            continue
        rates = [r["exchange_rate"] for r in rs if r.get("exchange_rate")]
        cycles.append({
            "effective": dt.date.fromisoformat(eff),
            "prices": priced[-1]["current_price"],
            "last": rs[-1],
            "complete": rs[0]["report_date"] == rs[0]["period_start"],
            "avg_rate": sum(rates) / len(rates) if rates else None,
        })
    return cycles


def build_months(cycles: list) -> list:
    """One entry per price change we have the before and after prices for."""
    months = []
    for prev, cur in zip(cycles, cycles[1:]):
        closing = prev["last"]
        months.append({
            "effective": cur["effective"],
            "old": prev["prices"],
            "new": cur["prices"],
            "change": {f: cur["prices"][f] - prev["prices"][f] for f in FUELS},
            "period_start": dt.date.fromisoformat(closing["period_start"]),
            "period_end": dt.date.fromisoformat(closing["period_end"]),
            "avg_over_under": closing["avg_over_under"],
            "avg_bfp": closing["avg_bfp"],
            "prev_effective": prev["effective"],
            "avg_rate": prev["avg_rate"] if prev["complete"] else None,
        })
    for older, m in zip([None] + months, months):
        m["prev_rate"] = older["avg_rate"] if older else None
    return months


def forecast_snapshot(status: dict):
    """The forecast as of CEF's latest report. Kept until a new report (or the
    period closing) changes it, so the pages don't churn with every hourly run."""
    key = [status["latest_official_report"]["report_date"], status["predicted_change_date"],
           status["review_period_closed"]]
    try:
        saved = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        if saved.get("key") == key:
            return saved
    except (OSError, ValueError):
        pass
    preds = status["predictions"]
    snap = {
        "key": key,
        "report_date": status["latest_official_report"]["report_date"],
        "effective": status["predicted_change_date"],
        "period_start": status["latest_official_report"]["period_start"],
        "period_close": status["review_period_close"],
        "closed": status["review_period_closed"],
        "official_days": preds["petrol95"]["official_days_count"],
        "current": {f: preds[f]["current_price_c_per_l"] for f in FUELS},
        "change": {f: preds[f]["predicted_pump_price_change_c_per_l"] for f in FUELS},
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


# ---------- page parts ----------

def style_version() -> str:
    m = re.search(r'style\.css\?v=(\d+)', (DOCS / "index.html").read_text(encoding="utf-8"))
    return m.group(1) if m else "1"


EXTRA_CSS = """
.month-nav { display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; margin: 0 0 20px; font-size: 14px; }
.month-nav > :last-child { text-align: right; }
.month-nav a, .prose a, .site-footer a { color: var(--brand); }
.prose p { margin: 0 0 12px; max-width: 75ch; color: var(--text-secondary); line-height: 1.6; }
.prose p:last-child { margin-bottom: 0; }
.prose strong { color: var(--text-primary); }
.hero-card .hero-label { margin-bottom: 6px; }
td.up { color: var(--status-critical); }
td.down { color: var(--delta-up-good); }
.price-chart { width: 100%; height: auto; display: block; }
.price-chart text { fill: var(--text-muted); font-size: 12px; font-family: inherit; }
.chart-key { display: flex; gap: 4px 18px; font-size: 13px; color: var(--text-secondary); margin-top: 8px; }
.chart-key { flex-wrap: wrap; }
.chart-key span::before { content: ""; display: inline-block; width: 14px; height: 3px; margin-right: 6px; vertical-align: middle; background: currentColor; }
@media (min-width: 761px) { .hero { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) {
  .month-table th, .month-table td { padding: 9px 6px; font-size: 13px; }
  .month-table th { font-size: 11px; letter-spacing: 0.02em; }
  .month-table td:first-child { white-space: normal; }
  .price-chart text { font-size: 26px; }
}
"""


def page(path: str, title: str, desc: str, h1: str, eyebrow: str, subtitle: str, body: str,
         crumbs: list) -> str:
    """crumbs: [(name, path)], the last being this page."""
    url = SITE + path
    ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": SITE + p}
            for i, (name, p) in enumerate(crumbs)
        ],
    }
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" type="image/png" sizes="96x96" href="/assets/favicon-96x96.png">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/favicon-192x192.png">
<link rel="apple-touch-icon" sizes="180x180" href="/assets/apple-touch-icon.png">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="https://psyphin.co.za/assets/img/projects/fuel-chart.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#000000">
<meta name="color-scheme" content="dark">
<script type="application/ld+json">
{json.dumps(ld, indent=2)}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css?v={style_version()}">
<style>{EXTRA_CSS}</style>
</head>
<body>
<header class="brand-bar">
  <nav class="back-nav" aria-label="Site">
    <a href="/" class="back-link"><span class="back-link-arrow" aria-hidden="true">&larr;</span> Live fuel price forecast <span class="back-link-domain">fuel.psyphin.co.za</span></a>
  </nav>
  <div class="brand-inner">
    <img src="/assets/logo.jpg" alt="PsyPhin" class="brand-logo" width="560" height="501">
    <div class="brand-text">
      <p class="brand-eyebrow">{esc(eyebrow)}</p>
      <h1>{esc(h1)}</h1>
      <p class="subtitle">{subtitle}</p>
    </div>
  </div>
</header>

<div class="page">
<main>
{body}
</main>
</div>

<footer class="site-footer">PsyPhin &middot; Source data: Central Energy Fund (CEF) daily Basic Fuel Price reports &middot; <a href="/">Next month's fuel price forecast</a> &middot; <a href="/fuel-price/">Fuel price history</a></footer>

<!-- GoatCounter is shared with psyphin.co.za; prefix paths with the host so this site is counted separately -->
<script>window.goatcounter = {{ path: function (p) {{ return location.host + p; }} }};</script>
<script data-goatcounter="https://psyphin.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>
"""


def hero(cards: list) -> str:
    """cards: [(label, change_c, sub)]"""
    out = []
    for label, c, sub in cards:
        out.append(f"""  <div class="hero-card">
    <div class="hero-label">{esc(label)}</div>
    <div class="hero-value {direction(c)}">{signed(c)}</div>
    <div class="hero-sub">{sub}</div>
  </div>""")
    return '<section class="hero">\n' + "\n".join(out) + "\n</section>"


def price_table(old: dict, new: dict, change: dict, new_head: str, approx: bool = False) -> str:
    rows = []
    for f in FUELS:
        cls = {"increase": "up", "decrease": "down"}.get(direction(change[f]), "")
        tilde = "~" if approx else ""
        rows.append(
            f'<tr><td>{esc(FUEL_NAMES[f])}<br><span class="muted small">{esc(PRICE_KIND[f].capitalize())}</span></td>'
            f'<td class="num">{rand(old[f])}</td><td class="num {cls}">{signed(change[f])}</td>'
            f'<td class="num">{tilde}{rand(new[f])}</td></tr>')
    return f"""<div class="table-wrap">
<table class="month-table">
<thead><tr><th>Fuel, per litre</th><th class="num">Before</th><th class="num">Change</th><th class="num">{esc(new_head)}</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</div>"""


def drivers(m: dict) -> str:
    """Why it moved: the review period's average over/(under) recovery against
    the announced change, for petrol 95 and diesel 0.05%."""
    paras = []
    period = f"from {d_long(m['period_start'])} to {d_long(m['period_end'])}"
    paras.append(
        f"<p>Each month's change is set by the <strong>review period</strong> before it, here {period}. "
        f"Every day of it, CEF compares what fuel actually cost to import (the Basic Fuel Price) with the cost "
        f"already built into the pump price. The period's average gap, the over- or under-recovery, is how much "
        f"the price has to move to catch up.</p>")
    for f in ("petrol95", "diesel005"):
        ou = m["avg_over_under"].get(f)
        if ou is None:
            continue
        market, actual = -ou, m["change"][f]
        name = "Petrol 95" if f == "petrol95" else "Diesel (0.05% sulphur)"
        if abs(ou) < 0.5:
            gap = "cost the same to import, on average, as was built into the price"
        elif ou < 0:
            gap = f"cost on average {amount(ou)} a litre <strong>more</strong> to import than was built into the price (an under-recovery)"
        else:
            gap = f"cost on average {amount(ou)} a litre <strong>less</strong> to import than was built into the price (an over-recovery)"
        bfp = m["avg_bfp"].get(f)
        bfp_txt = f" Its import cost averaged {rand(bfp)} a litre." if bfp else ""
        diff = actual - market
        if abs(diff) < 9.5:
            verdict = (f"On its own that called for a change of {signed(market)}; the official change, "
                       f"{signed(actual)}, was within a few cents of it.")
        else:
            verdict = (f"On its own that called for a change of {signed(market)}. The official change was "
                       f"{signed(actual)}, {amount(diff)} {'more' if diff > 0 else 'less'}: the rest comes from "
                       f"decisions outside the Basic Fuel Price, such as slate-levy and fuel-levy changes, which "
                       f"the government's announcement sets out.")
        paras.append(f"<p><strong>{name}</strong> {gap}.{bfp_txt} {verdict}</p>")
    if m["avg_rate"]:
        rate = f"The rand averaged R{m['avg_rate']:.2f} to the US dollar over the period"
        if m["prev_rate"]:
            delta = m["avg_rate"] - m["prev_rate"]
            if abs(delta) >= 0.05:
                rate += (f", {'weaker' if delta > 0 else 'stronger'} than the R{m['prev_rate']:.2f} of the period before"
                         f" ({'a weaker rand pushes fuel prices up' if delta > 0 else 'a stronger rand pulls fuel prices down'})")
            else:
                rate += f", about the same as the period before (R{m['prev_rate']:.2f})"
        paras.append(f"<p>{rate}.</p>")
    paras.append(f'<p class="muted small">Figures from CEF\'s daily Basic Fuel Price reports '
                 f'(<a href="{CEF_URL}" target="_blank" rel="noopener">cefgroup.co.za</a>): prices from its '
                 f'pump, wholesale and maximum retail price rows, the averages from the last report of the period.</p>')
    return "\n".join(paras)


def month_nav(prev_m, next_m) -> str:
    left = (f'<a href="/fuel-price/{slug(prev_m)}/">&larr; {month_name(prev_m)}</a>' if prev_m else "<span></span>")
    mid = '<a href="/fuel-price/">All months</a>'
    right = (f'<a href="/fuel-price/{slug(next_m)}/">{month_name(next_m)} &rarr;</a>' if next_m else "<span></span>")
    return f'<nav class="month-nav" aria-label="Months">{left}{mid}{right}</nav>'


def month_page(m: dict, prev_m, next_m, today: dt.date) -> str:
    e = m["effective"]
    future = e > today
    ch, new = m["change"], m["new"]
    p95, d05 = ch["petrol95"], ch["diesel005"]
    name = month_name(e)
    title = f"Fuel Price {name}: Petrol {change_words(p95)}, Diesel {change_words(d05)}"
    def moves(c, unit=""):
        if abs(c) < 0.5:
            return "stays at" if future else "stayed at"
        return f"{'goes' if future else 'went'} {change_words(c)}{unit} to"

    desc = trim_desc(
        f"South Africa's fuel price from {d_short(e)}: petrol 95 {change_words(p95)} to {rand(new['petrol95'])} "
        f"a litre in Gauteng, diesel {change_words(d05)}. What drove it, from CEF's data.")
    intro = (f"From {d_long(e)}, petrol 95 {moves(p95, ' a litre')} {rand(new['petrol95'])} in Gauteng, and the "
             f"wholesale price of diesel (0.05% sulphur) {moves(d05)} {rand(new['diesel005'])}.")
    if future:
        intro += " The new prices are already in CEF's daily reports ahead of the date."
    body = f"""{month_nav(prev_m, next_m)}
{hero([
    ("Petrol 95", p95, f"New price {rand(new['petrol95'])} a litre (Gauteng)"),
    ("Diesel 0.05%", d05, f"New price {rand(new['diesel005'])} a litre (wholesale)"),
])}
<section class="panel prose">
<p>{intro}</p>
</section>
<section class="panel">
<div class="panel-head"><h2>All fuels, {esc(d_short(e))}</h2>
<p class="muted small">Gauteng pump prices for petrol; coastal prices are lower by the cost of transport inland. Diesel and paraffin have no single pump price, so these are CEF's wholesale and maximum retail price rows.</p></div>
{price_table(m['old'], new, ch, 'After')}
</section>
<section class="panel prose">
<div class="panel-head"><h2>What moved it</h2></div>
{drivers(m)}
</section>
<section class="panel disclaimer">
<h2>The next change</h2>
<p>The price changes on the first Wednesday of every month. The <a href="/">live forecast</a> shows where the next one is heading, worked out from CEF's reports every day, and the <a href="/fuel-price/">fuel price history</a> has every month's change.</p>
</section>"""
    return page(f"/fuel-price/{slug(e)}/", title, desc, f"Fuel price {name}",
                "South Africa · Monthly fuel price change",
                f"The petrol, diesel and paraffin price change of {esc(d_long(e))}, and what drove it.",
                body, [("Fuel price forecast", "/"), ("Fuel price history", "/fuel-price/"),
                       (f"Fuel price {name}", f"/fuel-price/{slug(e)}/")])


def forecast_page(s: dict, prev_m) -> str:
    e = dt.date.fromisoformat(s["effective"])
    report = dt.date.fromisoformat(s["report_date"])
    start = dt.date.fromisoformat(s["period_start"])
    close = dt.date.fromisoformat(s["period_close"])
    ch, cur = s["change"], s["current"]
    new = {f: cur[f] + ch[f] for f in FUELS}
    p95, d05 = ch["petrol95"], ch["diesel005"]
    name = month_name(e)
    total = bm.business_days_between(start, close)
    title = f"Fuel Price {name}: Petrol and Diesel Forecast"
    desc = trim_desc(
        f"Forecast of South Africa's fuel price change on {d_short(e)}: petrol 95 {about(p95)}, "
        f"diesel {about(d05)}, from CEF's daily data. Updated every weekday.")
    if s["closed"]:
        sure = (f"The review period closed on {d_long(close)}, so CEF's figures for the whole period are in or "
                f"nearly in. The official announcement can still differ by any slate-levy or fuel-levy change.")
    else:
        sure = (f"The review period runs from {d_long(start)} to {d_long(close)}. CEF has published "
                f"{s['official_days']} of its {total} days so far; the rest assume the Basic Fuel Price stays where "
                f"it is now, so the figure can still move a lot before the period closes. It leaves out any "
                f"slate-levy or fuel-levy change, which the official announcement adds.")
    body = f"""{month_nav(prev_m, None)}
{hero([
    ("Petrol 95, forecast", p95, f"About {rand(new['petrol95'])} a litre (Gauteng)"),
    ("Diesel 0.05%, forecast", d05, f"About {rand(new['diesel005'])} a litre (wholesale)"),
])}
<section class="panel prose">
<p>South Africa's next fuel price change takes effect on <strong>{esc(d_long(e))}</strong>. On CEF's figures up to its report of {esc(d_long(report))}, petrol 95 is heading {'for no change' if abs(p95) < 0.5 else change_words(p95) + ' a litre'} and diesel (0.05% sulphur) {'for no change' if abs(d05) < 0.5 else change_words(d05)}.</p>
<p>{sure}</p>
<p>This page is updated each weekday when CEF publishes a new report. The <a href="/">live forecast</a> is updated every hour, with charts and every day of the period.</p>
</section>
<section class="panel">
<div class="panel-head"><h2>All fuels, forecast for {esc(d_short(e))}</h2>
<p class="muted small">Before any slate-levy or fuel-levy change. Gauteng pump prices for petrol; CEF's wholesale and maximum retail price rows for diesel and paraffin.</p></div>
{price_table(cur, new, ch, 'Forecast', approx=True)}
</section>"""
    return page(f"/fuel-price/{slug(e)}/", title, desc, f"Fuel price {name}: forecast",
                "South Africa · Next fuel price change",
                f"Where the petrol, diesel and paraffin price is heading on {esc(d_long(e))}, from CEF's daily reports.",
                body, [("Fuel price forecast", "/"), ("Fuel price history", "/fuel-price/"),
                       (f"Fuel price {name}", f"/fuel-price/{slug(e)}/")])


def price_chart(months: list) -> str:
    """Step chart of the petrol 95 (Gauteng) and diesel 0.05% (wholesale) price."""
    pts = [(m["effective"], m["new"]["petrol95"], m["new"]["diesel005"]) for m in months]
    if len(pts) < 2:
        return ""
    w, h, left, right, top, bottom = 720, 300, 64, 12, 16, 40
    lo = min(min(p[1], p[2]) for p in pts)
    hi = max(max(p[1], p[2]) for p in pts)
    span = hi - lo
    unit = 200 if span <= 800 else 400 if span <= 2000 else 1000
    lo, hi = (lo // unit) * unit, (hi // unit + 1) * unit
    t0, t1 = pts[0][0].toordinal(), pts[-1][0].toordinal() + 30

    def x(d):
        return left + (d - t0) / (t1 - t0) * (w - left - right)

    def y(c):
        return top + (hi - c) / (hi - lo) * (h - top - bottom)

    def line(i):
        """Flat until the next change, then a step: the price holds for the month."""
        path = f"M{x(pts[0][0].toordinal()):.1f},{y(pts[0][i]):.1f}"
        for p in pts[1:]:
            path += f"H{x(p[0].toordinal()):.1f}V{y(p[i]):.1f}"
        return path + f"H{x(t1):.1f}"

    grid = []
    step = unit
    c = lo
    while c <= hi:
        grid.append(f'<line x1="{left}" x2="{w - right}" y1="{y(c):.1f}" y2="{y(c):.1f}" style="stroke:var(--gridline)"/>'
                    f'<text x="{left - 8}" y="{y(c):.1f}" dominant-baseline="middle" text-anchor="end">R{c / 100:.0f}</text>')
        c += step
    labels = [f'<text x="{x(pts[0][0].toordinal()):.1f}" y="{h - 8}">{MONTHS[pts[0][0].month - 1][:3]} {pts[0][0].year}</text>',
              f'<text x="{x(t1):.1f}" y="{h - 8}" text-anchor="end">{MONTHS[pts[-1][0].month - 1][:3]} {pts[-1][0].year}</text>']
    return f"""<svg class="price-chart" viewBox="0 0 {w} {h}" role="img" aria-label="Petrol 95 and diesel price by month, {esc(month_name(pts[0][0]))} to {esc(month_name(pts[-1][0]))}">
{''.join(grid)}
<path d="{line(1)}" fill="none" style="stroke:var(--series-blue)" stroke-width="2.5"/>
<path d="{line(2)}" fill="none" style="stroke:var(--series-orange)" stroke-width="2.5"/>
{''.join(labels)}
</svg>
<div class="chart-key"><span style="color:var(--series-blue)">Petrol 95 (Gauteng pump price)</span><span style="color:var(--series-orange)">Diesel 0.05% (wholesale)</span></div>"""


def index_page(months: list, snap) -> str:
    rows = []
    if snap:
        e = dt.date.fromisoformat(snap["effective"])
        ch = snap["change"]
        rows.append(
            f'<tr><td><a href="/fuel-price/{slug(e)}/">{month_name(e)}</a><br><span class="muted small">Forecast</span></td>'
            f'<td class="num">{signed(ch["petrol95"])}<br><span class="muted small">~{rand(snap["current"]["petrol95"] + ch["petrol95"])}</span></td>'
            f'<td class="num">{signed(ch["diesel005"])}<br><span class="muted small">~{rand(snap["current"]["diesel005"] + ch["diesel005"])}</span></td></tr>')
    for m in reversed(months):
        e = m["effective"]
        rows.append(
            f'<tr><td><a href="/fuel-price/{slug(e)}/">{month_name(e)}</a><br><span class="muted small">{d_short(e)}</span></td>'
            f'<td class="num">{signed(m["change"]["petrol95"])}<br><span class="muted small">{rand(m["new"]["petrol95"])}</span></td>'
            f'<td class="num">{signed(m["change"]["diesel005"])}<br><span class="muted small">{rand(m["new"]["diesel005"])}</span></td></tr>')
    first, last = months[0]["effective"], months[-1]["effective"]
    p_first, p_last = months[0]["old"]["petrol95"], months[-1]["new"]["petrol95"]
    title = "SA Fuel Price History: Monthly Petrol and Diesel Price Changes"
    desc = trim_desc(
        f"Every South African petrol and diesel price change since {month_name(first)}, with what drove each one, "
        f"from CEF's daily Basic Fuel Price reports.")
    body = f"""<section class="panel prose">
<p>South Africa's fuel price changes on the first Wednesday of every month. Petrol 95 in Gauteng went from {rand(p_first)} a litre before the {month_name(first)} change to {rand(p_last)} after {month_name(last)}'s. Each month below has its own page with every fuel's price and what moved it.</p>
</section>
<section class="panel">
<div class="panel-head"><h2>Price by month</h2></div>
{price_chart(months)}
</section>
<section class="panel">
<div class="panel-head"><h2>Every change</h2>
<p class="muted small">The change per litre, with the new price under it. Petrol 95 is the Gauteng pump price; diesel 0.05% sulphur is CEF's wholesale price row. The forecast leaves out any slate-levy or fuel-levy change.</p></div>
<div class="table-wrap">
<table class="month-table">
<thead><tr><th>Month</th><th class="num">Petrol 95</th><th class="num">Diesel 0.05%</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</div>
</section>
<section class="panel disclaimer">
<h2>Where the figures come from</h2>
<p>CEF's daily Basic Fuel Price reports (<a href="{CEF_URL}" target="_blank" rel="noopener">cefgroup.co.za</a>), which carry the price in force and the running average over- or under-recovery that sets the next change. The <a href="/">live forecast</a> shows where next month's price is heading.</p>
</section>"""
    return page("/fuel-price/", title, desc, "South African fuel price history",
                "South Africa · Monthly fuel price changes",
                f"Every petrol and diesel price change since {month_name(first)}, from CEF's daily reports.",
                body, [("Fuel price forecast", "/"), ("Fuel price history", "/fuel-price/")])


# ---------- writing ----------

def write_if_changed(path: Path, text: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def write_sitemap(urls: list, changed: set, today: dt.date) -> bool:
    """urls: site paths, home first. lastmod: today for changed pages, otherwise
    whatever the sitemap already said (the home page's is kept as it is)."""
    old = {}
    try:
        for loc, mod in re.findall(r"<loc>(.*?)</loc><lastmod>(.*?)</lastmod>",
                                   SITEMAP_PATH.read_text(encoding="utf-8")):
            old[loc] = mod
    except OSError:
        pass
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in urls:
        loc = SITE + p
        mod = today.isoformat() if p in changed or loc not in old else old[loc]
        lines.append(f"  <url><loc>{loc}</loc><lastmod>{mod}</lastmod></url>")
    lines.append("</urlset>")
    return write_if_changed(SITEMAP_PATH, "\n".join(lines) + "\n")


def build(today: dt.date = None) -> list:
    """Builds every page; returns the repo-relative paths it changed."""
    today = today or dt.date.today()
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    months = build_months(load_cycles())
    if not months:
        print("month_pages: no complete months in the report cache; nothing written.")
        return []
    snap = forecast_snapshot(status)
    if dt.date.fromisoformat(snap["effective"]) <= months[-1]["effective"]:
        snap = None  # that month's prices are already in CEF's reports

    pages = {}
    for i, m in enumerate(months):
        prev_m = months[i - 1]["effective"] if i else None
        next_m = months[i + 1]["effective"] if i + 1 < len(months) else (
            dt.date.fromisoformat(snap["effective"]) if snap else None)
        pages[f"/fuel-price/{slug(m['effective'])}/"] = month_page(m, prev_m, next_m, today)
    if snap:
        pages[f"/fuel-price/{slug(dt.date.fromisoformat(snap['effective']))}/"] = forecast_page(snap, months[-1]["effective"])
    pages["/fuel-price/"] = index_page(months, snap)

    # Never drop a page that's already published (e.g. if the local cache were lost).
    existing = {f"/fuel-price/{d.name}/" for d in OUT_DIR.iterdir() if d.is_dir()} if OUT_DIR.exists() else set()
    missing = existing - set(pages)
    if missing:
        print(f"month_pages: the cache no longer covers {sorted(missing)}; nothing written.")
        return []

    changed = set()
    for p, text in pages.items():
        if write_if_changed(DOCS / p.strip("/") / "index.html", text):
            changed.add(p)
    month_urls = sorted((p for p in pages if p != "/fuel-price/"),
                        key=lambda p: (int(p.strip("/").split("-")[-1]), MONTHS.index(p.strip("/").split("/")[-1].split("-")[0].capitalize())),
                        reverse=True)
    paths = [f"docs{p}index.html" for p in sorted(changed)]
    if write_sitemap(["/", "/fuel-price/"] + month_urls, changed, today):
        paths.append("docs/sitemap.xml")
    return paths


if __name__ == "__main__":
    for p in build():
        print("wrote", p)
