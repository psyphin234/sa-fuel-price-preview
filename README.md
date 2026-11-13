# SA Basic Fuel Price Preview

A local dashboard that previews South Africa's daily Basic Fuel Price (BFP) the
same way the Central Energy Fund (CEF) does it, and turns the running
under/over-recovery into a projection of the next monthly pump-price change.

## How it works

CEF itself publishes a daily BFP report as a PDF at
[cefgroup.co.za/daily-basic-fuel-price](https://cefgroup.co.za/daily-basic-fuel-price/),
usually with about a one-day lag. This tool:

1. **Scrapes and parses CEF's own official daily PDFs** for every day already
   published in the current review period (the period that determines next
   month's price change). This part is exact - it's CEF's own numbers.
2. **Estimates the 1 (occasionally 2) day(s) CEF hasn't published yet** from
   free Yahoo Finance hourly prices (no key required): US RBOB petrol, NY Harbor
   ULSD/heating oil and Brent futures read at 15:00 London - just before the
   London Platts assessment CEF's figures are built from - plus USD/ZAR at
   10:00 London, which is what CEF's exchange rate tracks. How much each market
   counts for each fuel is re-fitted every run on up to the last 250 CEF days
   (`backend/nowcast.py`). In a backtest over Jun 2025 - Sep 2026 this was
   typically within 1.35% of CEF's real figure, vs 2.04% for "no change" and
   2.11% for the original model. It is still a proxy, **not** the real
   Mediterranean Platts assessment, and misses when European prices diverge
   from US markets.
3. **Lets you override the estimate** with a real number if you ever get hold
   of one (a Platts subscription, a trade desk, etc.) - it takes priority over
   the estimate for that date everywhere in the app.
4. Blends CEF's own official period-to-date average with your day(s), and
   the rest of the period at today's level, to project the next monthly
   price move, and shows the estimated new pump
   price alongside the current one.

There is no free, legitimate source for the actual Platts Mediterranean cargo
assessments themselves - that data is a paid S&P Global subscription. This
tool doesn't try to fake that; it just nowcasts the short gap between CEF's
last official day and today.

## Running it

Requires Python 3.10+ (no Node.js needed).

```powershell
.\run.ps1
```

This starts the server in the background with **no window** (through
`backend/run_dashboard_hidden.vbs` → `backend/run_dashboard.ps1`, which installs
the dependencies `flask`, `requests`, `pdfplumber`, `numpy` first) and opens
**http://127.0.0.1:5057** in your browser. Its output goes to
`data/dashboard.log`. Stop it with:

```powershell
.\stop.ps1
```

Or run it in the foreground, with a console:

```powershell
cd backend
pip install -r requirements.txt
python app.py
```

## Project layout

```
backend/
  cef_scraper.py   - fetches + parses CEF's daily PDF reports
  market_data.py    - live Yahoo Finance quotes (Brent, RBOB, ULSD, USD/ZAR)
  context_data.py   - background only, not used by the model: Brent futures
                      (Yahoo) vs. Dated Brent spot (EIA), and Strait of Hormuz
                      ship crossings (IMF PortWatch); cached for 3 hours
  nowcast.py         - estimates unpublished days from hourly market prices,
                       with weights re-fitted on CEF's own history each run
  bfp_model.py       - blended-average prediction logic
  fuel_levy.py       - announced fuel levy and slate levy changes, kept by
                       hand (e.g. the MTBPS relief of Nov 2026 - Jan 2027, the
                       slate levy rise to 135.84c of Nov 2026); added on top of
                       the BFP forecast for the price change they fall on
  forecast_range.py  - the "likely range" around the forecast, from how far
                       the same forecast missed at the same stage of the last
                       12 review periods; and the period's days for the
                       progress strip
  price_drivers.py   - splits the BFP part of a change into fuel prices abroad
                       and the rand, the DMPR's way (live and month pages)
  backtest_fetch.py  - downloads CEF's historical reports for backtesting
  backtest.py        - scores candidate estimation models against that history
  release_times.py   - prints when CEF's reports tend to come out
  db.py               - SQLite: manual overrides, report cache, prediction history
  app.py                - Flask app / API (private, local only)
  publish.py             - standalone script: builds a status snapshot and
                           pushes it to docs/data/status.json on GitHub
  month_pages.py           - builds the monthly pages in docs/fuel-price/ and
                             docs/sitemap.xml (called by publish.py)
  run_publish.ps1          - Task Scheduler wrapper around publish.py, with logging
frontend/
  index.html, style.css, app.js  - the full local dashboard (talks to the Flask
                                   API, has the manual-override form)
docs/
  index.html, style.css, app.js  - the PUBLIC, read-only GitHub Pages build
  context.js                     - the "Oil and the Strait of Hormuz" section
                                   (identical copy in frontend/)
                                   (fetches docs/data/status.json, no backend calls)
  circuit.js                     - the glowing circuit-board background (identical
                                   copy in frontend/ and on psyphin.co.za)
  fx.js                          - decoration only: the import-routes map in the
                                   header, chart-line glow, panels fading in on
                                   scroll (identical copy in frontend/)
  data/status.json                 - the published snapshot (overwritten each run)
  fuel-price/                      - one page per monthly price change, plus a
                                     forecast page and a history index (generated)
data/
  bfp.db      - local SQLite database (created on first run, gitignored)
  publish.log - log of each scheduled publish run (gitignored)
  backtest/   - downloaded history used by the backtest (gitignored)
  context_cache.json - last good copy of the background feeds (gitignored)
  market_cache.json  - last good Yahoo hourly prices, used for up to 24 hours
                       if Yahoo fails, so estimates don't fall back to "no
                       change" (gitignored)
```

## Public site + hourly auto-publish

The dashboard is published as a static, **read-only** site at:

**https://fuel.psyphin.co.za/**

(Older addresses redirect there automatically:
`https://psyphin.co.za/sa-fuel-price-preview/` and
`https://psyphin234.github.io/sa-fuel-price-preview/`. The header has a back
link to https://psyphin.co.za/.)

Source: https://github.com/psyphin234/sa-fuel-price-preview (public repo)

This works without exposing your PC to the internet at all: your PC only ever
makes *outbound* connections (to CEF, Yahoo Finance, and GitHub) to push a
fresh JSON snapshot - it never opens a port, runs a public server, or appears
as an address anywhere. There is nothing for anyone to "find" from the GitHub
repo or the published site; the repo's commit history just shows automated
commits from your GitHub account, same as any scheduled bot would.

A Windows Scheduled Task named **"BFP Preview Publish"** runs
`backend/run_publish.ps1` every hour at about :18, plus every 15 minutes
from 07:00 to 11:00 on weekdays to pick up CEF's morning report quickly
(only while you're logged in - that's Task Scheduler's default and needs no
stored password). The task's action is
`wscript.exe "E:\Claude_projects\BFP_Website\backend\run_publish_hidden.vbs"`,
a tiny launcher that starts the PowerShell script fully hidden: pointing the
task at `powershell.exe -WindowStyle Hidden` directly still flashes a console
window and steals focus. Each run:

1. Re-scrapes CEF's latest PDFs + free market benchmarks
2. Rebuilds `docs/data/status.json`
3. Rebuilds the monthly pages in `docs/fuel-price/` and the sitemap (only
   files whose text changed are rewritten)
4. Commits and pushes them, if anything changed

To manage the task: open **Task Scheduler** → look under the root
`\` folder for "BFP Preview Publish". You can change the interval, pause it,
or run it on demand from there. Its log is at `data/publish.log`.

Manual overrides you enter in the **local** dashboard (http://127.0.0.1:5057)
get baked into the next hourly push automatically - the public site has no
form of its own, since a static site can't accept writes (and a public write
endpoint is exactly the kind of exposure this design avoids).

### Custom domain

The site uses the custom domain **fuel.psyphin.co.za**, set up on 2026-09-27:

- DNS (at Afrihost): `CNAME` record `fuel.psyphin.co.za` → `psyphin234.github.io`.
  Afrihost's form needs the full name `fuel.psyphin.co.za`, not just `fuel`.
  It overrides the zone's `*` wildcard record.
- `docs/CNAME` contains `fuel.psyphin.co.za`. GitHub created it when the domain
  was set in Settings → Pages. **Don't delete it**, or the site falls back to
  psyphin.co.za/sa-fuel-price-preview/.
- "Enforce HTTPS" is on. GitHub issues and renews the certificate automatically.
- If the domain is ever changed in Settings → Pages, GitHub commits a new
  `docs/CNAME`. Run `git pull` straight away, otherwise the hourly publish
  push will fail.

## Limits and honesty notes

- The predicted price change is the review-period average unit over/(under)
  recovery, with the period's remaining business days projected at the latest
  BFP (official or estimated) against the reference CEF will use on each day.
  Without that projection the first days of a period, still measured against
  the old reference, dominated the figure: in Oct 2026 the site showed +R4.56
  for petrol 95 the day before a R3.33 rise took effect, against about +R1.51
  projected. Over 14 periods (Aug 2025 - Oct 2026) the projection roughly
  halved the error against the final average at every stage of the period.
  The real government announcement (effective the first Wednesday
  of the month) also folds in separate slate-levy and fuel-levy decisions
  DMRE can adjust independently, so treat this as directional, not exact.
  Once a fuel levy change is announced, add it to `backend/fuel_levy.py`:
  the site then adds it to the forecast for that price change (the hero
  shows the total and the BFP-only figure; paraffin has no fuel levy).
  The same goes for the slate levy (`SLATE` in that file): the DMPR changes it
  in its monthly announcement, usually a day or two before the change, and the
  model can't foresee it. Enter it once announced and the forecast for that
  date matches the official figure (in Nov 2026 the +48.18c slate rise was the
  whole gap between the forecast and the official change).
  `predicted_pump_price_change_c_per_l` itself stays BFP-only.
- Petrol 93's forecast change is petrol 95's (`FOLLOWS` in `bfp_model.py`):
  the DMPR usually gives inland 93 the same change as 95 (11 of 16 changes
  from Jul 2025 to Nov 2026), not its own over/under-recovery. 93's own
  figures still show in the charts and table.
- The **likely range** under each forecast ("Likely between −R3.40 and
  −R2.60") comes from `backend/forecast_range.py`. For each of the last 12
  finished review periods in the report cache it replays the forecast with
  the same number of days still to come (CEF's figures only, the rest held at
  that day's BFP against the reference CEF used), pooled with the stage either
  side, and takes the miss 80% of them stayed within. Checked walk-forward
  (each period's range built only from earlier ones, Mar - Oct 2026), that
  caught 78% of outcomes, so the site says "about 4 in 5". It covers the BFP
  part only, not a slate-levy change. It's widest early in a period (about
  ±R1 for petrol, ±R2.50 for diesel with 18 days to come) and narrows to a few
  cents in the last days.
- **"What's moving it"** (`price_drivers.py`, `renderDrivers` in both
  `app.js`, and a sentence on each month page) splits the BFP part of the
  change the way the DMPR does: rand part = the period's average BFP ×
  (1 − last period's average R/$ ÷ this period's), product part = the rest.
  The averages are per review period, of CEF's daily exchange rate. It
  reproduced every figure in the DMPR's November 2026 statement to the cent,
  for the grade each was quoted for (the DMPR's "petrol" took its product
  figure from 93 and its rand figure from 95). Live, it counts the estimated
  days and the rest of the period at the latest BFP and rate, like the
  forecast.
- The **"How the forecast adds up"** panel (`renderBreakdown` in both
  `app.js`) shows the period's days (official / estimated / to come), CEF's
  latest official average in words (the figure people quote), and a waterfall
  from that average to the forecast: estimated days, the rest of the period,
  petrol 93 matching 95, then announced fuel and slate levy changes. Hatched
  bars are estimates; the steps add up to the forecast exactly. A hidden table
  gives screen readers the same figures. On screens under 560px the step names
  go above the bars.
- A review period runs from the Friday before one price change (first
  Wednesday of the month) to the Thursday before the next one's Friday, i.e.
  it closes about six days before the change (the Thursday when that Friday is
  a public holiday; checked against every changeover May 2025 - Aug 2026). A
  prediction made early in the period can still move a lot before it closes.
  After it closes the site stops adding estimated days to it, and from the
  first report of the new period CEF already shows the upcoming price. Until
  it takes effect the site leads with that announced change (old price, new
  price and the difference, from the last report of the closed period) and
  shows the next cycle's prediction only as a smaller "early look", since it
  rests on just a few days.
  Those first reports still measure against the old price's BFP contribution,
  and CEF switches on the change date. When estimated days run past that date,
  the site uses the new contribution, derived as the old one less the closed
  period's average over/(under) recovery (within ~1 c/l of CEF's figure).
- CEF publishes a report every weekday, public holidays included (on days
  with no London Platts assessment, e.g. Christmas, it repeats the previous
  figure). Month-end reports are uploaded to the *next* month's folder on
  CEF's site, which the scraper checks too.
- To re-check the model: `python backtest_fetch.py 2025-06-01 <today>` then
  `python backtest.py` (from `backend/`).
- Diesel and illuminating paraffin don't have a single national pump price
  (diesel is wholesale/deregulated, paraffin has a price cap) - the "current
  price" shown for those is CEF's own wholesale / max-retail reference row.
