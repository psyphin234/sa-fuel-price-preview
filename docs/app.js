/* SA Basic Fuel Price Preview: the public page's script (docs/, fuel.psyphin.co.za).

   It downloads data/status.json and draws the page from it: the levy banner, the
   status strip, the three headline cards, the accuracy meter, the exchange-rate
   card, the two price charts, the day-by-day table and, through context.js, the
   oil and Hormuz background panel. All the sums (the estimates for days CEF hasn't
   published, the projected price change) are done by the Python backend, which
   rebuilds status.json every hour (backend/app.py build_status_data, written out
   by backend/publish.py). This file only formats and draws what it's given.

   Its twin is frontend/app.js, the local dashboard, which gets the same payload
   from the Flask API (/api/status) and adds a manual-entry form. The two are kept
   in step by hand: change shared code in both.

   Conventions used throughout:
   - Prices in the payload are in cents per litre (c/l); the page shows rand.
   - Dates are ISO "YYYY-MM-DD" strings, so they compare correctly as text.
   - Every daily figure has a `source`: "cef_official" (from CEF's published
     report), "estimated" (the backend's estimate for a day CEF hasn't published
     yet) or "manual" (typed into the local dashboard). Estimates must always look
     different from official figures: hollow points, dashed lines, badges.
   - Fuel keys: petrol95, petrol93, diesel005, diesel0005, illpar (paraffin).

   Loaded last, after Chart.js, circuit.js, fx.js and context.js (see index.html).
   Everything is inside one function so nothing leaks into the global scope. */
