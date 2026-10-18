/* The glowing circuit board behind every PsyPhin page. IDENTICAL on psyphin.co.za
   (js/circuit.js), fuel.psyphin.co.za (docs/ and frontend/circuit.js) and the
   other tools: change one, copy it to all.
   Traces are routed on a grid the way a PCB is: straight runs with 45-degree
   bends, single lines and buses of parallel lines, never crossing, with pads at
   the ends. They're drawn once onto a still canvas; a second canvas carries light
   pulses running along them (pads flash as one arrives) and a glow that lights
   the traces up around the mouse pointer. Both canvases get class "circuit-fx"
   (fixed behind the page, styled in each site's CSS), and <html> gets
   "fx-circuit" so the CSS can hide its static fallback tile. Under
   prefers-reduced-motion the board is drawn once and stays still. */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setUpCircuit);
  else setUpCircuit();
})();
