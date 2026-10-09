/* Background section at the bottom of the page: Brent futures vs. physical spot
   and Strait of Hormuz traffic, from data.context (backend/context_data.py).
   None of it feeds the prediction. Identical in docs/ and frontend/; app.js
   calls window.renderContext(data.context) on every render. Each block hides
   itself when its data is missing. */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmtDay = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "numeric", month: "short" });
  const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
  const fmtMonth = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { month: "short", year: "numeric" });
  const usd = (v) => `$${v.toFixed(2)}`;
  const narrow = () => window.innerWidth < 600;

  let chartBrent = null, chartHormuz = null;

  // ---------------------------------------------------------------- the art
  // A tanker riding the swell, just for decoration (aria-hidden). Wave layers
  // slide by exactly one wavelength per loop, so the loop is seamless; the
  // ship rocks gently and the funnel puffs smoke. All motion is CSS (style.css,
  // .tanker-art) and stops under prefers-reduced-motion.
  function wave(y, amp, period) {
    let d = `M${-period},${y}`;
    for (let x = -period; x < 1000 + period; x += period) d += ` q${period / 4},${-amp} ${period / 2},0 t${period / 2},0`;
    return d + " V130 H" + -period + " Z";
  }

  function drawTanker() {
    const host = $("#tanker-art");
    if (!host || host.dataset.drawn) return;
    host.dataset.drawn = "1";
    host.innerHTML = `
      <svg viewBox="0 0 1000 130" preserveAspectRatio="xMidYMax slice" focusable="false">
        <circle class="ta-moon-glow" cx="842" cy="30" r="26"/>
        <circle class="ta-moon" cx="842" cy="30" r="11"/>
        <g class="ta-far-ship"><path d="M0,0 h34 l6,-3 l-3,7 h-35 z M4,0 v-7 h8 v7 z"/></g>
        <g class="ta-wave ta-wave--back" style="--wl:-90px"><path d="${wave(96, 4, 90)}"/></g>
        <g transform="translate(340,80)">
          <g class="ta-ship">
            <g class="ta-smoke">
              <circle cx="32" cy="-66" r="5"/><circle cx="32" cy="-66" r="5"/><circle cx="32" cy="-66" r="5"/>
            </g>
            <path class="ta-funnel" d="M23,-42 L25,-63 L41,-63 L41,-42 Z"/>
            <rect class="ta-funnel-band" x="24.2" y="-57" width="16.8" height="5"/>
            <path class="ta-mast" d="M50,-42 V-58 M45,-54 H55 M300,-6 V-24 M296,-19 H304"/>
            <rect class="ta-house" x="8" y="-36" width="48" height="36"/>
            <rect class="ta-bridge" x="2" y="-43" width="60" height="7"/>
            <path class="ta-windows" d="M6,-41 h52 M14,-29 h4 M24,-29 h4 M34,-29 h4 M44,-29 h4 M14,-19 h4 M24,-19 h4 M34,-19 h4 M44,-19 h4"/>
            <path class="ta-hull" d="M0,0 L322,-6 L300,30 L14,30 Z"/>
            <path class="ta-boot" d="M7,19 L309,19 L300,30 L14,30 Z"/>
            <path class="ta-deck" d="M0,0 L322,-6"/>
            <path class="ta-pipes" d="M64,-4 L286,-8 M160,-5 V-15 L176,-12 M220,-6 V-14"/>
            <path class="ta-name" d="M286,8 h18"/>
          </g>
        </g>
        <g class="ta-wave ta-wave--mid" style="--wl:-120px"><path d="${wave(103, 5, 120)}"/></g>
        <g class="ta-wave ta-wave--front" style="--wl:-150px"><path d="${wave(112, 6, 150)}"/></g>
      </svg>`;
  }

  // ---------------------------------------------------------------- charts
  function baseOptions(unit) {
    const grid = cssVar("--gridline");
    const textSec = cssVar("--text-secondary");
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: true, position: "top", align: "start",
          labels: { color: textSec, boxWidth: 16, boxHeight: 2, font: { size: 13 } },
        },
        tooltip: { filter: (item) => item.parsed.y !== null && item.parsed.y !== undefined },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: textSec, maxRotation: 0, autoSkip: true, maxTicksLimit: narrow() ? 4 : 7 } },
        y: { grid: { color: grid }, ticks: { color: textSec }, title: { display: true, text: unit, color: textSec }, grace: "8%" },
      },
    };
  }

  function renderBrent(fut, spot) {
    const block = $("#ctx-brent");
    if (!fut && !spot) { block.hidden = true; return; }
    block.hidden = false;

    const futMap = new Map((fut ? fut.series : []).map(([d, v]) => [d, v]));
    const spotMap = new Map((spot ? spot.series : []).map(([d, v]) => [d, v]));
    // Same window for both lines: from the later of the two starts.
    const start = [fut, spot].filter(Boolean).map((p) => p.series[0][0]).sort().pop();
    const dates = [...new Set([...futMap.keys(), ...spotMap.keys()])].filter((d) => d >= start).sort();

    const figs = [];
    if (fut) figs.push(stat("Futures (in the news)", usd(fut.series[fut.series.length - 1][1]), `a barrel, ${fmtDay(fut.data_to)}`));
    if (spot) figs.push(stat("Physical cargoes (Dated Brent)", usd(spot.series[spot.series.length - 1][1]), `a barrel, ${fmtDay(spot.data_to)}`));
    if (fut && spot) {
      // Compare on the same day: the latest day both have.
      const day = [...spotMap.keys()].reverse().find((d) => futMap.has(d));
      if (day) {
        const gap = spotMap.get(day) - futMap.get(day);
        figs.push(stat("Physical minus futures", `${gap >= 0 ? "+" : "−"}${usd(Math.abs(gap))}`, `a barrel, ${fmtDay(day)}`, Math.abs(gap) >= 5 ? "alert" : ""));
      }
    }
    $("#ctx-brent-figures").replaceChildren(...figs);

    const blue = cssVar("--series-blue");
    const orange = cssVar("--series-orange");
    const line = (label, map, color) => ({
      label, data: dates.map((d) => map.has(d) ? map.get(d) : null),
      borderColor: color, backgroundColor: color, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4,
      tension: 0, spanGaps: true, fill: false,
    });
    const opts = baseOptions("$/barrel");
    opts.plugins.tooltip.callbacks = { label: (ctx) => `${ctx.dataset.label}: ${usd(ctx.parsed.y)}` };
    if (chartBrent) chartBrent.destroy();
    chartBrent = new Chart($("#chart-brent"), {
      type: "line",
      data: {
        labels: dates.map(fmtDay),
        datasets: [
          ...(spot ? [line("Physical (Dated Brent)", spotMap, orange)] : []),
          ...(fut ? [line("Futures", futMap, blue)] : []),
        ],
      },
      options: opts,
    });

    const parts = [];
    if (fut) parts.push(`futures to ${fmtDate(fut.data_to)}`);
    if (spot) parts.push(`physical to ${fmtDate(spot.data_to)} (the EIA publishes it weekly)`);
    $("#ctx-brent-asof").textContent = "Data: " + parts.join("; ") + ".";
  }

  // Dotted vertical lines for events (h.events, from context_data.py). An event
  // with a "to" date gets a line at each end and faint shading between. Each
  // label sits on its own row so neighbouring labels never overlap.
  const eventsPlugin = (series, events) => ({
    id: "ctxEvents",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      ctx.save();
      for (const ev of events) {
        if (!ev.to) continue;
        const a = series.findIndex((r) => r[0] >= ev.from);
        let b = series.findIndex((r) => r[0] >= ev.to);
        if (a < 0) continue;
        if (b < 0) b = series.length - 1;
        const x0 = scales.x.getPixelForValue(a), x1 = scales.x.getPixelForValue(b);
        ctx.fillStyle = cssVar("--series-blue") + "1f";
        ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.bottom - chartArea.top);
      }
      ctx.restore();
    },
    afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      ctx.save();
      ctx.font = "12px " + getComputedStyle(document.body).fontFamily;
      events.forEach((ev, row) => {
        const xs = [ev.from, ev.to].filter(Boolean)
          .map((d) => series.findIndex((r) => r[0] >= d))
          .filter((i) => i >= 0)
          .map((i) => scales.x.getPixelForValue(i));
        if (!xs.length) return;
        ctx.strokeStyle = cssVar("--text-muted");
        ctx.setLineDash([2, 3]);
        for (const x of xs) {
          ctx.beginPath();
          ctx.moveTo(x, chartArea.top);
          ctx.lineTo(x, chartArea.bottom);
          ctx.stroke();
        }
        ctx.setLineDash([]);
        ctx.fillStyle = cssVar("--text-secondary");
        const w = ctx.measureText(ev.label).width;
        const x = xs.length > 1 ? (xs[0] + xs[1]) / 2 - w / 2 : xs[0] + 6;
        ctx.fillText(ev.label, Math.max(chartArea.left + 2, Math.min(x, chartArea.right - w)), chartArea.top + 12 + row * 16);
      });
      ctx.restore();
    },
  });

  function renderHormuz(h) {
    const block = $("#ctx-hormuz");
    if (!h) { block.hidden = true; return; }
    block.hidden = false;

    const s = h.series;
    const avg = s.map((_, i) => {
      if (i < 6) return null;
      let sum = 0;
      for (let j = i - 6; j <= i; j++) sum += s[j][1];
      return Math.round((sum / 7) * 10) / 10;
    });

    $("#ctx-hormuz-figures").replaceChildren(
      stat("Ships a day seen crossing", h.avg_7d.toFixed(1), `7-day average to ${fmtDay(h.data_to)}`, h.avg_7d < h.normal_per_day / 2 ? "alert" : ""),
      stat("Normal before the conflict", h.normal_per_day.toFixed(0), `a day, ${fmtMonth(h.normal_from)} – ${fmtMonth(h.conflict_start)}`),
    );

    const blue = cssVar("--series-blue");
    const muted = cssVar("--text-muted");
    const opts = baseOptions("ships a day");
    opts.scales.x.ticks.callback = function (value) {
      // Quarterly labels (half-yearly on phones), the year only on January,
      // so they never crowd.
      const iso = s[value][0];
      const months = narrow() ? ["01", "07"] : ["01", "04", "07", "10"];
      if (iso.slice(8) !== "01" || !months.includes(iso.slice(5, 7))) return null;
      return iso.slice(5, 7) === "01" ? fmtMonth(iso) : new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { month: "short" });
    };
    opts.scales.x.ticks.autoSkip = false;
    opts.scales.y.beginAtZero = true;
    opts.plugins.legend.display = false; // the text under the chart explains bars, line and dashed line
    opts.plugins.tooltip.callbacks = {
      title: (items) => fmtDate(s[items[0].dataIndex][0]),
      label: (ctx) => {
        if (ctx.datasetIndex === 0) return `Seen crossing: ${ctx.parsed.y} (tankers ${s[ctx.dataIndex][2]})`;
        if (ctx.datasetIndex === 1) return `7-day average: ${ctx.parsed.y}`;
        return `Normal before the conflict: ${ctx.parsed.y}`;
      },
    };
    if (chartHormuz) chartHormuz.destroy();
    chartHormuz = new Chart($("#chart-hormuz"), {
      type: "bar",
      data: {
        labels: s.map((r) => r[0]),
        datasets: [
          {
            type: "bar", label: "Ships seen each day", data: s.map((r) => r[1]),
            backgroundColor: blue + "55", borderWidth: 0, barPercentage: 1, categoryPercentage: 1, order: 3,
          },
          {
            type: "line", label: "7-day average", data: avg, borderColor: blue, backgroundColor: blue,
            borderWidth: 2, pointRadius: 0, pointHoverRadius: 3, tension: 0.2, order: 1,
          },
          {
            type: "line", label: "Normal before the conflict", data: s.map(() => h.normal_per_day),
            borderColor: muted, backgroundColor: muted, borderWidth: 1.5, borderDash: [6, 5],
            pointRadius: 0, pointHoverRadius: 0, order: 2,
          },
        ],
      },
      options: opts,
      plugins: [eventsPlugin(s, h.events || [{ from: h.conflict_start, label: "Conflict begins" }])],
    });

    $("#ctx-hormuz-asof").textContent = `Data to ${fmtDate(h.data_to)}. PortWatch publishes a few days late and revises recent days.`;
  }

  function stat(label, value, sub, mod) {
    const box = document.createElement("div");
    box.className = "ctx-stat" + (mod ? " ctx-stat--" + mod : "");
    const l = document.createElement("div"); l.className = "ctx-stat-label"; l.textContent = label;
    const v = document.createElement("div"); v.className = "ctx-stat-value"; v.textContent = value;
    const u = document.createElement("div"); u.className = "ctx-stat-sub"; u.textContent = sub;
    box.append(l, v, u);
    return box;
  }

  window.renderContext = function (context) {
    const panel = $("#context-panel");
    if (!panel) return;
    const c = context || {};
    if (!c.brent_futures && !c.brent_spot && !c.hormuz) { panel.hidden = true; return; }
    panel.hidden = false;
    drawTanker();
    renderBrent(c.brent_futures, c.brent_spot);
    renderHormuz(c.hormuz);
  };
})();