(() => {
  "use strict";

  // Defaults for every chart on the page. fx.js also styles the tooltips and adds
  // the glow to the lines.
  Chart.defaults.font.family = '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 13;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.boxPadding = 4;

  // Public, read-only build: data comes from a static JSON snapshot that a
  // private backend pushes to this repo on a schedule (see backend/publish.py).
  // There is no live API here - "Check for update" just re-fetches that file.
  const DATA_URL = "data/status.json";

  // The five fuels in CEF's reports, in tab order (the keys used all through the payload).
  const FUEL_ORDER = ["petrol95", "petrol93", "diesel005", "diesel0005", "illpar"];
  // The selected tab is remembered in this browser, so a refresh stays on the same
  // fuel. localStorage can be blocked (private windows), hence the try/catch.
  const FUEL_KEY = "bfp-fuel";
  const savedFuel = () => {
    try {
      const f = localStorage.getItem(FUEL_KEY);
      return FUEL_ORDER.includes(f) ? f : "petrol95";
    } catch {
      return "petrol95";
    }
  };
  // Which kind of price the "current price" is for each fuel. Petrol is regulated at
  // the pump (CEF reports the Gauteng figure); diesel only at wholesale, since
  // retailers set its pump price; paraffin has a single national maximum retail price.
  const PRICE_ROW_LABEL = {
    petrol95: "Gauteng pump price",
    petrol93: "Gauteng pump price",
    diesel005: "Wholesale price",
    diesel0005: "Wholesale price",
    illpar: "Single national max retail price",
  };

  // state.fuel is the selected tab, state.data the whole payload. Every render
  // function reads only these two, so a tab change is just: set state.fuel, render().
  // The charts are kept so they can be destroyed before being drawn again.
  let state = { fuel: savedFuel(), data: null };
  let chartBfp = null, chartRecovery = null, chartFx = null;

  // Small helpers. cssVar reads a colour token from style.css, so the charts use
  // the same colours as the rest of the page.
  const $ = (sel) => document.querySelector(sel);
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  // Formatting. The payload is in cents per litre; a missing value shows as a dash.
  const centsToRand = (c) => (c === null || c === undefined) ? null : c / 100;
  const fmtRand = (c) => c === null || c === undefined ? "—" : `R${centsToRand(c).toFixed(2)}/l`;
  const fmtRandDelta = (c) => {
    if (c === null || c === undefined) return "—";
    const sign = c > 0 ? "+" : c < 0 ? "−" : "";
    return `${sign}R${centsToRand(Math.abs(c)).toFixed(2)}/l`;
  };
  const fmtCents = (c) => c === null || c === undefined ? "—" : c.toFixed(2);
  // Compares one of our estimates with CEF's figure for the same day, once CEF has
  // published it. error_c_per_l is official minus estimate (backend/db.py
  // log_accuracy), so a positive error means the estimate was too low.
  const describeEstimate = (est, official) => {
    const diff = est.error_c_per_l;
    const off = Math.abs(diff).toFixed(2);
    const pct = est.pct_error === null ? "" : ` (${Math.abs(est.pct_error).toFixed(2)}%)`;
    const verdict = Math.abs(diff) < 0.005 ? "spot on" : `${off} c/l too ${diff > 0 ? "low" : "high"}${pct}`;
    return { estimate: fmtCents(est.bfp), official: fmtCents(official), verdict };
  };
  // "T00:00:00" without a time zone is read as local midnight, so the date shown is
  // the date in the data whatever the visitor's time zone.
  const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "2-digit", month: "short", year: "numeric" });

  // The fuel tabs. Clicking one changes state.fuel and redraws the whole page.
  function buildTabs() {
    const nav = $("#fuel-tabs");
    nav.innerHTML = "";
    FUEL_ORDER.forEach((fuel) => {
      const btn = document.createElement("button");
      btn.className = "fuel-tab";
      btn.type = "button";
      btn.role = "tab";
      btn.setAttribute("aria-selected", fuel === state.fuel ? "true" : "false");
      btn.textContent = state.data.fuels[fuel] || fuel;
      btn.addEventListener("click", () => {
        state.fuel = fuel;
        try { localStorage.setItem(FUEL_KEY, fuel); } catch { /* not remembered, still works */ }
        render();
      });
      nav.appendChild(btn);
    });
  }

  // CSS class for a price change: red for a rise, green for a fall (style.css).
  const dirClass = (c) => c > 0 ? "increase" : c < 0 ? "decrease" : "";

  // Announced fuel levy and slate levy changes on the forecast date
  // (backend/fuel_levy.py). The model only forecasts the Basic Fuel Price part, so
  // these are added on top.
  const onForecastDate = (c) => c && c.effective === state.data.predicted_change_date ? c : null;
  const levyFor = (fuel) => {
    const lc = onForecastDate(state.data.levy_change), sc = onForecastDate(state.data.slate_change);
    return (lc ? lc.change[fuel] || 0 : 0) + (sc ? sc.change[fuel] || 0 : 0);
  };
  // A temporary levy cut in force on a price-change date, for marking prices that
  // have it built in (they go back up when it ends).
  const reliefOn = (iso, fuel) =>
    (state.data.levy_relief || []).find((r) => iso && r.start <= iso && iso <= r.end && r.relief[fuel]);
  // Shows the cyan "Includes R…/l fuel levy relief" tag next to a price whose date
  // falls in a relief period, and hides it otherwise.
  function setLevyTag(sel, iso) {
    const el = $(sel);
    const r = reliefOn(iso, state.fuel);
    el.hidden = !r;
    if (!r) return;
    el.textContent = `Includes ${fmtRand(r.relief[state.fuel])} fuel levy relief, to ${fmtDate(r.end)}`;
    el.title = `A temporary cut in the fuel levy, announced in the ${r.source} on ${fmtDate(r.announced)} ` +
      `and in force from ${fmtDate(r.start)} to ${fmtDate(r.end)}. The price goes back up by this much when it ends.`;
  }

  // Banner under the fuel tabs while temporary levy relief is announced or in force.
  function renderLevyBanner() {
    const el = $("#levy-banner");
    const today = state.data.generated_at.slice(0, 10);
    const periods = (state.data.levy_relief || []).filter((r) => r.end >= today);
    el.hidden = !periods.length;
    if (!periods.length) return;
    const priceDate = state.data.latest_official_report.pump_price_effective;
    const inPrice = periods.some((r) => r.start <= priceDate && priceDate <= r.end);
    const lead = !inPrice ? `Fuel levy relief from ${fmtDate(periods[0].start)}.`
      : priceDate > today ? `Fuel levy relief is built into the new price from ${fmtDate(priceDate)}.`
      : "Fuel levy relief is built into the current price.";
    const steps = periods.map((r, i) => i === 0
      ? `${fmtRand(r.relief.petrol95)} off petrol and ${fmtRand(r.relief.diesel005)} off diesel ` +
        (r.start > today ? `from ${fmtDate(r.start)} ` : "") + `to ${fmtDate(r.end)}`
      : `then ${fmtRand(r.relief.petrol95)} and ${fmtRand(r.relief.diesel005)} to ${fmtDate(r.end)}`);
    const strong = document.createElement("strong");
    strong.textContent = lead;
    el.replaceChildren(strong, ` Announced in the ${periods[0].source} on ${fmtDate(periods[0].announced)}: ` +
      `${steps.join(", ")}. ` +
      (inPrice ? "Prices go back up as it ends, and the forecast below includes that. " : "The forecast below includes it. ") +
      "Paraffin has no fuel levy.");
  }

  // The small print under a forecast when an announced fuel levy or slate levy
  // change falls on the forecast date: what's included, and what the Basic Fuel
  // Price alone would do. Empty when neither applies.
  function levyNote(fuel, bfpChange) {
    const lc = onForecastDate(state.data.levy_change), sc = onForecastDate(state.data.slate_change);
    const amount = (c) => fmtRand(Math.abs(c)).replace("/l", "");
    const parts = [];
    const levy = lc ? lc.change[fuel] || 0 : 0;
    if (levy) {
      parts.push(levy < 0
        ? `the ${amount(levy)} fuel levy cut announced in the ${lc.source} on ${fmtDate(lc.announced)}`
        : `the fuel levy going back up by ${amount(levy)} as the ${lc.source} relief winds down`);
    }
    const slate = sc ? sc.change[fuel] || 0 : 0;
    if (slate) {
      parts.push(`the slate levy going ${slate > 0 ? "up" : "down"} by ${amount(slate)} ` +
        `(to ${amount(sc.to)}), announced by the ${sc.source} on ${fmtDate(sc.announced)}`);
    }
    const noSlate = sc ? "" : " Before any slate-levy change.";
    if (!parts.length) {
      return lc || sc
        ? "Paraffin carries no fuel or slate levy, so the announced levy changes don't apply." + noSlate
        : "";
    }
    return `Includes ${parts.join(" and ")}. Basic Fuel Price alone: ${fmtRandDelta(bfpChange)}.` + noSlate;
  }

  // Under a forecast that takes another fuel's change (petrol 93 follows 95; see
  // FOLLOWS in backend/bfp_model.py), the line saying so. Empty otherwise.
  const followNote = (pred) => pred.follows
    ? `Same as ${state.data.predictions[pred.follows].label}: the official change for 93 usually matches 95's.`
    : "";
  const joinNotes = (...notes) => notes.filter(Boolean).join(" ");

  // Until an announced change takes effect it leads, and the next cycle's
  // prediction (only a few days in, so still uncertain) is a smaller early look.
  function renderAnnounced() {
    const ann = state.data.announced_change;
    const change = ann ? ann.change[state.fuel] : undefined;
    const show = change !== undefined;
    $("#hero-announced").hidden = !show;
    $("#hero-forecast").hidden = show;
    if (!show) return false;

    const pred = state.data.predictions[state.fuel];
    $("#ann-title").textContent = `Price change on ${fmtDate(ann.effective)}`;
    const changeEl = $("#ann-change");
    changeEl.textContent = fmtRandDelta(change);
    changeEl.className = "hero-value " + dirClass(change);
    const badge = $("#ann-badge");
    badge.className = "hero-badge " + (dirClass(change) || "flat");
    badge.textContent = change > 0 ? "▲ Announced increase" : change < 0 ? "▼ Announced decrease" : "■ Announced: no change";
    $("#ann-prices").textContent =
      `${PRICE_ROW_LABEL[state.fuel]}: ${fmtRand(ann.previous_price[state.fuel])} → ${fmtRand(ann.new_price[state.fuel])}`;
    setLevyTag("#ann-levy", ann.effective);

    $("#early-title").textContent = `Early look: ${fmtDate(state.data.predicted_change_date)}`;
    const earlyEl = $("#early-change");
    const levy = levyFor(state.fuel);
    const early = pred.predicted_pump_price_change_c_per_l + levy;
    earlyEl.textContent = fmtRandDelta(early);
    earlyEl.className = "hero-value " + dirClass(early);
    setRange("#early-range", state.fuel, early);
    setLevyTag("#early-levy", state.data.predicted_change_date);
    const days = pred.blended_days_count;
    const note = joinNotes(followNote(pred), levyNote(state.fuel, pred.predicted_pump_price_change_c_per_l));
    $("#early-sub").textContent =
      `About ${fmtRand(pred.predicted_new_price_c_per_l + levy)}. Only ${days} day${days === 1 ? "" : "s"} of the review period so far, so this can still move a lot.` +
      (note ? " " + note : "");
    return true;
  }

  // The three headline cards for the selected fuel: the price in force (or just
  // announced), the predicted change on the next price-change date, and the
  // predicted new price, with how many days of the review period are official,
  // estimated or manual. While a change is announced but not yet in force,
  // renderAnnounced() shows that instead of the forecast.
  function renderHero() {
    $("#period-range").textContent =
      `${fmtDate(state.data.latest_official_report.period_start)} – ${fmtDate(state.data.latest_official_report.period_end)} (to date)`;
    if (renderAnnounced()) return;

    const pred = state.data.predictions[state.fuel];
    const levy = levyFor(state.fuel);
    const change = pred.predicted_pump_price_change_c_per_l + levy;
    const dir = levy ? (change > 0 ? "increase" : change < 0 ? "decrease" : "no change") : pred.direction;

    $("#hero-current").textContent = fmtRand(pred.current_price_c_per_l);
    // In the days before a price change CEF already reports the upcoming price.
    const effective = state.data.latest_official_report.pump_price_effective;
    const upcoming = effective > state.data.generated_at.slice(0, 10);
    $("#hero-current-title").textContent = upcoming ? `New price from ${fmtDate(effective)}` : "Current price";
    $("#hero-current-label").textContent = PRICE_ROW_LABEL[state.fuel] + (upcoming ? " (announced)" : " (current cycle)");
    setLevyTag("#hero-current-levy", effective);

    const changeDate = state.data.predicted_change_date;
    $("#hero-change-title").textContent = changeDate ? `Predicted change on ${fmtDate(changeDate)}` : "Predicted next-cycle move";

    const changeEl = $("#hero-change");
    changeEl.textContent = fmtRandDelta(change);
    changeEl.className = "hero-value " + (dir === "increase" ? "increase" : dir === "decrease" ? "decrease" : "");

    const badge = $("#hero-direction-badge");
    const icon = dir === "increase" ? "▲" : dir === "decrease" ? "▼" : "■";
    const label = dir === "increase" ? "Price expected to rise" : dir === "decrease" ? "Price expected to fall" : "Little change expected";
    badge.className = "hero-badge " + (dir === "increase" ? "increase" : dir === "decrease" ? "decrease" : "flat");
    badge.textContent = `${icon} ${label}`;
    setRange("#hero-range", state.fuel, change);
    $("#hero-change-note").textContent =
      joinNotes(followNote(pred),
        levyNote(state.fuel, pred.predicted_pump_price_change_c_per_l) || "Before any slate-levy or fuel-levy change.");

    $("#hero-newprice").textContent = fmtRand(pred.predicted_new_price_c_per_l + levy);
    setLevyTag("#hero-newprice-levy", changeDate);
    const officialDays = pred.official_days_count;
    const estDays = pred.estimated_days.length;
    const manDays = pred.manual_days.length;
    let conf = `${officialDays} official day${officialDays === 1 ? "" : "s"}`;
    if (estDays) conf += ` + ${estDays} estimated`;
    if (manDays) conf += ` + ${manDays} manual`;
    const projDays = pred.projected_days_count || 0;
    $("#hero-confidence").textContent = state.data.review_period_closed
      ? `Review period closed ${fmtDate(state.data.review_period_close)} (${conf})`
      : conf + " so far" + (projDays
        ? `. The other ${projDays} day${projDays === 1 ? "" : "s"} to ${fmtDate(state.data.review_period_close)} assume the BFP stays where it is now`
        : " in this review period");
  }

  const fmtShortDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "2-digit", month: "short" });

  // Dashed vertical line where one review period ends and the next begins, with
  // the price change each side feeds when there is room for the label.
  function cycleDivider(series) {
    return {
      id: "cycleDivider",
      afterDatasetsDraw(chart) {
        const { top, bottom, left, right } = chart.chartArea;
        const xs = chart.scales.x;
        const ctx = chart.ctx;
        ctx.save();
        ctx.font = "12px " + getComputedStyle(document.body).fontFamily;
        ctx.textBaseline = "top";
        for (let i = 1; i < series.length; i++) {
          const before = series[i - 1].cycle, after = series[i].cycle;
          if (!before || !after || before === after) continue;
          const x = (xs.getPixelForValue(i - 1) + xs.getPixelForValue(i)) / 2;
          ctx.strokeStyle = cssVar("--text-muted");
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(x, top);
          ctx.lineTo(x, bottom);
          ctx.stroke();
          ctx.setLineDash([]);
          // Each label sits on its own side of the line; one that doesn't fit there
          // goes on a second row on the other side, its arrow still pointing across.
          const labels = [`← sets ${fmtShortDate(before)} price`, `sets ${fmtShortDate(after)} price →`];
          const widths = labels.map((t) => ctx.measureText(t).width);
          const fits = [x - 6 - widths[0] >= left, x + 6 + widths[1] <= right];
          labels.forEach((text, k) => {
            const onLeft = k === 0 ? fits[0] : !fits[1];
            const row = fits[k] ? 0 : 1;
            const x0 = onLeft ? x - 6 - widths[k] : x + 6;
            if (x0 < left || x0 + widths[k] > right) return;
            const y = top + 4 + row * 18;
            ctx.fillStyle = cssVar("--surface-1") + "e6";
            ctx.fillRect(x0 - 3, y - 2, widths[k] + 6, 17);
            ctx.fillStyle = cssVar("--text-secondary");
            ctx.textAlign = "left";
            ctx.fillText(text, x0, y);
          });
        }
        ctx.restore();
      },
    };
  }

  // Headroom at the top of a chart for the divider's labels.
  function withDividerRoom(opts, series) {
    if (series.some((d, k) => k > 0 && d.cycle && series[k - 1].cycle && d.cycle !== series[k - 1].cycle)) {
      opts.scales.y.afterDataLimits = (scale) => { scale.max += (scale.max - scale.min) * 0.25; };
    }
    return opts;
  }

  // The two main charts for the selected fuel, over the last 30 days:
  // 1. Daily BFP (blue) against the BFP built into the pump price (orange, the
  //    "reference"). The reference is fixed for a month and steps on the
  //    price-change date.
  // 2. The daily over/(under) recovery: reference minus BFP. Negative (red) means
  //    fuel cost more to import than the price allows for, which pushes the next
  //    price up. The review period's average of this sets the next change.
  // Days CEF hasn't published yet get hollow points and dashed line segments.
  // Both charts are destroyed and rebuilt on every render.
  function renderCharts() {
    const series = [...state.data.daily_series[state.fuel]].sort((a, b) => a.date.localeCompare(b.date));
    const referenceValue = state.data.latest_official_report.reference_price[state.fuel];

    const labels = series.map((d) => fmtDate(d.date));
    const bfpValues = series.map((d) => d.bfp);
    // A day without its own reference falls back to the latest report's.
    const refValues = series.map((d) => d.reference ?? referenceValue);
    const isEstimated = series.map((d) => d.source !== "cef_official");
    // For days CEF has since published: what we had estimated for them, drawn as
    // hollow diamonds so the estimate can be compared with the real figure.
    const priorEstimates = series.map((d) => d.estimate ? d.estimate.bfp : null);
    const hasPriorEstimates = priorEstimates.some((v) => v !== null);

    const blue = cssVar("--series-blue");
    const orange = cssVar("--series-orange");
    const red = cssVar("--series-red");
    const grid = cssVar("--gridline");
    const textSec = cssVar("--text-secondary");

    if (chartBfp) chartBfp.destroy();
    chartBfp = new Chart($("#chart-bfp"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Basic Fuel Price",
            data: bfpValues,
            borderColor: blue,
            backgroundColor: blue,
            borderWidth: 2,
            pointRadius: (ctx) => isEstimated[ctx.dataIndex] ? 4 : 2,
            pointBackgroundColor: (ctx) => isEstimated[ctx.dataIndex] ? cssVar("--surface-1") : blue,
            pointBorderColor: blue,
            pointBorderWidth: (ctx) => isEstimated[ctx.dataIndex] ? 2 : 0,
            segment: {
              borderDash: (ctx) => (isEstimated[ctx.p0DataIndex] || isEstimated[ctx.p1DataIndex]) ? [5, 4] : undefined,
            },
            tension: 0,
            fill: false,
          },
          {
            label: "Built into the pump price",
            data: refValues,
            stepped: true,
            borderColor: orange,
            backgroundColor: orange,
            borderWidth: 2,
            borderDash: [2, 3],
            pointRadius: 0,
            tension: 0,
            fill: false,
          },
          ...(hasPriorEstimates ? [{
            label: "Our estimate before CEF published",
            data: priorEstimates,
            showLine: false,
            borderColor: textSec,
            backgroundColor: cssVar("--surface-1"),
            pointStyle: "rectRot",
            pointRadius: 5,
            pointHoverRadius: 6,
            pointBorderWidth: 2,
            estimateFor: series,
          }] : []),
        ],
      },
      options: withDividerRoom(chartOptions(grid, textSec, "c/l"), series),
      plugins: [cycleDivider(series)],
    });

    // Recovery chart: the line and its fill are blue above zero and red below.
    const overUnder = series.map((d) => d.unit_over_under);
    const zeroLine = series.map(() => 0);
    const segColor = (ctx) => {
      const avg = ((ctx.p0.parsed.y ?? 0) + (ctx.p1.parsed.y ?? 0)) / 2;
      return avg >= 0 ? blue : red;
    };

    if (chartRecovery) chartRecovery.destroy();
    chartRecovery = new Chart($("#chart-recovery"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Unit over/(under) recovery",
            data: overUnder,
            borderWidth: 2,
            borderColor: blue,
            pointRadius: (ctx) => isEstimated[ctx.dataIndex] ? 4 : 2,
            pointBackgroundColor: (ctx) => {
              const v = ctx.raw ?? 0;
              const base = v >= 0 ? blue : red;
              return isEstimated[ctx.dataIndex] ? cssVar("--surface-1") : base;
            },
            pointBorderColor: (ctx) => (ctx.raw ?? 0) >= 0 ? blue : red,
            pointBorderWidth: (ctx) => isEstimated[ctx.dataIndex] ? 2 : 0,
            segment: {
              borderColor: segColor,
              backgroundColor: (ctx) => segColor(ctx) + "2e",
              borderDash: (ctx) => (isEstimated[ctx.p0DataIndex] || isEstimated[ctx.p1DataIndex]) ? [5, 4] : undefined,
            },
            fill: "origin",
            tension: 0,
          },
          {
            label: "Break-even",
            data: zeroLine,
            borderColor: cssVar("--baseline"),
            borderWidth: 1,
            borderDash: [3, 3],
            pointRadius: 0,
            fill: false,
            tension: 0,
          },
        ],
      },
      options: (() => {
        const opts = withDividerRoom(chartOptions(grid, textSec, "c/l"), series);
        // The line is blue above zero and red below, so the key needs both colours.
        opts.plugins.legend.labels.generateLabels = (chart) => {
          const [line, ...rest] = Chart.defaults.plugins.legend.labels.generateLabels(chart);
          return [
            { ...line, text: "Over-recovery", fillStyle: blue, strokeStyle: blue },
            { ...line, text: "Under-recovery", fillStyle: red, strokeStyle: red },
            ...rest,
          ];
        };
        return opts;
      })(),
      plugins: [cycleDivider(series)],
    });
  }

  // The rand/dollar card. The big figure is the live USD/ZAR rate when the data was
  // built (Yahoo Finance); the chart is the rate in each of CEF's daily reports,
  // plus the backend's estimate for days CEF hasn't published.
  function renderFx() {
    const series = [...state.data.exchange_rate_series].sort((a, b) => a.date.localeCompare(b.date));
    const current = state.data.current_exchange_rate;
    $("#fx-current").textContent = current ? `R${current.toFixed(4)} / $1` : "—";

    const changeEl = $("#fx-change");
    const validRates = series.filter((d) => d.rate !== null && d.rate !== undefined);
    if (validRates.length >= 2) {
      const last = validRates[validRates.length - 1].rate;
      const prev = validRates[validRates.length - 2].rate;
      const changePct = ((last - prev) / prev) * 100;
      const dir = changePct > 0.01 ? "up" : changePct < -0.01 ? "down" : "flat";
      const arrow = dir === "up" ? "▲" : dir === "down" ? "▼" : "■";
      changeEl.textContent = `${arrow} ${changePct > 0 ? "+" : ""}${changePct.toFixed(2)}% vs prior day`;
      changeEl.className = "fx-change " + dir;
    } else {
      changeEl.textContent = "";
      changeEl.className = "fx-change";
    }

    const labels = series.map((d) => fmtDate(d.date));
    const rates = series.map((d) => d.rate);
    const isEstimated = series.map((d) => d.source !== "cef_official");
    const blue = cssVar("--series-blue");
    const grid = cssVar("--gridline");
    const textSec = cssVar("--text-secondary");

    if (chartFx) chartFx.destroy();
    chartFx = new Chart($("#chart-fx"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "USD/ZAR",
          data: rates,
          borderColor: blue,
          backgroundColor: blue,
          borderWidth: 2,
          pointRadius: (ctx) => isEstimated[ctx.dataIndex] ? 4 : 2,
          pointBackgroundColor: (ctx) => isEstimated[ctx.dataIndex] ? cssVar("--surface-1") : blue,
          pointBorderColor: blue,
          pointBorderWidth: (ctx) => isEstimated[ctx.dataIndex] ? 2 : 0,
          segment: {
            borderDash: (ctx) => (isEstimated[ctx.p0DataIndex] || isEstimated[ctx.p1DataIndex]) ? [5, 4] : undefined,
          },
          tension: 0,
          fill: false,
        }],
      },
      options: (() => {
        const opts = chartOptions(grid, textSec, "R/$");
        opts.plugins.legend.display = false;
        return opts;
      })(),
    });
  }

  // "How reliable are the estimated days?" Each estimate is checked against CEF's
  // figure once published (backend/accuracy.py); this shows 100% minus the average
  // % error over the most recent checks, coloured green, amber or red.
  function renderAccuracy() {
    const acc = state.data.accuracy;
    const fill = $("#accuracy-fill");
    const headline = $("#accuracy-headline");
    const sub = $("#accuracy-sub");

    if (!acc || acc.status === "collecting") {
      fill.style.width = "0%";
      fill.className = "accuracy-meter-fill unknown";
      headline.textContent = "Not enough data yet";
      sub.textContent = "Estimate tracking just started. The first comparison comes once CEF publishes the next official day.";
      return;
    }

    const pct = acc.accuracy_pct;
    fill.style.width = `${pct}%`;
    fill.className = "accuracy-meter-fill " + (pct >= 97 ? "" : pct >= 90 ? "warning" : "critical");
    headline.textContent = `${pct}% accurate on average`;
    const warmup = acc.status === "warming_up" ? " (still an early sample, so treat this loosely)" : "";
    sub.textContent = `Based on ${acc.n} estimated day${acc.n === 1 ? "" : "s"} checked against CEF's real figures so far: typically about ${acc.mean_abs_error_c_per_l} c/l (${acc.mean_abs_pct_error}%) off${warmup}.`;
  }

  // ---- How sure the forecast is, and how it adds up ----

  // A change without the "/l": −R3.24.
  const fmtRandBare = (c) => fmtRandDelta(c).replace("/l", "");
  // An average over/(under) recovery in words: "R3.24/l over-recovery".
  const fmtOverUnder = (avg) => `${fmtRand(Math.abs(avg))} ${avg >= 0 ? "over" : "under"}-recovery`;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // The likely range around a forecast change (backend/forecast_range.py): the
  // forecast plus or minus how far forecasts at the same stage of the last dozen
  // review periods missed, about 4 times in 5. Rounded outwards to 10c so it doesn't
  // look more exact than it is. null when there's no range (too little history, or
  // CEF has published every day of the period).
  function likelyRange(fuel, change) {
    const fr = state.data.forecast_range;
    const h = fr && fr.half_width ? fr.half_width[fuel] : undefined;
    if (h === undefined || h === null || h < 0.5) return null;
    return { lo: Math.floor((change - h) / 10) * 10, hi: Math.ceil((change + h) / 10) * 10, fr };
  }
  const rangeExplainer = (fr) =>
    `With ${plural(fr.remaining_days, "day")} of the review period still to come, forecasts in the last ` +
    `${fr.periods} review periods landed this close to the final figure about 4 times in 5. ` +
    "It covers the Basic Fuel Price only, not a slate-levy change.";

  // "Likely between −R3.50 and −R2.80" under a forecast; hidden when there's no range.
  function setRange(sel, fuel, change) {
    const el = $(sel);
    const r = likelyRange(fuel, change);
    el.hidden = !r;
    if (!r) return;
    el.textContent = `Likely between ${fmtRandBare(r.lo)} and ${fmtRandBare(r.hi)}`;
    el.title = rangeExplainer(r.fr);
  }

  // The review period's days as a row of cells (official, estimated, by hand, to
  // come), with a gap between weeks, and the count above it.
  function renderProgress() {
    const days = state.data.review_days || [];
    const count = { official: 0, estimated: 0, manual: 0, to_come: 0 };
    days.forEach((d) => { count[d.status] = (count[d.status] || 0) + 1; });
    const n = days.length;
    const close = state.data.review_period_close;
    const unpublished = count.estimated + count.manual;
    let headline, detail;
    if (count.to_come) {
      headline = `Day ${n - count.to_come} of ${n}`;
      detail = [`${count.official} official`, unpublished && `${unpublished} estimated`,
        `${count.to_come} to come`, `closes ${fmtShortDate(close)}`].filter(Boolean).join(" · ");
    } else if (unpublished) {
      headline = `Closed ${fmtShortDate(close)}`;
      detail = `${count.official} of ${n} days official, ${plural(unpublished, "day")} still to come from CEF`;
    } else {
      headline = `All ${n} days in`;
      detail = `Every day to ${fmtShortDate(close)} is CEF official`;
    }
    $("#pp-headline").textContent = headline;
    $("#pp-detail").textContent = detail;
    const words = { official: "CEF official", estimated: "estimated", manual: "entered by hand", to_come: "still to come" };
    const ol = $("#pp-cells");
    ol.replaceChildren(...days.map((d, i) => {
      const li = document.createElement("li");
      const monday = new Date(d.date + "T00:00:00Z").getUTCDay() === 1;
      li.className = d.status + (monday && i > 0 ? " week-start" : "");
      li.title = `${fmtDate(d.date)}: ${words[d.status]}`;
      li.setAttribute("aria-hidden", "true");
      return li;
    }));
    ol.setAttribute("role", "img");
    ol.setAttribute("aria-label", `${headline}: ${detail}`);
    $("#pp-legend-manual").hidden = !count.manual;
  }

  // The steps from CEF's average so far to the forecast change for `fuel`, in c/l of
  // price change (positive = up). They add up to the forecast exactly.
  function breakdownSteps(fuel) {
    const pred = state.data.predictions[fuel];
    const report = state.data.latest_official_report;
    const close = state.data.review_period_close;
    const steps = [];
    const official = -pred.official_avg_over_under;
    steps.push({
      label: "CEF's average so far", sub: `${pred.official_days_count} official days`, value: official, kind: "official",
      tip: `CEF's average for the ${pred.official_days_count} days it has published (${fmtShortDate(report.period_start)} ` +
        `to ${fmtShortDate(report.period_end)}) is a ${fmtOverUnder(pred.official_avg_over_under)}. If the review period ` +
        `ended today, that alone would move the price by ${fmtRandBare(official)}.`,
    });
    const extra = pred.estimated_days.length + pred.manual_days.length;
    if (extra) {
      const v = -(pred.blended_avg_over_under - pred.official_avg_over_under);
      steps.push({
        label: "Days CEF hasn't published", sub: `${plural(extra, "day")}, estimated`, value: v, kind: "estimate",
        tip: `This tool's figures for ${plural(extra, "day")} CEF hasn't published yet move the average by ${fmtRandBare(v)}.`,
      });
    }
    if (pred.projected_days_count) {
      const v = -(pred.projected_avg_over_under - pred.blended_avg_over_under);
      steps.push({
        label: "Rest of the period", sub: `${plural(pred.projected_days_count, "day")} at today's price`, value: v, kind: "estimate",
        tip: `The other ${plural(pred.projected_days_count, "day")} to ${fmtShortDate(close)} are assumed to stay at the ` +
          `latest Basic Fuel Price, which moves the average by ${fmtRandBare(v)}. This is the part most likely to change.`,
      });
    }
    if (pred.follows) {
      const own = -pred.projected_avg_over_under;
      const v = pred.predicted_pump_price_change_c_per_l - own;
      steps.push({
        label: "Matched to petrol 95", sub: "93 usually moves with 95", value: v, kind: "estimate",
        tip: `The official change for petrol 93 usually matches petrol 95's, so the forecast uses 95's. ` +
          `On its own figures, 93 would be at ${fmtRandBare(own)}.`,
      });
    }
    const lc = onForecastDate(state.data.levy_change), sc = onForecastDate(state.data.slate_change);
    if (lc && lc.change[fuel]) {
      const v = lc.change[fuel];
      steps.push({
        label: v < 0 ? "Fuel levy cut" : "Fuel levy back up", sub: `announced in the ${lc.source}`, value: v, kind: "announced",
        tip: v < 0 ? `The fuel levy cut announced in the ${lc.source} on ${fmtDate(lc.announced)}.`
          : `The fuel levy going back up as the ${lc.source} relief (announced ${fmtDate(lc.announced)}) winds down.`,
      });
    }
    if (sc && sc.change[fuel]) {
      const v = sc.change[fuel];
      steps.push({
        label: `Slate levy ${v > 0 ? "up" : "down"}`, sub: `announced by the ${sc.source}`, value: v, kind: "announced",
        tip: `The slate levy going ${v > 0 ? "up" : "down"} to ${fmtRand(sc.to).replace("/l", "")} a litre, announced by the ` +
          `${sc.source} on ${fmtDate(sc.announced)}.`,
      });
    }
    return steps;
  }

  // A diagonal hatch in `color` (6-digit hex), for the bars that are estimates. The
  // progress strip's estimated days use the same idea in style.css.
  function hatch(color) {
    const c = document.createElement("canvas");
    c.width = c.height = 8;
    const g = c.getContext("2d");
    g.fillStyle = color + "2e";
    g.fillRect(0, 0, 8, 8);
    g.strokeStyle = color + "c0";
    g.lineWidth = 2;
    g.beginPath();
    for (const o of [-8, 0, 8]) { g.moveTo(o, 8); g.lineTo(o + 8, 0); }
    g.stroke();
    return g.createPattern(c, "repeat");
  }

  // Splits a tooltip sentence into lines of about `width` characters.
  function wrapText(text, width = 46) {
    const lines = [];
    let line = "";
    for (const word of text.split(" ")) {
      if (line && (line + " " + word).length > width) { lines.push(line); line = word; }
      else line = line ? line + " " + word : word;
    }
    if (line) lines.push(line);
    return lines;
  }

  // Draws on the waterfall: dashed connectors from each step's end to the next bar,
  // each step's signed value beyond the end it moves to, and the likely range as a
  // bracket across the forecast bar.
  function waterfallMarks(bars, range, narrow) {
    return {
      id: "waterfallMarks",
      afterDatasetsDraw(chart) {
        const ctx = chart.ctx;
        const xs = chart.scales.x, meta = chart.getDatasetMeta(0);
        const text = cssVar("--text-primary"), muted = cssVar("--text-muted");
        const font = getComputedStyle(document.body).fontFamily;
        ctx.save();
        ctx.strokeStyle = muted;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        for (let i = 0; i < bars.length - 1; i++) {
          const x = xs.getPixelForValue(bars[i].end);
          const a = meta.data[i], b = meta.data[i + 1];
          ctx.beginPath();
          ctx.moveTo(x, a.y + a.height / 2);
          ctx.lineTo(x, b.y - b.height / 2);
          ctx.stroke();
        }
        ctx.setLineDash([]);
        if (range) {
          const el = meta.data[bars.length - 1];
          const x0 = xs.getPixelForValue(range.lo), x1 = xs.getPixelForValue(range.hi);
          const cap = el.height / 2 + 4;
          ctx.strokeStyle = text;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(x0, el.y); ctx.lineTo(x1, el.y);
          ctx.moveTo(x0, el.y - cap); ctx.lineTo(x0, el.y + cap);
          ctx.moveTo(x1, el.y - cap); ctx.lineTo(x1, el.y + cap);
          ctx.stroke();
        }
        if (narrow) {
          // No room beside the bars on a phone, so each step's name goes above its
          // bar, on a patch of background so the connectors don't run through it.
          ctx.font = `12px ${font}`;
          ctx.textAlign = "left";
          ctx.textBaseline = "bottom";
          bars.forEach((bar, i) => {
            const el = meta.data[i];
            const name = `${bar.label} · ${bar.sub}`, y = el.y - el.height / 2 - 5;
            ctx.fillStyle = cssVar("--surface-1") + "e6";
            ctx.fillRect(chart.chartArea.left - 2, y - 15, ctx.measureText(name).width + 6, 16);
            ctx.fillStyle = cssVar("--text-secondary");
            ctx.fillText(name, chart.chartArea.left, y);
          });
        }
        ctx.font = `600 13px ${font}`;
        ctx.textBaseline = "middle";
        ctx.fillStyle = text;
        bars.forEach((bar, i) => {
          const el = meta.data[i];
          let lo = Math.min(bar.start, bar.end), hi = Math.max(bar.start, bar.end);
          if (range && bar.kind === "total") { lo = Math.min(lo, range.lo); hi = Math.max(hi, range.hi); }
          const left = bar.value < 0;
          ctx.textAlign = left ? "right" : "left";
          ctx.fillText(fmtRandBare(bar.value), xs.getPixelForValue(left ? lo : hi) + (left ? -8 : 8), el.y);
        });
        ctx.restore();
      },
    };
  }

  // "How the forecast adds up": the period's progress, CEF's latest official
  // average in words, and the waterfall from it to the forecast (hatched = estimate),
  // with a table of the same steps for screen readers.
  let chartWaterfall = null, waterfallNarrow = null;
  // The waterfall is laid out differently on narrow screens, so redraw it when the
  // width crosses that line (a phone turned sideways, say).
  let waterfallResize = 0;
  window.addEventListener("resize", () => {
    clearTimeout(waterfallResize);
    waterfallResize = setTimeout(() => {
      if (state.data && waterfallNarrow !== null && ($("#waterfall-wrap").clientWidth < 560) !== waterfallNarrow) renderBreakdown();
    }, 200);
  });
  function renderBreakdown() {
    const fuel = state.fuel;
    const pred = state.data.predictions[fuel];
    const report = state.data.latest_official_report;
    const changeDate = state.data.predicted_change_date;
    renderProgress();

    $("#breakdown-title").textContent = `How the ${fmtShortDate(changeDate)} forecast adds up`;
    const avg = pred.official_avg_over_under;
    const asChange = fmtRand(Math.abs(avg)).replace("/l", "");
    $("#cef-latest").innerHTML =
      `<strong>CEF's latest official figure</strong> (its report for ${fmtShortDate(report.report_date)}, ` +
      `${pred.official_days_count} days into the period): an average <strong>${fmtOverUnder(avg)}</strong>. ` +
      `If the period ended today, that alone would mean ${avg >= 0 ? "a" : "an"} <strong>${asChange} ` +
      `${avg >= 0 ? "cut" : "increase"}</strong>.`;

    const steps = breakdownSteps(fuel);
    const estimates = steps.some((s) => s.kind === "estimate");
    $("#cef-latest").insertAdjacentText("beforeend", estimates
      ? " The rest of the forecast is this tool's estimate."
      : " That covers the whole review period, so only announced levy changes come on top.");
    let run = 0;
    const bars = steps.map((s) => { const start = run; run += s.value; return { ...s, start, end: run }; });
    const total = pred.predicted_pump_price_change_c_per_l + levyFor(fuel);
    const range = likelyRange(fuel, total);
    bars.push({
      label: "Forecast change", sub: fmtShortDate(changeDate), start: 0, end: total, value: total, kind: "total",
      tip: `The forecast change on ${fmtDate(changeDate)}: ${fmtRandBare(total)}.` +
        (range ? ` Likely between ${fmtRandBare(range.lo)} and ${fmtRandBare(range.hi)}.` : "") +
        (onForecastDate(state.data.slate_change) ? "" : " Before any slate-levy change."),
    });

    const up = cssVar("--status-critical"), down = cssVar("--status-good"), brand = cssVar("--brand");
    const muted = cssVar("--text-muted"), grid = cssVar("--gridline"), textSec = cssVar("--text-secondary");
    const tone = (b) => b.kind === "total" ? brand : Math.abs(b.value) < 0.5 ? muted : b.value > 0 ? up : down;
    const fill = (b) => b.kind === "estimate" ? hatch(tone(b)) : tone(b) + (b.kind === "total" ? "a6" : "bf");

    const wrap = $("#waterfall-wrap");
    const narrow = wrap.clientWidth < 560;
    waterfallNarrow = narrow;
    wrap.style.height = `${bars.length * (narrow ? 62 : 52) + 48}px`;
    const canvas = $("#chart-waterfall");
    canvas.setAttribute("aria-label",
      `How the ${fmtShortDate(changeDate)} forecast adds up: ` +
      bars.map((b) => `${b.label} ${fmtRandBare(b.value)}`).join(", ") + ". The table below has the same figures.");
    $("#waterfall-table tbody").replaceChildren(...bars.map((b) => {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.scope = "row";
      th.textContent = `${b.label} (${b.sub})`;
      const td = document.createElement("td");
      td.textContent = fmtRandBare(b.value) + (b.kind === "total" && range
        ? `, likely between ${fmtRandBare(range.lo)} and ${fmtRandBare(range.hi)}` : "");
      tr.append(th, td);
      return tr;
    }));

    // The axis runs past the bars on the side each value label sits, and ends on a
    // round 50c, R1 or R2 (whichever keeps it to about eight ticks), so its ticks are round too.
    const ends = bars.flatMap((b) => [b.start, b.end]).concat(range ? [range.lo, range.hi] : []);
    const dataMin = Math.min(0, ...ends), dataMax = Math.max(0, ...ends);
    const span = dataMax - dataMin || 100;
    const room = span * 0.24;  // about a label's width
    let needMin = dataMin, needMax = dataMax;
    bars.forEach((b) => {
      let lo = Math.min(b.start, b.end), hi = Math.max(b.start, b.end);
      if (range && b.kind === "total") { lo = Math.min(lo, range.lo); hi = Math.max(hi, range.hi); }
      if (b.value < 0) needMin = Math.min(needMin, lo - room); else needMax = Math.max(needMax, hi + room);
    });
    const step = span <= 200 ? 50 : span <= 450 ? 100 : 200;
    const axisMin = Math.floor(needMin / step) * step, axisMax = Math.ceil(needMax / step) * step;
    if (chartWaterfall) chartWaterfall.destroy();
    chartWaterfall = new Chart(canvas, {
      type: "bar",
      data: {
        labels: bars.map((b) => [b.label, b.sub]),
        datasets: [{
          data: bars.map((b) => [b.start, b.end]),
          backgroundColor: bars.map(fill),
          borderColor: bars.map(tone),
          borderWidth: 1.5,
          borderSkipped: false,
          borderRadius: 4,
          maxBarThickness: narrow ? 18 : 26,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 500 },
        layout: { padding: { top: narrow ? 18 : 4 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => bars[items[0].dataIndex].label,
              label: (ctx) => wrapText(bars[ctx.dataIndex].tip),
            },
          },
        },
        scales: {
          x: {
            min: axisMin,
            max: axisMax,
            grid: { color: grid },
            ticks: { color: textSec, stepSize: step, maxRotation: 0, autoSkipPadding: 10, callback: (v) => fmtRandBare(v) },
            title: { display: true, text: "Change per litre", color: textSec },
          },
          y: { grid: { display: false }, ticks: { display: !narrow, color: textSec, font: { size: 12 } } },
        },
      },
      plugins: [waterfallMarks(bars, range, narrow)],
    });

    const sc = onForecastDate(state.data.slate_change);
    $("#breakdown-note").textContent =
      "Solid bars are CEF's official figure and announced levy changes." +
      (estimates ? " Hatched bars are this tool's estimates: days CEF hasn't published yet and the rest of the period " +
        "held at the latest price" + (pred.follows ? ", plus matching petrol 95's change." : ".") : "") +
      (range ? ` The bracket on the forecast bar is the likely range. ${rangeExplainer(range.fr)}` : "") +
      (sc ? "" : " A slate-levy change, if there is one, comes on top. It's only known when the DMPR announces the prices, a day or two before the change.");
  }

  // Fuel names as they read mid-sentence.
  const FUEL_IN_TEXT = {
    petrol95: "petrol 95", petrol93: "petrol 93", diesel005: "diesel 0.05%", diesel0005: "diesel 0.005%", illpar: "paraffin",
  };

  // "What's moving it": the forecast's Basic Fuel Price part split into fuel prices
  // abroad and the rand (backend/price_drivers.py, the DMPR's method), as signed
  // bars out from a centre line, with the two facts behind them in words. Hidden
  // when there's no split for the fuel.
  function renderDrivers() {
    const dr = state.data.drivers;
    const d = dr && dr.fuels ? dr.fuels[state.fuel] : null;
    $("#drivers-panel").hidden = !d;
    if (!d) return;
    const rows = [
      { label: "Fuel prices abroad", sub: "world prices, in dollars", value: d.product },
      { label: "The rand", sub: "its exchange rate to the dollar", value: d.rand },
      { label: "Basic Fuel Price part", sub: "of the forecast, before levies", value: d.total, total: true },
    ];
    const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
    $("#driver-rows").replaceChildren(...rows.map((r) => {
      const row = document.createElement("div");
      row.className = "driver-row" + (r.total ? " driver-row--total" : "");
      const label = document.createElement("div");
      label.className = "driver-label";
      const sub = document.createElement("span");
      sub.textContent = r.sub;
      label.append(r.label, sub);
      const track = document.createElement("div");
      track.className = "driver-track";
      track.setAttribute("aria-hidden", "true");
      const bar = document.createElement("div");
      bar.className = "driver-bar " + (r.total ? "total" : r.value > 0 ? "up" : "down");
      const width = (Math.abs(r.value) / max) * 50;
      bar.style.width = `${width}%`;
      bar.style.left = r.value >= 0 ? "50%" : `${50 - width}%`;
      track.append(bar);
      const value = document.createElement("div");
      value.className = "driver-value";
      value.textContent = fmtRandBare(r.value);
      row.append(label, track, value);
      return row;
    }));

    const name = FUEL_IN_TEXT[d.follows || state.fuel];
    const facts = [];
    if (d.usd_prev) {
      const pct = (d.usd_cur / d.usd_prev - 1) * 100;
      facts.push(Math.abs(pct) < 0.5
        ? `In dollars, ${name} costs about the same to import as in the last review period.`
        : `In dollars, ${name} costs about ${Math.abs(pct).toFixed(0)}% ${pct < 0 ? "less" : "more"} to import than ` +
          `in the last review period. That accounts for ${fmtRandBare(d.product)}.`);
    }
    const fxMove = dr.fx_cur - dr.fx_prev;
    facts.push(Math.abs(fxMove) < 0.005
      ? `The rand is averaging R${dr.fx_cur.toFixed(2)} to the dollar, the same as in the last review period.`
      : `The rand is averaging R${dr.fx_cur.toFixed(2)} to the dollar this period, against R${dr.fx_prev.toFixed(2)} in ` +
        `the last: ${fxMove > 0 ? "weaker, which pushes prices up" : "stronger, which pulls prices down"} ` +
        `(${fmtRandBare(d.rand)}).`);
    $("#driver-facts").replaceChildren(...facts.map((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      return li;
    }));
    $("#drivers-note").textContent =
      (d.follows ? "Petrol 93's forecast follows petrol 95, so this is petrol 95's split. " : "") +
      "Worked out the way the DMPR does it, which matched its November 2026 figures to the cent. Like the forecast, " +
      "it counts this tool's estimates for days CEF hasn't published and the rest of the period at today's level, " +
      "so it moves as the period fills in.";
  }

  // A miss as a size: "12c", "R1.32".
  const fmtMiss = (c) => c < 99.5 ? `${Math.round(c)}c` : `R${(c / 100).toFixed(2)}`;

  // Track record (backend/track_record.py): for each recent price change, the
  // forecast with 10 and 5 review days to go, the final Basic Fuel Price part, the
  // levy and other decisions, and the official change, with a summary of how close
  // the forecasts came. Replayed forecasts are italic with a †. Hidden when there's
  // no record for the fuel.
  function renderTrackRecord() {
    const tr = state.data.track_record;
    const rows = tr && tr.fuels ? tr.fuels[state.fuel] || [] : [];
    $("#track-panel").hidden = !rows.length;
    if (!rows.length) return;
    const stages = tr.stages.map(String);

    const summarise = (s) => {
      const misses = rows.filter((r) => r.stages[s]).map((r) => Math.abs(r.stages[s].value - r.final)).sort((a, b) => a - b);
      if (!misses.length) return null;
      const mid = misses.length / 2;
      const median = misses.length % 2 ? misses[Math.floor(mid)] : (misses[mid - 1] + misses[mid]) / 2;
      return { n: misses.length, within: misses.filter((m) => m <= 25).length, median };
    };
    const parts = stages.map((s) => ({ s, sum: summarise(s) })).filter((p) => p.sum);
    $("#track-summary").textContent = parts.map(({ s, sum }, i) => i === 0
      ? `With ${s} days of the review period to go, the forecast was within 25c of the final figure for ` +
        `${sum.within} of the last ${sum.n} price changes (typical miss ${fmtMiss(sum.median)}).`
      : `With ${s} days to go: ${sum.within} of ${sum.n} (typical miss ${fmtMiss(sum.median)}).`).join(" ");

    let replayed = false;
    const cell = (row, s) => {
      const st = row.stages[s];
      if (!st) return '<td class="num">—</td>';
      const rep = st.source === "replayed";
      replayed = replayed || rep;
      return `<td class="num${rep ? " replayed" : ""}">${fmtRandBare(st.value)}${rep ? '<sup class="fn-mark">†</sup>' : ""}` +
        `<span class="miss">${fmtMiss(Math.abs(st.value - row.final))} off</span></td>`;
    };
    $("#track-table tbody").innerHTML = rows.map((row) => `<tr>
        <td>${fmtDate(row.effective)}</td>
        ${stages.map((s) => cell(row, s)).join("")}
        <td class="num">${fmtRandBare(row.final)}</td>
        <td class="num">${fmtRandBare(row.official - row.final)}</td>
        <td class="num">${fmtRandBare(row.official)}</td>
      </tr>`).join("");

    const notes = [];
    if (replayed && tr.logging_since) {
      notes.push(`<sup class="fn-mark">†</sup> Replayed: worked out afterwards from CEF's daily figures the way the site ` +
        `forecasts, because the site only started keeping its forecasts on ${fmtDate(tr.logging_since)}. ` +
        "The others are what it showed at the time.");
    }
    notes.push("Levies &amp; other is the official change minus the final Basic Fuel Price part: fuel levy and slate " +
      "levy decisions, and rounding. It's large in months when either levy changed.");
    if (state.fuel === "petrol93") notes.push("Petrol 93's forecast follows petrol 95, so this is petrol 95's record.");
    else if (state.fuel !== "petrol95") notes.push(`The official change is for CEF's ${PRICE_ROW_LABEL[state.fuel].toLowerCase()}.`);
    $("#track-notes").innerHTML = notes.map((t) => `<p>${t}</p>`).join("");
  }

  // Options shared by every chart in this file. The tooltip skips empty points and,
  // on the "Our estimate" diamonds, says how far that estimate was from CEF.
  function chartOptions(grid, textSec, unit) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: true,
          position: "top",
          align: "start",
          labels: { color: textSec, boxWidth: 16, boxHeight: 2, usePointStyle: false, font: { size: 13 } },
        },
        tooltip: {
          filter: (item) => item.parsed.y !== null && item.parsed.y !== undefined,
          callbacks: {
            label: (ctx) => {
              const day = ctx.dataset.estimateFor && ctx.dataset.estimateFor[ctx.dataIndex];
              if (day && day.estimate) {
                const e = describeEstimate(day.estimate, day.bfp);
                return `Our estimate was ${e.estimate} ${unit}, ${e.verdict}`;
              }
              return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)} ${unit}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { color: grid, display: false }, ticks: { color: textSec, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
        y: { grid: { color: grid }, ticks: { color: textSec }, title: { display: true, text: unit, color: textSec }, grace: "10%" },
      },
    };
  }

  // Adds days to an ISO date. Done in UTC so daylight saving can't skip or repeat a day.
  const shiftIsoDate = (iso, days) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
  };

  // Footnotes for table rows without a CEF report, and which one a date gets.
  const NO_DATA_NOTES = {
    "*": "Weekend. CEF only publishes on weekdays.",
    "**": "CEF didn't publish a report for this weekday (rare). Any figure shown is an estimate for reference only and isn't counted in the prediction.",
  };

  function noDataReason(iso) {
    const weekday = new Date(iso + "T00:00:00Z").getUTCDay();
    if (weekday === 0 || weekday === 6) return { badge: "Weekend", mark: "*" };
    return { badge: "No report", mark: "**" };
  }

  // The day-by-day table for the current review period, newest first. Every
  // calendar day gets a row: published and estimated days show their figures;
  // weekends and the odd weekday CEF skipped get a row saying why, with the
  // backend's indicative estimate if it made one (shown for reference only).
  function renderTable() {
    const byDate = new Map(state.data.daily_series[state.fuel].map((d) => [d.date, d]));
    const indicative = new Map(((state.data.indicative_days || {})[state.fuel] || []).map((d) => [d.date, d]));
    const start = state.data.latest_official_report.period_start;
    const lastSeries = [...byDate.keys()].sort().pop() || start;
    const generated = state.data.generated_at.slice(0, 10);
    let end = generated > lastSeries ? generated : lastSeries;
    const close = state.data.review_period_close;
    // Runs to today, but stops at the period's last day once the period has closed
    // (days after it belong to the next price change).
    if (close && end > close && lastSeries <= close) end = close;
    const tbody = $("#daily-table tbody");
    tbody.innerHTML = "";
    const usedMarks = new Set();
    for (let iso = end; iso >= start; iso = shiftIsoDate(iso, -1)) {
      const d = byDate.get(iso);
      if (!d) {
        const reason = noDataReason(iso);
        const est = indicative.get(iso);
        usedMarks.add(reason.mark);
        const mark = `<sup class="fn-mark">${reason.mark}</sup>`;
        const tr = document.createElement("tr");
        tr.className = "no-data-row";
        tr.innerHTML = `
          <td>${fmtDate(iso)}</td>
          <td><span class="src-badge none">${reason.badge}</span></td>
          ${est
            ? `<td class="num est-value">${fmtCents(est.bfp)}${mark}</td><td class="num est-value">${fmtCents(est.unit_over_under)}${mark}</td>`
            : `<td class="num">No figures${mark}</td><td class="num">—</td>`}`;
        tbody.appendChild(tr);
        continue;
      }
      const tr = document.createElement("tr");
      const srcLabel = d.source === "cef_official" ? "CEF official" : d.source === "estimated" ? "Estimated" : "Manual";
      tr.innerHTML = `
        <td>${d.estimate
          ? `<span class="has-compare" tabindex="0" data-est="${d.estimate.bfp}" data-official="${d.bfp}" data-err="${d.estimate.error_c_per_l}" data-pct="${d.estimate.pct_error ?? ""}">${fmtDate(d.date)}</span>`
          : fmtDate(d.date)}</td>
        <td><span class="src-badge ${d.source}">${srcLabel}</span></td>
        <td class="num">${fmtCents(d.bfp)}</td>
        <td class="num">${fmtCents(d.unit_over_under)}</td>
      `;
      tbody.appendChild(tr);
    }
    $("#table-notes").innerHTML = ["*", "**"]
      .filter((m) => usedMarks.has(m))
      .map((m) => `<p><sup class="fn-mark">${m}</sup> ${NO_DATA_NOTES[m]}</p>`)
      .join("");
  }

  // The strip above the tabs: when the data was built, and the countdown to the next
  // price change (amber in the last three days).
  function renderStatusBar() {
    const generated = new Date(state.data.generated_at);
    $("#last-updated").textContent =
      `Data updated ${generated.toLocaleDateString("en-ZA", { day: "2-digit", month: "short" })} at ${generated.toLocaleTimeString("en-ZA")}, refreshes every hour`;

    const days = state.data.days_until_next_price_change;
    const changeDate = fmtDate(state.data.next_price_change_date);
    const pill = $("#countdown-pill");
    if (days === null || days === undefined) {
      pill.textContent = "—";
      pill.className = "status-pill countdown-pill";
      return;
    }
    const dayWord = days === 1 ? "day" : "days";
    pill.textContent = days <= 0
      ? `⏳ Price change day, ${changeDate}`
      : `⏳ ${days} ${dayWord} until the next price change (${changeDate})`;
    pill.className = "status-pill countdown-pill" + (days <= 3 ? " urgent" : "");
  }

  // Tooltip on table dates that were estimated first: our estimate against CEF's
  // figure. One shared element, shown on hover or keyboard focus, placed above the
  // date (or below it if there's no room) and hidden on scroll.
  const compareTip = document.createElement("div");
  compareTip.className = "compare-tip";
  compareTip.setAttribute("role", "tooltip");
  compareTip.hidden = true;
  document.body.appendChild(compareTip);

  function showCompareTip(el) {
    const est = {
      bfp: parseFloat(el.dataset.est),
      error_c_per_l: parseFloat(el.dataset.err),
      pct_error: el.dataset.pct === "" ? null : parseFloat(el.dataset.pct),
    };
    const e = describeEstimate(est, parseFloat(el.dataset.official));
    compareTip.innerHTML = `
      <div class="compare-tip-title">Estimate vs. CEF official</div>
      <div class="compare-tip-row"><span>Our estimate</span><strong>${e.estimate} c/l</strong></div>
      <div class="compare-tip-row"><span>CEF official</span><strong>${e.official} c/l</strong></div>
      <div class="compare-tip-verdict">Estimate was ${e.verdict}</div>`;
    compareTip.hidden = false;
    const r = el.getBoundingClientRect();
    const tr = compareTip.getBoundingClientRect();
    let left = r.left;
    let top = r.top - tr.height - 8;
    if (top < 8) top = r.bottom + 8;
    left = Math.max(8, Math.min(left, window.innerWidth - tr.width - 8));
    compareTip.style.left = `${left}px`;
    compareTip.style.top = `${top}px`;
  }
  const hideCompareTip = () => { compareTip.hidden = true; };
  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest(".has-compare");
    if (el) showCompareTip(el); else if (!compareTip.hidden && document.activeElement?.closest?.(".has-compare") == null) hideCompareTip();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest(".has-compare");
    if (el) showCompareTip(el); else hideCompareTip();
  });
  document.addEventListener("focusout", (e) => { if (e.target.closest(".has-compare")) hideCompareTip(); });
  window.addEventListener("scroll", hideCompareTip, { passive: true });

  // The small fuel name above each per-fuel chart and the day-by-day table, so a
  // chart (or a screenshot of one) always says which fuel it is.
  function renderFuelLabels() {
    document.querySelectorAll(".chart-fuel").forEach((el) => {
      el.textContent = state.data.fuels[state.fuel] || state.fuel;
    });
  }

  // Redraws the whole page from state. Called after every load and on every tab change.
  function render() {
    buildTabs();
    renderFuelLabels();
    renderLevyBanner();
    renderStatusBar();
    renderHero();
    renderBreakdown();
    renderDrivers();
    renderAccuracy();
    renderTrackRecord();
    renderFx();
    renderCharts();
    renderTable();
    if (window.renderContext) window.renderContext(state.data.context);
  }

  // When the data was last downloaded (ms), for refreshIfStale() below.
  let loadedAt = 0;

  async function fetchData() {
    const resp = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`Request failed (${resp.status})`);
    loadedAt = Date.now();
    return resp.json();
  }

  // First load, and the button in the header: shows the loading message, then the
  // page, or an error if the data couldn't be read.
  async function loadData() {
    $("#loading").hidden = false;
    $("#error-state").hidden = true;
    $("#content").hidden = true;
    try {
      state.data = await fetchData();
      $("#loading").hidden = true;
      $("#content").hidden = false;
      render();
    } catch (err) {
      $("#loading").hidden = true;
      $("#error-state").hidden = false;
      $("#error-state").textContent = "Couldn't load data: " + err.message;
    }
  }

  // "Check for update" downloads status.json again. The page can't make the data
  // newer: that only happens when the hourly publish pushes a new file.
  $("#refresh-btn").addEventListener("click", async () => {
    const btn = $("#refresh-btn");
    btn.disabled = true;
    btn.textContent = "Checking…";
    await loadData();
    btn.disabled = false;
    btn.textContent = "Check for update";
  });

  // A tab left open, or one a phone brings back from memory, keeps showing what it
  // drew when it was first opened (an old price step, for one). So fetch again when
  // the page comes back into view after a while, and every so often while it's
  // shown, and redraw in place if the bot has published since.
  const STALE_MS = 10 * 60 * 1000;
  async function refreshIfStale() {
    if (document.hidden || !state.data || Date.now() - loadedAt < STALE_MS) return;
    try {
      const data = await fetchData();
      if (data.generated_at === state.data.generated_at) return;
      state.data = data;
      render();
    } catch {
      // Keep what's on screen; "Check for update" still shows the error.
    }
  }
  document.addEventListener("visibilitychange", refreshIfStale);
  window.addEventListener("pageshow", (e) => { if (e.persisted) refreshIfStale(); });
  setInterval(refreshIfStale, STALE_MS);

  loadData();
})();
