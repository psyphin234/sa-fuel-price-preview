(() => {
  "use strict";

  Chart.defaults.font.family = '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 13;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.boxPadding = 4;

  // Public, read-only build: data comes from a static JSON snapshot that a
  // private backend pushes to this repo on a schedule (see backend/publish.py).
  // There is no live API here - "Check for update" just re-fetches that file.
  const DATA_URL = "data/status.json";

  const FUEL_ORDER = ["petrol95", "petrol93", "diesel005", "diesel0005", "illpar"];
  const PRICE_ROW_LABEL = {
    petrol95: "Gauteng pump price",
    petrol93: "Gauteng pump price",
    diesel005: "Wholesale price",
    diesel0005: "Wholesale price",
    illpar: "Single national max retail price",
  };

  let state = { fuel: "petrol95", data: null };
  let chartBfp = null, chartRecovery = null, chartFx = null;

  const $ = (sel) => document.querySelector(sel);
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const centsToRand = (c) => (c === null || c === undefined) ? null : c / 100;
  const fmtRand = (c) => c === null || c === undefined ? "—" : `R${centsToRand(c).toFixed(2)}/l`;
  const fmtRandDelta = (c) => {
    if (c === null || c === undefined) return "—";
    const sign = c > 0 ? "+" : "";
    return `${sign}R${centsToRand(c).toFixed(2)}/l`;
  };
  const fmtCents = (c) => c === null || c === undefined ? "—" : c.toFixed(2);
  const describeEstimate = (est, official) => {
    const diff = est.error_c_per_l;
    const off = Math.abs(diff).toFixed(2);
    const pct = est.pct_error === null ? "" : ` (${Math.abs(est.pct_error).toFixed(2)}%)`;
    const verdict = Math.abs(diff) < 0.005 ? "spot on" : `${off} c/l too ${diff > 0 ? "low" : "high"}${pct}`;
    return { estimate: fmtCents(est.bfp), official: fmtCents(official), verdict };
  };
  const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "2-digit", month: "short", year: "numeric" });

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
        render();
      });
      nav.appendChild(btn);
    });
  }

  const dirClass = (c) => c > 0 ? "increase" : c < 0 ? "decrease" : "";

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

    $("#early-title").textContent = `Early look: ${fmtDate(state.data.predicted_change_date)}`;
    const earlyEl = $("#early-change");
    earlyEl.textContent = fmtRandDelta(pred.predicted_pump_price_change_c_per_l);
    earlyEl.className = "hero-value " + dirClass(pred.predicted_pump_price_change_c_per_l);
    const days = pred.blended_days_count;
    $("#early-sub").textContent =
      `About ${fmtRand(pred.predicted_new_price_c_per_l)}. Only ${days} day${days === 1 ? "" : "s"} of the review period so far, so this can still move a lot.`;
    return true;
  }

  function renderHero() {
    $("#period-range").textContent =
      `${fmtDate(state.data.latest_official_report.period_start)} – ${fmtDate(state.data.latest_official_report.period_end)} (to date)`;
    if (renderAnnounced()) return;

    const pred = state.data.predictions[state.fuel];
    const dir = pred.direction; // "increase" | "decrease" | "no change"

    $("#hero-current").textContent = fmtRand(pred.current_price_c_per_l);
    // In the days before a price change CEF already reports the upcoming price.
    const effective = state.data.latest_official_report.pump_price_effective;
    const upcoming = effective > state.data.generated_at.slice(0, 10);
    $("#hero-current-title").textContent = upcoming ? `New price from ${fmtDate(effective)}` : "Current price";
    $("#hero-current-label").textContent = PRICE_ROW_LABEL[state.fuel] + (upcoming ? " (announced)" : " (current cycle)");

    const changeDate = state.data.predicted_change_date;
    $("#hero-change-title").textContent = changeDate ? `Predicted change on ${fmtDate(changeDate)}` : "Predicted next-cycle move";

    const changeEl = $("#hero-change");
    changeEl.textContent = fmtRandDelta(pred.predicted_pump_price_change_c_per_l);
    changeEl.className = "hero-value " + (dir === "increase" ? "increase" : dir === "decrease" ? "decrease" : "");

    const badge = $("#hero-direction-badge");
    const icon = dir === "increase" ? "▲" : dir === "decrease" ? "▼" : "■";
    const label = dir === "increase" ? "Price expected to rise" : dir === "decrease" ? "Price expected to fall" : "Little change expected";
    badge.className = "hero-badge " + (dir === "increase" ? "increase" : dir === "decrease" ? "decrease" : "flat");
    badge.textContent = `${icon} ${label}`;

    $("#hero-newprice").textContent = fmtRand(pred.predicted_new_price_c_per_l);
    const officialDays = pred.official_days_count;
    const estDays = pred.estimated_days.length;
    const manDays = pred.manual_days.length;
    let conf = `${officialDays} official day${officialDays === 1 ? "" : "s"}`;
    if (estDays) conf += ` + ${estDays} estimated`;
    if (manDays) conf += ` + ${manDays} manual`;
    const projDays = pred.projected_days_count || 0;
    $("#hero-confidence").textContent = state.data.review_period_closed
      ? `Review period closed ${fmtDate(state.data.review_period_close)} — ${conf}`
      : conf + " so far" + (projDays
        ? `; the other ${projDays} day${projDays === 1 ? "" : "s"} to ${fmtDate(state.data.review_period_close)} assume the BFP stays where it is now`
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

  function renderCharts() {
    const series = [...state.data.daily_series[state.fuel]].sort((a, b) => a.date.localeCompare(b.date));
    const referenceValue = state.data.latest_official_report.reference_price[state.fuel];

    const labels = series.map((d) => fmtDate(d.date));
    const bfpValues = series.map((d) => d.bfp);
    const refValues = series.map((d) => d.reference ?? referenceValue);
    const isEstimated = series.map((d) => d.source !== "cef_official");
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
      options: withDividerRoom(chartOptions(grid, textSec, "c/l"), series),
      plugins: [cycleDivider(series)],
    });
  }

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

  function renderAccuracy() {
    const acc = state.data.accuracy;
    const fill = $("#accuracy-fill");
    const headline = $("#accuracy-headline");
    const sub = $("#accuracy-sub");

    if (!acc || acc.status === "collecting") {
      fill.style.width = "0%";
      fill.className = "accuracy-meter-fill unknown";
      headline.textContent = "Not enough data yet";
      sub.textContent = "Estimate tracking just started — the first comparison lands once CEF publishes the next official day.";
      return;
    }

    const pct = acc.accuracy_pct;
    fill.style.width = `${pct}%`;
    fill.className = "accuracy-meter-fill " + (pct >= 97 ? "" : pct >= 90 ? "warning" : "critical");
    headline.textContent = `${pct}% accurate on average`;
    const warmup = acc.status === "warming_up" ? " — still an early sample, so treat this loosely" : "";
    sub.textContent = `Based on ${acc.n} estimated day${acc.n === 1 ? "" : "s"} checked against CEF's real figures so far: typically about ${acc.mean_abs_error_c_per_l} c/l (${acc.mean_abs_pct_error}%) off${warmup}.`;
  }

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
                return `Our estimate was ${e.estimate} ${unit} — ${e.verdict}`;
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

  const shiftIsoDate = (iso, days) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
  };

  const NO_DATA_NOTES = {
    "*": "Weekend — CEF only publishes on weekdays.",
    "**": "CEF didn't publish a report for this weekday (rare). Any figure shown is an estimate for reference only and isn't counted in the prediction.",
  };

  function noDataReason(iso) {
    const weekday = new Date(iso + "T00:00:00Z").getUTCDay();
    if (weekday === 0 || weekday === 6) return { badge: "Weekend", mark: "*" };
    return { badge: "No report", mark: "**" };
  }

  function renderTable() {
    const byDate = new Map(state.data.daily_series[state.fuel].map((d) => [d.date, d]));
    const indicative = new Map(((state.data.indicative_days || {})[state.fuel] || []).map((d) => [d.date, d]));
    const start = state.data.latest_official_report.period_start;
    const lastSeries = [...byDate.keys()].sort().pop() || start;
    const generated = state.data.generated_at.slice(0, 10);
    let end = generated > lastSeries ? generated : lastSeries;
    const close = state.data.review_period_close;
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

  function renderStatusBar() {
    const generated = new Date(state.data.generated_at);
    $("#last-updated").textContent =
      `Data updated ${generated.toLocaleDateString("en-ZA", { day: "2-digit", month: "short" })} at ${generated.toLocaleTimeString("en-ZA")} — refreshes every hour`;

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
      ? `⏳ Price change day — ${changeDate}`
      : `⏳ ${days} ${dayWord} until the next price change (${changeDate})`;
    pill.className = "status-pill countdown-pill" + (days <= 3 ? " urgent" : "");
  }

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

  function render() {
    buildTabs();
    renderStatusBar();
    renderHero();
    renderAccuracy();
    renderFx();
    renderCharts();
    renderTable();
  }

  async function loadData() {
    $("#loading").hidden = false;
    $("#error-state").hidden = true;
    $("#content").hidden = true;
    try {
      const resp = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!resp.ok) throw new Error(`Request failed (${resp.status})`);
      state.data = await resp.json();
      $("#loading").hidden = true;
      $("#content").hidden = false;
      render();
    } catch (err) {
      $("#loading").hidden = true;
      $("#error-state").hidden = false;
      $("#error-state").textContent = "Couldn't load data: " + err.message;
    }
  }

  $("#refresh-btn").addEventListener("click", async () => {
    const btn = $("#refresh-btn");
    btn.disabled = true;
    btn.textContent = "Checking…";
    await loadData();
    btn.disabled = false;
    btn.textContent = "Check for update";
  });

  loadData();
})();
