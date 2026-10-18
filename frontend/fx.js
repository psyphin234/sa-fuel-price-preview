/* Visual effects, decoration only. Identical in docs/ and frontend/. Loads after
   Chart.js and before app.js:
   - the glowing circuit board behind the page (two fixed canvases),
   - the import-routes map in the header (canvas.hero-fx): Africa in dots,
     with tankers sailing the lanes fuel arrives along,
   - a soft neon glow on chart lines (a global Chart.js plugin),
   - panels fading in as they scroll into view.
   Nothing here touches the data. Under prefers-reduced-motion the circuit and the map
   are drawn once and stay still, and the fade-ins are skipped. */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------ chart glow
  if (window.Chart) {
    Chart.defaults.font.family = '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif';
    Object.assign(Chart.defaults.plugins.tooltip, {
      backgroundColor: "rgba(8,14,38,0.94)",
      borderColor: "rgba(76,201,255,0.35)",
      borderWidth: 1,
      titleColor: "#eaf2ff",
      bodyColor: "#a8b7d6",
      padding: 10,
      cornerRadius: 10,
    });
    Chart.register({
      id: "neonGlow",
      beforeDatasetDraw(chart, args) {
        const ds = args.meta.dataset && chart.data.datasets[args.index];
        if (!ds || args.meta.type !== "line" || ds.showLine === false) return;
        const ctx = chart.ctx;
        ctx.save();
        ctx.shadowColor = typeof ds.borderColor === "string" ? ds.borderColor : "#4cc9ff";
        ctx.shadowBlur = 10;
      },
      afterDatasetDraw(chart, args) {
        const ds = args.meta.dataset && chart.data.datasets[args.index];
        if (!ds || args.meta.type !== "line" || ds.showLine === false) return;
        chart.ctx.restore();
      },
    });
  }

  // --------------------------------------------------------- scroll reveal
  function setUpReveal() {
    if (reduceMotion || !("IntersectionObserver" in window)) return;
    document.documentElement.classList.add("fx-reveal");
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.classList.add("is-visible");
        io.unobserve(e.target);
      }
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.04 });
    document.querySelectorAll(".panel, .hero-card").forEach((el) => io.observe(el));
  }


  // ---------------------------------------------------------- the routes map
  // Africa (and the edges of Europe and the Middle East) as a grid of dots, South
  // Africa brighter, with glowing tankers sailing three lanes into Cape Town and
  // Durban: from the Mediterranean, from the Arab Gulf through Hormuz, and from
  // Asia. A scan line sweeps down the map and dust drifts across the header.
  // Outlines are rough (lon, lat) polygons; they only decide which grid dots light.
  const AFRICA = [[-5.9,35.8],[-2,35.1],[1,36.5],[3,36.8],[8.6,36.9],[10.3,37.3],[11.1,37],[10.2,34.2],[11.1,33.2],[15.2,32.3],[19,30.3],[20.1,31.9],[23,32.6],[25,31.6],[29.9,31.2],[32.3,31.3],[32.6,29.9],[33.6,27.5],[35.6,23.9],[37.2,19.6],[38.5,18],[39.7,15.6],[41.7,13.3],[43.3,12],[44,10.4],[45,10.4],[49,11.3],[51.3,11.8],[51,10.4],[50,7.5],[48.9,5.5],[47,3.5],[45.3,2],[42.5,-0.5],[40.5,-2.5],[39.6,-4.1],[39.3,-6.8],[39.6,-10],[40.5,-10.5],[40.6,-14.5],[40,-16],[36.8,-18],[34.8,-19.8],[35.5,-22],[35.4,-24],[32.6,-25.9],[32.9,-27],[31,-29.9],[30,-31.3],[25.6,-34],[22,-34.2],[20,-34.8],[18.4,-34],[18,-32.5],[16.5,-28.6],[15.2,-26.6],[14.5,-22.9],[13,-20],[11.8,-17.2],[12.3,-13.5],[13.2,-8.8],[12.2,-6],[11.8,-4.8],[9.5,-1.5],[9.4,0.5],[9.8,3],[9.2,4],[8.5,4.6],[6,4.3],[3.4,6.4],[1.2,6.1],[-2,4.8],[-4,5.2],[-7.5,4.4],[-10,6.5],[-11.5,7],[-13.2,8.5],[-15,10.8],[-16.7,12.5],[-17.5,14.7],[-16.5,16.2],[-16,19],[-17,21],[-15.9,23.7],[-14.5,26.1],[-13,27.6],[-11,28.7],[-9.6,30.4],[-9.8,32],[-7.6,33.6],[-6.8,34],[-6.2,35.5]];
  const MADAGASCAR = [[49.3,-12],[50.5,-15.5],[49.5,-17.5],[48,-22],[47,-25],[45.2,-25.5],[43.7,-23.5],[43.3,-21.5],[44.4,-19.5],[44,-17],[46.3,-15.8],[48,-13.5]];
  const SOUTH_AFRICA = [[16.5,-28.6],[20,-28.4],[20,-24.8],[23,-25.3],[25.8,-25.6],[27,-23.5],[29.4,-22.2],[31.3,-22.4],[32,-24.5],[31.9,-25.9],[32.9,-26.9],[31,-29.9],[30,-31.3],[25.6,-34],[22,-34.2],[20,-34.8],[18.4,-34],[18,-32.5]];
  const MIDDLE_EAST = [[34.2,31.3],[35,32.8],[35.9,35],[36,36.8],[33,36.1],[30.6,36.8],[28.5,36.6],[27.2,37.8],[26.2,39.5],[26.5,40.4],[29,41.1],[29,46],[70,46],[70,25],[66.6,25.4],[61.6,25.2],[57.3,25.8],[56.3,27.2],[54.8,26.5],[53.5,26.9],[51.5,27.9],[50.3,29.2],[48.8,30.2],[48,29.4],[48.5,28],[49.6,26.8],[50.2,26.2],[50.8,25.5],[51.2,26.1],[51.6,25.3],[51,24.6],[52,24],[54.4,24.4],[55.3,25.3],[56.3,26.4],[56.4,24.8],[57,24],[58.6,23.6],[59.8,22.5],[58.5,20.4],[57,18.9],[55,17],[52.2,15.6],[48.5,14],[45,12.8],[43.4,12.7],[42.8,14.8],[41.5,17.5],[39.2,21.5],[38.1,24.1],[36.5,26],[35,28],[34.9,29.5],[34.2,27.7],[32.7,29.8],[32.4,31.2]];
  const EUROPE = [[-9.5,38.7],[-8.9,37],[-6,36.2],[-5.4,36.1],[-2,36.7],[0,38.7],[-0.3,39.5],[3.2,41.9],[3,43],[5,43.3],[8.8,44.4],[10.5,43],[12,41.8],[14.2,40.8],[15.7,40],[16,38],[17,39],[18.5,40.1],[16,41.5],[13.5,43.6],[12.3,45.4],[13.8,45.6],[15.5,43.5],[19,42],[19.5,40.5],[21,38.5],[21.7,36.8],[23,36.4],[24,38],[22.9,40.6],[26,40.8],[28.5,41.2],[28.5,48],[-9.5,48]];
  const SICILY = [[12.4,38.1],[15.6,38.3],[15.1,36.7],[12.4,37.8]];

  const ROUTES = [
    { label: "Mediterranean", at: [5, 40.2], ships: 3, secs: 22,
      path: [[17,34],[12,36],[6,37.8],[0,37.2],[-3.5,36],[-5.6,35.95],[-8.5,35.4],[-12,32],[-15.5,27],[-19,21],[-19.5,14.5],[-15,7],[-7,2.5],[3,-1],[7,-7],[10,-14],[11.5,-21],[13,-27],[15.8,-32],[17.6,-34.4],[18.4,-33.95]] },
    { label: "Arab Gulf", at: [47, 32.2], ships: 3, secs: 24,
      path: [[49.8,28.2],[52.5,26.9],[55.5,26.6],[56.6,26.3],[57.8,25],[59.5,24],[61,21],[58.5,16.5],[54,13],[53,11.5],[52,6],[48.5,0],[44.5,-5],[42.5,-11],[41.8,-15.5],[40.2,-19.5],[37.5,-24.5],[34,-28],[31,-29.9]] },
    { label: "Asia", at: [58.5, -9.5], ships: 2, secs: 16,
      path: [[64,-11],[57,-22],[51,-28],[42,-31],[35,-31],[31,-29.9]] },
  ];
  const PORTS = [
    { name: "Durban", lon: 31, lat: -29.9, dx: 12, dy: 4, align: "left" },
    { name: "Cape Town", lon: 18.4, lat: -33.95, dx: -10, dy: 16, align: "right" },
  ];
  const LON0 = -21, LON1 = 63, LAT0 = -37.5, LAT1 = 42;

  const inPoly = (x, y, poly) => {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  };

  // A smooth curve through the waypoints (Catmull-Rom), as a dense polyline.
  function smooth(pts, steps = 10) {
    const out = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(i - 1, 0)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(i + 2, pts.length - 1)];
      for (let k = 0; k < steps; k++) {
        const t = k / steps, t2 = t * t, t3 = t2 * t;
        out.push([0, 1].map((d) => 0.5 * (2 * p1[d] + (-p0[d] + p2[d]) * t + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t2 + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * t3)));
      }
    }
    out.push(pts[pts.length - 1]);
    return out;
  }

  function setUpRouteMap() {
    const canvas = document.querySelector(".hero-fx");
    if (!canvas || !canvas.getContext) return;
    const header = canvas.parentElement;
    const text = header.querySelector(".brand-text");
    const ctx = canvas.getContext("2d");

    // Land dots on a 1.25-degree grid. kind: 2 South Africa, 1 rest of Africa, 0 elsewhere.
    const dots = [];
    for (let lat = LAT1; lat >= LAT0; lat -= 1.25) {
      for (let lon = LON0; lon <= LON1; lon += 1.25) {
        let kind = -1;
        if (inPoly(lon, lat, SOUTH_AFRICA)) kind = 2;
        else if (inPoly(lon, lat, AFRICA) || inPoly(lon, lat, MADAGASCAR)) kind = 1;
        else if (inPoly(lon, lat, MIDDLE_EAST) || inPoly(lon, lat, EUROPE) || inPoly(lon, lat, SICILY)) kind = 0;
        if (kind < 0) continue;
        // Fade out towards the top and right edges so the cut-off doesn't show.
        const edge = Math.min(1, Math.max(0, (LAT1 + 1 - lat) / 9)) * Math.min(1, Math.max(0, (LON1 + 1 - lon) / 9));
        dots.push({ lon, lat, kind, edge, phase: Math.random() * 6.28 });
      }
    }
    const routes = ROUTES.map((r) => ({ ...r, geo: smooth(r.path) }));
    const dust = Array.from({ length: 60 }, () => ({ x: Math.random(), y: Math.random(), v: 0.004 + Math.random() * 0.01, p: Math.random() * 6.28, s: Math.random() < 0.2 ? 1.6 : 1 }));

    // Soft glow sprite for ships and ports.
    const sprite = document.createElement("canvas");
    sprite.width = sprite.height = 32;
    const sg = sprite.getContext("2d");
    const grad = sg.createRadialGradient(16, 16, 0, 16, 16, 16);
    grad.addColorStop(0, "rgba(220,245,255,1)");
    grad.addColorStop(0.25, "rgba(76,201,255,0.85)");
    grad.addColorStop(1, "rgba(76,201,255,0)");
    sg.fillStyle = grad;
    sg.fillRect(0, 0, 32, 32);

    let w = 0, h = 0, s = 1, x0 = 0, y0 = 0, fade = 1, labels = true;
    let mx = 0, my = 0, tx = 0, ty = 0;
    const P = (lon, lat) => [x0 + (lon - LON0) * s, y0 + (LAT1 - lat) * s];

    function resize() {
      const rect = header.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width; h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const textRight = text ? text.getBoundingClientRect().right - rect.left : w * 0.6;
      const contentRight = (w + Math.min(w, 1120)) / 2;
      s = (h - 20) / (LAT1 - LAT0);
      const mapW = (LON1 - LON0) * s;
      if (w - textRight > mapW * 0.8) {
        // Room beside the text: the map sits to its right.
        x0 = Math.max(textRight + 10, Math.min(w - mapW - 6, contentRight - mapW + 90));
        y0 = 10;
        fade = 1; labels = true;
      } else {
        // Narrow screens: a faint map behind the text, towards the right.
        s = Math.min((h * 0.9) / (LAT1 - LAT0), (w * 1.05) / (LON1 - LON0));
        x0 = w - (LON1 - LON0) * s * 0.85;
        y0 = h * 0.05;
        fade = 0.55; labels = false;
      }
      for (const d of dots) [d.x, d.y] = P(d.lon, d.lat);
      for (const r of routes) {
        r.px = r.geo.map(([lon, lat]) => P(lon, lat));
        r.cum = [0];
        for (let i = 1; i < r.px.length; i++) r.cum.push(r.cum[i - 1] + Math.hypot(r.px[i][0] - r.px[i - 1][0], r.px[i][1] - r.px[i - 1][1]));
        r.len = r.cum[r.cum.length - 1];
        r.labelPx = P(...r.at);
      }
      for (const p of PORTS) [p.x, p.y] = P(p.lon, p.lat);
    }

    // Point at distance d along a route.
    function along(r, d) {
      d = Math.max(0, Math.min(d, r.len));
      let lo = 0, hi = r.cum.length - 1;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (r.cum[m] < d) lo = m; else hi = m; }
      const seg = r.cum[hi] - r.cum[lo] || 1, f = (d - r.cum[lo]) / seg;
      return [r.px[lo][0] + (r.px[hi][0] - r.px[lo][0]) * f, r.px[lo][1] + (r.px[hi][1] - r.px[lo][1]) * f];
    }

    function frame(t) {
      const time = t / 1000;
      ctx.clearRect(0, 0, w, h);

      // Dust, over the whole header.
      ctx.fillStyle = "rgb(150,210,255)";
      for (const d of dust) {
        const y = ((d.y - time * d.v) % 1 + 1) % 1;
        ctx.globalAlpha = Math.max(0, (0.25 + 0.35 * Math.sin(time * 1.5 + d.p)) * Math.max(fade, 0.6));
        ctx.fillRect(d.x * w, y * h, d.s, d.s);
      }

      // Gentle parallax with the pointer.
      tx += (mx - tx) * 0.05; ty += (my - ty) * 0.05;
      ctx.save();
      ctx.translate(tx * 10, ty * 6);
      ctx.globalCompositeOperation = "lighter";

      // Light pooled over southern Africa.
      const [hx, hy] = P(24, -18);
      const halo = ctx.createRadialGradient(hx, hy, 0, hx, hy, s * 40);
      halo.addColorStop(0, `rgba(47,107,255,${0.2 * fade})`);
      halo.addColorStop(1, "rgba(47,107,255,0)");
      ctx.globalAlpha = 1;
      ctx.fillStyle = halo;
      ctx.fillRect(hx - s * 40, hy - s * 40, s * 80, s * 80);

      // Land dots, brightened as the scan line passes.
      const scanY = y0 + ((time / 7) % 1) * (LAT1 - LAT0 + 16) * s - 8 * s;
      const size = Math.max(1.2, s * 0.32);
      const colours = ["rgb(125,150,255)", "rgb(90,185,255)", "rgb(190,240,255)"];
      for (let k = 0; k <= 2; k++) {
        ctx.fillStyle = colours[k];
        const base = k === 2 ? 0.85 : k === 1 ? 0.42 : 0.3;
        for (const d of dots) {
          if (d.kind !== k) continue;
          const dy = (d.y - scanY) / (s * 3);
          const scan = Math.exp(-dy * dy) * 0.6;
          ctx.globalAlpha = Math.min(1, (base + scan + 0.08 * Math.sin(time * 1.3 + d.phase)) * d.edge * fade);
          ctx.fillRect(d.x - size / 2, d.y - size / 2, size, size);
        }
      }

      // The lanes: a faint dashed line each.
      ctx.globalAlpha = 0.35 * fade;
      ctx.strokeStyle = "rgb(76,201,255)";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 5]);
      ctx.lineDashOffset = -time * 8;
      for (const r of routes) {
        ctx.beginPath();
        r.px.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // Tankers: a bright head with a fading wake, spaced evenly along each lane.
      const trail = s * 9;
      for (const r of routes) {
        for (let n = 0; n < r.ships; n++) {
          const u = ((time / r.secs + n / r.ships) % 1 + 1) % 1;
          const d = u * r.len;
          const arrive = u > 0.94 ? (1 - u) / 0.06 : 1, depart = u < 0.04 ? u / 0.04 : 1;
          const a = Math.min(arrive, depart) * fade;
          for (let k = 12; k >= 1; k--) {
            const [x, y] = along(r, d - (trail * k) / 12);
            ctx.globalAlpha = a * 0.55 * (1 - k / 13);
            ctx.fillStyle = "rgb(120,220,255)";
            ctx.fillRect(x - 0.9, y - 0.9, 1.8, 1.8);
          }
          const [x, y] = along(r, d);
          const g = s * 3.4;
          ctx.globalAlpha = a;
          ctx.drawImage(sprite, x - g / 2, y - g / 2, g, g);
        }
      }

      // Ports: a beacon with a ring pulsing out.
      for (const p of PORTS) {
        const g = s * 3;
        ctx.globalAlpha = fade;
        ctx.drawImage(sprite, p.x - g / 2, p.y - g / 2, g, g);
        const ph = (time / 2.4 + (p.lon > 25 ? 0 : 0.5)) % 1;
        ctx.globalAlpha = (1 - ph) * 0.8 * fade;
        ctx.strokeStyle = "rgb(120,220,255)";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2 + ph * s * 3.2, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.globalCompositeOperation = "source-over";

      // Labels.
      if (labels) {
        ctx.font = `600 ${Math.round(Math.max(9, s * 2.1))}px Inter, system-ui, sans-serif`;
        if ("letterSpacing" in ctx) ctx.letterSpacing = "2px";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "rgb(150,190,235)";
        ctx.globalAlpha = 0.75;
        ctx.textAlign = "center";
        for (const r of routes) ctx.fillText(r.label.toUpperCase(), r.labelPx[0], r.labelPx[1]);
        ctx.fillStyle = "rgb(210,240,255)";
        ctx.globalAlpha = 0.95;
        for (const p of PORTS) {
          ctx.textAlign = p.align;
          ctx.fillText(p.name.toUpperCase(), p.x + p.dx, p.y + p.dy);
        }
      }
      ctx.restore();
      ctx.globalAlpha = 1;
    }

    let running = false, visible = true, raf = 0;
    const loop = (t) => { frame(t); raf = requestAnimationFrame(loop); };
    const update = () => {
      const should = !reduceMotion && visible && !document.hidden;
      if (should && !running) { running = true; raf = requestAnimationFrame(loop); }
      if (!should && running) { running = false; cancelAnimationFrame(raf); }
    };
    const still = () => { if (!running) frame(5000); };

    resize();
    still();
    if ("ResizeObserver" in window) new ResizeObserver(() => { resize(); still(); }).observe(header);
    else window.addEventListener("resize", () => { resize(); still(); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { resize(); still(); });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(([e]) => { visible = e.isIntersecting; update(); }).observe(header);
    }
    document.addEventListener("visibilitychange", update);
    header.addEventListener("pointermove", (e) => {
      const rect = header.getBoundingClientRect();
      mx = (e.clientX - rect.left) / rect.width - 0.5;
      my = (e.clientY - rect.top) / rect.height - 0.5;
    });
    update();
  }

  // ------------------------------------------------------ the circuit board
  // Traces routed on a grid the way a PCB is: straight runs with 45-degree bends,
  // single lines and buses of parallel lines, never crossing, with pads at the
  // ends. They're drawn once onto a still canvas; a second canvas carries light
  // pulses running along them (pads flash as one arrives) and a glow that lights
  // the traces up around the mouse pointer.
  function setUpCircuit() {
    const base = document.createElement("canvas");
    const live = document.createElement("canvas");
    base.className = live.className = "circuit-fx";
    base.setAttribute("aria-hidden", "true");
    live.setAttribute("aria-hidden", "true");
    document.body.prepend(base, live);
    document.documentElement.classList.add("fx-circuit");
    const bctx = base.getContext("2d"), lctx = live.getContext("2d");
    const bright = document.createElement("canvas"), brctx = bright.getContext("2d");
    const lens = document.createElement("canvas"), lnctx = lens.getContext("2d");
    const G = 22, LENS = 150;
    const DIRS = [[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1],[0,-1],[1,-1]];

    let W = 0, H = 0, dpr = 1, traces = [], pads = [];

    function route() {
      const cols = Math.ceil(W / G) + 1, rows = Math.ceil(H / G) + 1;
      const occ = new Uint8Array(cols * rows);
      const free = (c, r) => c >= 0 && r >= 0 && c < cols && r < rows && !occ[r * cols + c];
      traces = []; pads = [];
      const attempts = Math.round((cols * rows) / 5);
      for (let a = 0; a < attempts; a++) {
        const c0 = Math.floor(Math.random() * cols), r0 = Math.floor(Math.random() * rows);
        const d0 = Math.floor(Math.random() * 4) * 2;                 // start orthogonal
        const k = [1, 1, 1, 1, 2, 3, 4, 5][Math.floor(Math.random() * 8)];
        const [px, py] = DIRS[(d0 + 2) % 8];                          // bus spacing
        const lines = Array.from({ length: k }, (_, i) => [[c0 + px * i, r0 + py * i]]);
        if (!lines.every(([[c, r]]) => free(c, r))) continue;
        const steps = 3 + Math.floor(Math.random() * 16);
        let d = d0;
        for (let s = 0; s < steps; s++) {
          // Bend 45 degrees now and then, staying within 45 degrees of the start
          // so the run keeps heading one way (bus lines then can't cross).
          if (Math.random() < 0.16) {
            const nd = (d + (Math.random() < 0.5 ? 1 : 7)) % 8;
            if (Math.min((nd - d0 + 8) % 8, (d0 - nd + 8) % 8) <= 1) d = nd;
          }
          const [dx, dy] = DIRS[d];
          const next = lines.map((l) => { const [c, r] = l[l.length - 1]; return [c + dx, r + dy]; });
          if (!next.every(([c, r]) => free(c, r))) break;
          // A diagonal step mustn't cut through a diagonal already laid across it.
          if (dx && dy && !lines.every((l) => { const [c, r] = l[l.length - 1]; return free(c + dx, r) || free(c, r + dy); })) break;
          next.forEach((p, i) => lines[i].push(p));
        }
        if (lines[0].length < 4) continue;
        for (const l of lines) {
          for (const [c, r] of l) occ[r * cols + c] = 1;
          // Merge straight runs into single segments.
          const pts = [l[0]];
          for (let i = 1; i < l.length; i++) {
            const prev = pts[pts.length - 1], cur = l[i], nxt = l[i + 1];
            if (nxt && cur[0] - prev[0] === nxt[0] - cur[0] && cur[1] - prev[1] === nxt[1] - cur[1]) continue;
            pts.push(cur);
          }
          const xy = pts.map(([c, r]) => [c * G + 0.5, r * G + 0.5]);
          const cum = [0];
          for (let i = 1; i < xy.length; i++) cum.push(cum[i - 1] + Math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]));
          traces.push({ xy, cum, len: cum[cum.length - 1] });
          pads.push({ x: xy[0][0], y: xy[0][1], ring: Math.random() < 0.6 });
          pads.push({ x: xy[xy.length - 1][0], y: xy[xy.length - 1][1], ring: Math.random() < 0.6 });
        }
      }
    }

    function paint(ctx, line, pad, blur) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.shadowColor = "rgba(63,182,255,0.9)";
      ctx.shadowBlur = blur;
      ctx.strokeStyle = line;
      ctx.lineWidth = 1.1;
      ctx.beginPath();
      for (const t of traces) t.xy.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
      ctx.strokeStyle = pad;
      ctx.fillStyle = pad;
      ctx.lineWidth = 1.2;
      const rings = new Path2D(), dots = new Path2D();
      for (const p of pads) {
        if (p.ring) { rings.moveTo(p.x + 3, p.y); rings.arc(p.x, p.y, 3, 0, Math.PI * 2); }
        else { dots.moveTo(p.x + 2, p.y); dots.arc(p.x, p.y, 2, 0, Math.PI * 2); }
      }
      ctx.stroke(rings);
      ctx.fill(dots);
      ctx.shadowBlur = 0;
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth;
      // Taller than the window, so a phone's toolbar sliding away doesn't re-route.
      H = Math.max(window.innerHeight, (window.screen && window.screen.height) || 0);
      for (const c of [base, live, bright]) {
        c.width = Math.round(W * dpr);
        c.height = Math.round(H * dpr);
        c.style.width = W + "px";
        c.style.height = H + "px";
      }
      lens.width = lens.height = Math.round(LENS * 2 * dpr);
      route();
      paint(bctx, "rgba(63,182,255,0.16)", "rgba(92,200,255,0.32)", 5);
      paint(brctx, "rgba(150,228,255,0.9)", "rgba(190,240,255,1)", 9);
      pulses.forEach(spawn);
    }

    // Pulses: a bright head with a fading tail, running end to end along a trace.
    const sprite = document.createElement("canvas");
    sprite.width = sprite.height = 32;
    const sg = sprite.getContext("2d");
    const grad = sg.createRadialGradient(16, 16, 0, 16, 16, 16);
    grad.addColorStop(0, "rgba(230,248,255,1)");
    grad.addColorStop(0.3, "rgba(76,201,255,0.8)");
    grad.addColorStop(1, "rgba(76,201,255,0)");
    sg.fillStyle = grad;
    sg.fillRect(0, 0, 32, 32);

    const pulses = [], flashes = [];
    function spawn(p) {
      const long = traces.filter((t) => t.len > G * 5);
      p.t = long.length ? long[Math.floor(Math.random() * long.length)] : null;
      p.d = -Math.random() * 400;                      // a staggered start
      p.v = 70 + Math.random() * 110;
      p.rev = Math.random() < 0.5;
      p.violet = Math.random() < 0.2;
    }
    function at(t, d) {
      d = Math.max(0, Math.min(d, t.len));
      let i = 1;
      while (i < t.cum.length - 1 && t.cum[i] < d) i++;
      const a = t.xy[i - 1], b = t.xy[i], f = (d - t.cum[i - 1]) / ((t.cum[i] - t.cum[i - 1]) || 1);
      return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
    }

    let pointer = null, lensAlpha = 0, last = 0;
    function frame(now) {
      const dt = last ? Math.min((now - last) / 1000, 0.1) : 0;
      last = now;
      lctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      lctx.clearRect(0, 0, W, H);

      // Traces light up around the pointer.
      lensAlpha += ((pointer ? 1 : 0) - lensAlpha) * 0.08;
      if (pointer && lensAlpha > 0.01) {
        const sx = (pointer[0] - LENS) * dpr, sy = (pointer[1] - LENS) * dpr, size = LENS * 2 * dpr;
        lnctx.globalCompositeOperation = "source-over";
        lnctx.clearRect(0, 0, size, size);
        lnctx.drawImage(bright, sx, sy, size, size, 0, 0, size, size);
        lnctx.globalCompositeOperation = "destination-in";
        const m = lnctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        m.addColorStop(0, "rgba(0,0,0,0.9)");
        m.addColorStop(1, "rgba(0,0,0,0)");
        lnctx.fillStyle = m;
        lnctx.fillRect(0, 0, size, size);
        lctx.globalAlpha = lensAlpha;
        lctx.drawImage(lens, pointer[0] - LENS, pointer[1] - LENS, LENS * 2, LENS * 2);
        lctx.globalAlpha = 1;
      }

      lctx.globalCompositeOperation = "lighter";
      for (const p of pulses) {
        if (!p.t) continue;
        p.d += p.v * dt;
        if (p.d > p.t.len) {
          const end = p.rev ? p.t.xy[0] : p.t.xy[p.t.xy.length - 1];
          flashes.push({ x: end[0], y: end[1], age: 0, violet: p.violet });
          spawn(p);
          continue;
        }
        if (p.d < 0) continue;
        const pos = (d) => at(p.t, p.rev ? p.t.len - d : d);
        lctx.lineWidth = 1.6;
        lctx.lineCap = "round";
        const tail = 70, n = 10;
        let prev = pos(Math.max(p.d - tail, 0));
        for (let i = 1; i <= n; i++) {
          const cur = pos(Math.max(p.d - tail + (tail * i) / n, 0));
          lctx.strokeStyle = p.violet ? `rgba(160,130,255,${(i / n) * 0.65})` : `rgba(110,215,255,${(i / n) * 0.7})`;
          lctx.beginPath();
          lctx.moveTo(prev[0], prev[1]);
          lctx.lineTo(cur[0], cur[1]);
          lctx.stroke();
          prev = cur;
        }
        lctx.globalAlpha = 0.85;
        lctx.drawImage(sprite, prev[0] - 7, prev[1] - 7, 14, 14);
        lctx.globalAlpha = 1;
      }
      for (let i = flashes.length - 1; i >= 0; i--) {
        const f = flashes[i];
        f.age += dt;
        if (f.age > 0.7) { flashes.splice(i, 1); continue; }
        const k = (1 - f.age / 0.7) * 0.8, s = 10 + f.age * 30;
        lctx.globalAlpha = k;
        lctx.drawImage(sprite, f.x - s / 2, f.y - s / 2, s, s);
      }
      lctx.globalAlpha = 1;
      lctx.globalCompositeOperation = "source-over";
    }

    const count = () => Math.max(8, Math.min(30, Math.round((window.innerWidth * window.innerHeight) / 50000)));
    for (let i = 0; i < count(); i++) pulses.push({});
    resize();
    let lastW = W, lastH = H, timer = 0;
    window.addEventListener("resize", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const h = Math.max(window.innerHeight, (window.screen && window.screen.height) || 0);
        if (window.innerWidth === lastW && h <= lastH) return;
        resize();
        lastW = W; lastH = H;
      }, 200);
    });
    if (reduceMotion) return;

    window.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse") pointer = [e.clientX, e.clientY]; }, { passive: true });
    document.documentElement.addEventListener("pointerleave", () => { pointer = null; });

    // About 30 frames a second is plenty for this, and halves the work of the
    // glass panels re-blurring what moves behind them.
    let running = false, raf = 0, tick = 0;
    const loop = (t) => {
      raf = requestAnimationFrame(loop);
      if (t - tick < 32) return;
      tick = t;
      frame(t);
    };
    const update = () => {
      const should = !document.hidden;
      if (should && !running) { running = true; last = 0; raf = requestAnimationFrame(loop); }
      if (!should && running) { running = false; cancelAnimationFrame(raf); }
    };
    document.addEventListener("visibilitychange", update);
    update();
  }

  const start = () => { setUpCircuit(); setUpReveal(); setUpRouteMap(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
