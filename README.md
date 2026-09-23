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
2. **Estimates the 1 (occasionally 2) day(s) CEF hasn't published yet** using
   free market benchmarks - ICE Brent crude, NYMEX RBOB gasoline, NY Harbor
   ULSD futures, and USD/ZAR spot (all via Yahoo Finance's public quote API,
   no key required) - applied as a % move on top of the last official,
   Platts-based figure. This is a same-direction proxy, **not** the real
   Mediterranean Platts assessment, and can drift in volatile weeks.
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

This installs the three dependencies (`flask`, `requests`, `pdfplumber`) and
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
  market_data.py    - free Yahoo Finance benchmarks (Brent, RBOB, ULSD, USD/ZAR)
  bfp_model.py       - nowcast + blended-average prediction logic
  db.py               - SQLite: manual overrides, report cache, prediction history
  app.py                - Flask app / API
frontend/
  index.html, style.css, app.js  - the dashboard (vanilla JS + Chart.js via CDN)
data/
  bfp.db  - local SQLite database (created on first run)
```

## Limits and honesty notes

- The predicted price change is the review-period average unit over/(under)
  recovery. The real government announcement (effective the first Wednesday
  of the month) also folds in separate slate-levy and fuel-levy decisions
  DMRE can adjust independently, so treat this as directional, not exact.
- The review period only closes around the 25th of the month - a prediction
  made early in the cycle can still move a lot before it closes.
- Diesel and illuminating paraffin don't have a single national pump price
  (diesel is wholesale/deregulated, paraffin has a price cap) - the "current
  price" shown for those is CEF's own wholesale / max-retail reference row.
