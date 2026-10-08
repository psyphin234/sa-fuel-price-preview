# SA Basic Fuel Price Preview

Previews South Africa's daily Basic Fuel Price (BFP) the way CEF calculates it, and projects the next monthly pump-price change. **README.md** has the full explanation: the model, the project layout, how publishing works, and its limits. Read it before making non-trivial changes. This file only covers what's easy to get wrong.

- Repo: `psyphin234/sa-fuel-price-preview`. The branch is **`master`** (not `main`).
- Public site: **https://fuel.psyphin.co.za/**, served by GitHub Pages from `docs/`. The custom domain is set by `docs/CNAME`; don't delete it. The older `psyphin.co.za/sa-fuel-price-preview/` and `psyphin234.github.io/sa-fuel-price-preview/` addresses 301-redirect here.
- The landing page's project card (`projects.js` in `E:\Claude_projects\psyphin.co.za`) links here, and its photo (`assets/img/projects/fuel-chart.jpg` there) is a crop of this site's first chart, "Daily Basic Fuel Price vs. price built into the current pump price". If that chart's look changes, refresh the card image. If this site's URL changes, update it there too. Domain and DNS details (Afrihost `fuel` CNAME → `psyphin234.github.io`) are in README.md under "Custom domain".

## Two frontends, kept in sync by hand

| Folder | What it is | Data source |
|---|---|---|
| `frontend/` | Local dashboard at http://127.0.0.1:5057 (Flask, `backend/app.py`). Has the manual-override form. | Flask API |
| `docs/` | **Public** read-only GitHub Pages site | `docs/data/status.json` |

