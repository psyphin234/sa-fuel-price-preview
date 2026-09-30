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
4. Blends CEF's own official period-to-date average with your day(s) to
   project the next monthly price move, and shows the estimated new pump
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

This installs the dependencies (`flask`, `requests`, `pdfplumber`, `numpy`) and
starts the server at **http://127.0.0.1:5057**, opening it in your browser.

Or manually:

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
  nowcast.py         - estimates unpublished days from hourly market prices,
                       with weights re-fitted on CEF's own history each run
  bfp_model.py       - blended-average prediction logic
  backtest_fetch.py  - downloads CEF's historical reports for backtesting
  backtest.py        - scores candidate estimation models against that history
  release_times.py   - prints when CEF's reports tend to come out
  db.py               - SQLite: manual overrides, report cache, prediction history
  app.py                - Flask app / API (private, local only)
  publish.py             - standalone script: builds a status snapshot and
                           pushes it to docs/data/status.json on GitHub
  run_publish.ps1          - Task Scheduler wrapper around publish.py, with logging
frontend/
  index.html, style.css, app.js  - the full local dashboard (talks to the Flask
                                   API, has the manual-override form)
docs/
  index.html, style.css, app.js  - the PUBLIC, read-only GitHub Pages build
                                   (fetches docs/data/status.json, no backend calls)
  data/status.json                 - the published snapshot (overwritten each run)
data/
  bfp.db      - local SQLite database (created on first run, gitignored)
  publish.log - log of each scheduled publish run (gitignored)
  backtest/   - downloaded history used by the backtest (gitignored)
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
`backend/run_publish.ps1` every hour (only while you're logged in - that's
Task Scheduler's default and needs no stored password). Each run:

1. Re-scrapes CEF's latest PDFs + free market benchmarks
2. Rebuilds `docs/data/status.json`
3. Commits and pushes it, if anything changed

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
  recovery. The real government announcement (effective the first Wednesday
  of the month) also folds in separate slate-levy and fuel-levy decisions
  DMRE can adjust independently, so treat this as directional, not exact.
- A review period runs from the Friday before one price change (first
  Wednesday of the month) to the Thursday before the next one's Friday, i.e.
  it closes about six days before the change (the Thursday when that Friday is
  a public holiday; checked against every changeover May 2025 - Aug 2026). A
  prediction made early in the period can still move a lot before it closes.
  After it closes the site stops adding estimated days to it, and from the
  first report of the new period CEF already shows the upcoming price, which
  the site labels "New price from <date>" until it takes effect.
- CEF publishes a report every weekday, public holidays included (on days
  with no London Platts assessment, e.g. Christmas, it repeats the previous
  figure). Month-end reports are uploaded to the *next* month's folder on
  CEF's site, which the scraper checks too.
- To re-check the model: `python backtest_fetch.py 2025-06-01 <today>` then
  `python backtest.py` (from `backend/`).
- Diesel and illuminating paraffin don't have a single national pump price
  (diesel is wholesale/deregulated, paraffin has a price cap) - the "current
  price" shown for those is CEF's own wholesale / max-retail reference row.
