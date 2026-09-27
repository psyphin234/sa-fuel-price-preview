# SA Basic Fuel Price Preview

Previews South Africa's daily Basic Fuel Price (BFP) the way CEF calculates it, and projects the next monthly pump-price change. **README.md** has the full explanation: the model, the project layout, how publishing works, and its limits. Read it before making non-trivial changes. This file only covers what's easy to get wrong.

- Repo: `psyphin234/sa-fuel-price-preview`. The branch is **`master`** (not `main`).
- Public site: **https://fuel.psyphin.co.za/**, served by GitHub Pages from `docs/`. The custom domain is set by `docs/CNAME`; don't delete it. The older `psyphin.co.za/sa-fuel-price-preview/` and `psyphin234.github.io/sa-fuel-price-preview/` addresses 301-redirect here.
- The landing page's project card (`projects.js` in `E:\Claude_projects\psyphin.co.za`) links here. If this site's URL changes, update it there too. Domain and DNS details (Afrihost `fuel` CNAME → `psyphin234.github.io`) are in README.md under "Custom domain".

## Two frontends, kept in sync by hand

| Folder | What it is | Data source |
|---|---|---|
| `frontend/` | Local dashboard at http://127.0.0.1:5057 (Flask, `backend/app.py`). Has the manual-override form. | Flask API |
| `docs/` | **Public** read-only GitHub Pages site | `docs/data/status.json` |

- `style.css` is identical in both. Keep it that way: apply a CSS change to both files.
- `index.html` and `app.js` differ on purpose. `docs/` has no manual-entry form, has slightly different wording, fetches static JSON instead of calling the API, and has a "← psyphin.co.za" back link in the header (absolute URL `https://psyphin.co.za/`). When changing shared UI, make the change in both and keep these differences.
- When you change a CSS/JS file under `docs/`, bump its `?v=` cache-buster in `docs/index.html` so visitors don't get a stale copy.
- **Never hand-edit `docs/data/status.json`.** It's generated and overwritten every hour.
- `docs/index.html` loads GoatCounter (https://psyphin.goatcounter.com/, shared with the psyphin.co.za landing page). A small `window.goatcounter.path` snippet prefixes paths with the host, so this site shows as `fuel.psyphin.co.za/` and the landing page's `/` stays separate. Visits from before 2026-09-27 are logged under `/sa-fuel-price-preview/`. GoatCounter is intentionally **not** in `frontend/`, because the local dashboard shouldn't count visits.

## The hourly publish bot pushes from this clone

Windows Scheduled Task **"BFP Preview Publish"** runs `backend/run_publish.ps1` → `backend/publish.py` **every hour at about :18**, in this working copy. It rebuilds `docs/data/status.json`, then runs `git add` on that file, a plain `git commit`, and `git push`. Consequences:

- **Anything staged gets swept into the bot's "Update BFP preview data" commit.** Don't leave files staged; stage and commit in one step.
- **Any unpushed local commits get pushed** with the bot's commit. Don't leave half-finished work committed on `master`.
- **It commits to whichever branch is checked out.** Stay on `master`, or switch back well before :18. Otherwise data commits land on your feature branch and the push fails.
- **It never pulls.** If `origin/master` gets ahead (for example after an edit on github.com or a push from another machine), the bot's pushes fail until this clone is updated. Always push from this clone and `git pull --rebase` before pushing.
- Avoid committing or pushing between about :15 and :22. Check `data/publish.log` for the last run's result.

## Running things

- Dashboard: `.\run.ps1`. It installs requirements, opens the browser and runs `python app.py` on port 5057 in the foreground.
- To stop the dashboard, close its window or kill **only that PID** (`netstat -ano | findstr :5057`). **Never** kill `python.exe` by image name: that would also kill the dashboard and any publish run in progress.
- Manual publish: `cd backend; python publish.py`. It pushes too, so treat it like a push.
- Backtest the model (from `backend/`): `python backtest_fetch.py 2025-06-01 <today>` then `python backtest.py`.
- `data/` (the SQLite database, logs, backtest cache) is gitignored and stays local.
- `PsyPhin logo black V3.jfif` and `PsyPhin logo.jfif` in the repo root are local reference copies of the logo, gitignored via `*.jfif`. Keep them. The originals are committed in the psyphin.co.za repo as `psyphin-logo-black.jpg` and `psyphin-logo.jpg`. The site itself uses `docs/assets/logo.jpg`.

## Conventions

- The brand name is written **PsyPhin** (capital P, lowercase sy, capital P, lowercase hin) in all visible text: titles, meta tags, alt text and footers. Domains and URLs stay lowercase (`psyphin.co.za`).
- **Commit identity:** commits use the GitHub private address `74655215+psyphin234@users.noreply.github.com` (set globally in git on this PC, 2026-09-27). Never commit with a personal email: in 2026-09 the history of this repo was rewritten to remove it. Old-history backups are in `E:\Claude_projects\_git-backups-2026-09-27\` (local only; never push them).
- **Backups:** the Windows Scheduled Task **"Project Backup"** runs `E:\Backup\Project_Backupsackup-projects.ps1` nightly at 02:00. It copies all of `E:\Claude_projects` (including local-only data such as the fuel site's `datafp.db` and the project source folders) to `E:\Backup\Project_Backups\latest\` (adds and updates, never deletes) plus a dated zip in `daily\` (newest 14 kept); log in `backup.log`. It's on the same disk as the projects, so it guards against mistakes and corruption, not a disk failure.
- Python 3.10+, with Flask, requests, pdfplumber and numpy (`backend/requirements.txt`). There is no Node or build step.
- Chart.js 4.5.1 loads from cdnjs with an `integrity` (SRI) hash in both `docs/index.html` and `frontend/index.html`. If you upgrade the version, update the hash too (from `https://api.cdnjs.com/libraries/Chart.js/<version>?fields=sri`), or the browser will refuse to load the script and the charts will disappear.
- The whole design depends on your PC only making **outbound** connections to CEF, Yahoo Finance and GitHub. Don't add anything that listens publicly or gives the public site a write endpoint.
- Values carry a `source` of `cef_official`, `estimated` or `manual`, and the UI must keep estimates visibly distinct from official figures.
