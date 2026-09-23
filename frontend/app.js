(() => {
  "use strict";

  Chart.defaults.font.family = '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 13;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.boxPadding = 4;

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
  const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "2-digit", month: "short", year: "numeric" });

  async function api(path, opts) {
    const resp = await fetch(path, opts);
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || `Request failed (${resp.status})`);
    return body;
  }

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

  function renderHero() {
    const pred = state.data.predictions[state.fuel];
    const dir = pred.direction; // "increase" | "decrease" | "no change"

    $("#hero-current").textContent = fmtRand(pred.current_price_c_per_l);
    $("#hero-current-label").textContent = PRICE_ROW_LABEL[state.fuel] + " (current cycle)";

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
    $("#hero-confidence").textContent = conf + " in this review period so far";

    $("#period-range").textContent =
      `${fmtDate(state.data.latest_official_report.period_start)} – ${fmtDate(state.data.latest_official_report.period_end)} (to date)`;
  }

  function renderCharts() {
    const series = [...state.data.daily_series[state.fuel]].sort((a, b) => a.date.localeCompare(b.date));
    const refPrice = state.data.predictions[state.fuel] ? null : null;
    const referenceValue = state.data.latest_official_report.reference_price[state.fuel];

    const labels = series.map((d) => fmtDate(d.date));
    const bfpValues = series.map((d) => d.bfp);
    const refValues = series.map(() => referenceValue);
    const isEstimated = series.map((d) => d.source !== "cef_official");

    const blue = cssVar("--series-blue");
    const orange = cssVar("--series-orange");
    const red = cssVar("--series-red");
    const muted = cssVar("--text-muted");
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
            pointStyle: (ctx) => isEstimated[ctx.dataIndex] ? "circle" : "circle",
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
            label: "Built into current pump price",
            data: refValues,
            borderColor: orange,
            backgroundColor: orange,
            borderWidth: 2,
            borderDash: [2, 3],
            pointRadius: 0,
            tension: 0,
            fill: false,
          },
        ],
      },
      options: chartOptions(grid, textSec, "c/l"),
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
      options: chartOptions(grid, textSec, "c/l"),
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
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y === null ? "—" : ctx.parsed.y.toFixed(2)} ${unit}`,
          },
        },
      },
      scales: {
        x: { grid: { color: grid, display: false }, ticks: { color: textSec, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
        y: { grid: { color: grid }, ticks: { color: textSec }, title: { display: true, text: unit, color: textSec }, grace: "10%" },
      },
    };
  }

  function renderTable() {
    const series = [...state.data.daily_series[state.fuel]].sort((a, b) => b.date.localeCompare(a.date));
    const tbody = $("#daily-table tbody");
    tbody.innerHTML = "";
    series.forEach((d) => {
      const tr = document.createElement("tr");
      const srcLabel = d.source === "cef_official" ? "CEF official" : d.source === "estimated" ? "Estimated" : "Manual";
      tr.innerHTML = `
        <td>${fmtDate(d.date)}</td>
        <td><span class="src-badge ${d.source}">${srcLabel}</span></td>
        <td class="num">${fmtCents(d.bfp)}</td>
        <td class="num">${fmtCents(d.unit_over_under)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderManualForm() {
    $("#mf-fuel-label").textContent = state.data.fuels[state.fuel];
    const min = state.data.latest_official_report.period_start;
    const dateInput = $("#mf-date");
    dateInput.min = min;
    if (!dateInput.value) dateInput.value = new Date().toISOString().slice(0, 10);
  }

  async function renderManualList() {
    const overrides = await api("/api/manual-overrides");
    const container = $("#manual-list");
    container.innerHTML = "";
    const dates = Object.keys(overrides).sort().reverse();
    if (!dates.length) {
      container.innerHTML = `<p class="muted small">No manual entries yet.</p>`;
      return;
    }
    dates.forEach((date) => {
      const entry = overrides[date];
      const row = document.createElement("div");
      row.className = "manual-list-row";
      const bfpStr = Object.entries(entry.bfp).map(([f, v]) => `${state.data.fuels[f] || f}: ${v}`).join(", ");
      row.innerHTML = `
        <span>${fmtDate(date)} — ${bfpStr}${entry.exchange_rate ? ` (FX ${entry.exchange_rate})` : ""}</span>
        <button class="btn btn-danger" data-date="${date}">Remove</button>
      `;
      row.querySelector("button").addEventListener("click", async (e) => {
        await api(`/api/manual-override/${date}`, { method: "DELETE" });
        await loadData();
      });
      container.appendChild(row);
    });
  }

  function renderStatusBar() {
    const generated = new Date(state.data.generated_at);
    $("#last-updated").textContent =
      `Live — loaded ${generated.toLocaleDateString("en-ZA", { day: "2-digit", month: "short" })} at ${generated.toLocaleTimeString("en-ZA")}`;

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

  function render() {
    buildTabs();
    renderStatusBar();
    renderHero();
    renderAccuracy();
    renderFx();
    renderCharts();
    renderTable();
    renderManualForm();
    renderManualList();
  }

  async function loadData() {
    $("#loading").hidden = false;
    $("#error-state").hidden = true;
    $("#content").hidden = true;
    try {
      state.data = await api("/api/status");
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
    btn.textContent = "Refreshing…";
    try {
      await api("/api/refresh", { method: "POST" });
      await loadData();
    } catch (err) {
      alert("Refresh failed: " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Refresh data";
    }
  });

  $("#manual-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const date = $("#mf-date").value;
    const bfp = parseFloat($("#mf-bfp").value);
    const fx = $("#mf-fx").value ? parseFloat($("#mf-fx").value) : null;
    try {
      await api("/api/manual-override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, bfp: { [state.fuel]: bfp }, exchange_rate: fx }),
      });
      $("#mf-bfp").value = "";
      $("#mf-fx").value = "";
      await loadData();
    } catch (err) {
      alert("Couldn't save: " + err.message);
    }
  });

  loadData();
})();