- `style.css` is identical in both. Keep it that way: apply a CSS change to both files.
- **Always dark** (since 2026-10-08, to match psyphin.co.za and the other tools): both `index.html` files have `<html data-theme="dark">` and `<meta name="color-scheme" content="dark">`, so the `:root[data-theme="dark"]` tokens apply whatever the visitor's setting. The light tokens are still in `style.css` but unused. Dark mode uses the shared background `#020203`, cards `#111418`/`#181c21`, and the faint circuit-trace `body::before` pattern (via `--circuit-pattern`), the same as psyphin.co.za. Charts read their colours from these CSS variables when they draw.
- `index.html` and `app.js` differ on purpose. `docs/` has no manual-entry form, has slightly different wording, fetches static JSON instead of calling the API, and has a "← More PsyPhin tools" back link in the header (absolute URL `https://psyphin.co.za/#tools`, the Tools section of the landing page; the towing checker at psyphin.co.za/sa-towing-check/ uses the same pill). When changing shared UI, make the change in both and keep these differences.
- When you change a CSS/JS file under `docs/`, bump its `?v=` cache-buster in `docs/index.html` so visitors don't get a stale copy.
- **Never hand-edit `docs/data/status.json`.** It's generated and overwritten every hour.
- `docs/index.html` loads GoatCounter (https://psyphin.goatcounter.com/, shared with the psyphin.co.za landing page). A small `window.goatcounter.path` snippet prefixes paths with the host, so this site shows as `fuel.psyphin.co.za/` and the landing page's `/` stays separate. Visits from before 2026-09-27 are logged under `/sa-fuel-price-preview/`. GoatCounter is intentionally **not** in `frontend/`, because the local dashboard shouldn't count visits.

## The hourly publish bot pushes from this clone

Windows Scheduled Task **"BFP Preview Publish"** runs `wscript.exe backend/run_publish_hidden.vbs` → `backend/run_publish.ps1` → `backend/publish.py` in this working copy, on two triggers: **every hour at about :18**, and **every 15 minutes (:00, :15, :30, :45) from 07:00 to 11:00 on weekdays** to pick up CEF's morning report quickly. The `.vbs` launcher keeps it from flashing a console window and stealing focus. Don't point the task straight at `powershell.exe`, because `-WindowStyle Hidden` doesn't prevent the flash. It rebuilds `docs/data/status.json`, then runs `git add` on that file, a plain `git commit`, and `git push`. Consequences:

- **Anything staged gets swept into the bot's "Update BFP preview data" commit.** Don't leave files staged; stage and commit in one step.
- **Any unpushed local commits get pushed** with the bot's commit. Don't leave half-finished work committed on `master`.
- **It commits to whichever branch is checked out.** Stay on `master`, or switch back well before :18. Otherwise data commits land on your feature branch and the push fails.
- **It never pulls.** If `origin/master` gets ahead (for example after an edit on github.com or a push from another machine), the bot's pushes fail until this clone is updated. Always push from this clone and `git pull --rebase` before pushing.
- Avoid committing or pushing between about :15 and :22, and on weekday mornings (07:00–11:00) also within a couple of minutes of :00, :30 and :45. Check `data/publish.log` for the last run's result.

## Running things

- Dashboard: `.\run.ps1`. It installs requirements, opens the browser and runs `python app.py` on port 5057 in the foreground.
- To stop the dashboard, close its window or kill **only that PID** (`netstat -ano | findstr :5057`). **Never** kill `python.exe` by image name: that would also kill the dashboard and any publish run in progress.
- Manual publish: `cd backend; python publish.py`. It pushes too, so treat it like a push.
- Backtest the model (from `backend/`): `python backtest_fetch.py 2025-06-01 <today>` then `python backtest.py`.
- `data/` (the SQLite database and its `*.bak*` copies, logs, backtest cache) is gitignored and stays local.
- `PsyPhin logo black V3.jfif` and `PsyPhin logo.jfif` in the repo root are local reference copies of the logo, gitignored via `*.jfif`. Keep them. The originals are committed in the psyphin.co.za repo as `psyphin-logo-black.jpg` and `psyphin-logo.jpg`. The site itself uses `docs/assets/logo.jpg`.

## Conventions

- The brand name is written **PsyPhin** (capital P, lowercase sy, capital P, lowercase hin) in all visible text: titles, meta tags, alt text and footers. Domains and URLs stay lowercase (`psyphin.co.za`).
- **Commit identity:** commits use the GitHub private address `74655215+psyphin234@users.noreply.github.com` (set globally in git on this PC, 2026-09-27). Never commit with a personal email: in 2026-09 the history of this repo was rewritten to remove it. Old-history backups are in `E:\Claude_projects\_git-backups-2026-09-27\` (local only; never push them).
- **Backups:** the Windows Scheduled Task **"Project Backup"** runs `E:\Backup\Project_Backups\backup-projects.ps1` nightly at 02:00 (started through `backup-projects-hidden.vbs` via `wscript.exe` so no window flashes, the same approach as the publish task). It copies all of `E:\Claude_projects` (including local-only data such as the fuel site's `data\bfp.db` and the project source folders) to `E:\Backup\Project_Backups\latest\` (adds and updates, never deletes) plus a dated zip in `daily\` (newest 14 kept); log in `backup.log`. `E:\Backup` is in turn backed up to the owner's NAS, so a disk failure is covered too (and the code is also on GitHub).
- Python 3.10+, with Flask, requests, pdfplumber and numpy (`backend/requirements.txt`). There is no Node or build step.
- Chart.js 4.5.1 loads from cdnjs with an `integrity` (SRI) hash in both `docs/index.html` and `frontend/index.html`. If you upgrade the version, update the hash too (from `https://api.cdnjs.com/libraries/Chart.js/<version>?fields=sri`), or the browser will refuse to load the script and the charts will disappear.
- The whole design depends on your PC only making **outbound** connections to CEF, Yahoo Finance and GitHub. Don't add anything that listens publicly or gives the public site a write endpoint.
- Values carry a `source` of `cef_official`, `estimated` or `manual`, and the UI must keep estimates visibly distinct from official figures.
