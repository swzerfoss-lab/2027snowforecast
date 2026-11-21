/* Snowfall animation for the resort photo.
   One canvas, no libraries. The look scales with the current snowfall rate (inches per hour):
   Flurries < 0.1, Light 0.1-0.5, Moderate 0.5-1, Heavy 1-2, Blizzard > 2 with gusts over 35 mph.
   Between levels the parameters blend, so 0.9 in/hr looks a little heavier than 0.6. */
(function (root) {
  const LEVELS = [
    { n: 0, name: "Not snowing", min: 0 },
    { n: 1, name: "Flurries", min: 0.001 },
    { n: 2, name: "Light snow", min: 0.1 },
    { n: 3, name: "Moderate snow", min: 0.5 },
    { n: 4, name: "Heavy snow", min: 1 },
    { n: 5, name: "Blizzard", min: 2 },
  ];
  // Preset rates used by the ?snow=N preview switch.
  const PRESET_RATE = [0, 0.05, 0.3, 0.75, 1.5, 3];
  const BLIZZARD_GUST_MPH = 35;

  // dens = flakes per 10,000 css px²; vy = fall speed px/s; wind = drift px/s; wob = sway px; fog/streak 0..1; dim/sat = photo filter
  const P = [
    { r: 0,    dens: 0,   s0: 2.0, s1: 4.0, vy0: 20,  vy1: 36,  wind: 4,   wob: 14, fog: 0,    streak: 0,    gust: 0,    dim: 1,   sat: 1 },
    { r: 0.05, dens: 0.9, s0: 2.6, s1: 5.2, vy0: 18,  vy1: 34,  wind: 6,   wob: 16, fog: 0,    streak: 0,    gust: 0.1,  dim: 1,   sat: 1 },
    { r: 0.3,  dens: 5,   s0: 1.6, s1: 3.8, vy0: 32,  vy1: 62,  wind: 12,  wob: 10, fog: 0.02, streak: 0,    gust: 0.15, dim: .95, sat: .95 },
    { r: 0.75, dens: 13,  s0: 1.4, s1: 4.2, vy0: 50,  vy1: 105, wind: 26,  wob: 8,  fog: 0.07, streak: 0.05, gust: 0.25, dim: .88, sat: .85 },
    { r: 1.5,  dens: 26,  s0: 1.3, s1: 4.6, vy0: 85,  vy1: 170, wind: 90,  wob: 6,  fog: 0.16, streak: 0.35, gust: 0.5,  dim: .8,  sat: .7 },
    { r: 3,    dens: 42,  s0: 1.0, s1: 3.6, vy0: 150, vy1: 280, wind: 420, wob: 3,  fog: 0.38, streak: 1,    gust: 1,    dim: .72, sat: .55 },
  ];

  function paramsFor(rate, windy) {
    let a = P[P.length - 1], b = a, t = 0;
    for (let i = 0; i < P.length - 1; i++) {
      if (rate <= P[i + 1].r) { a = P[i]; b = P[i + 1]; t = Math.max(0, (rate - a.r) / (b.r - a.r)); break; }
    }
    const o = {};
    for (const k in a) o[k] = a[k] + (b[k] - a[k]) * t;
    if (!windy) { // heavy snow without strong wind: no blizzard streaks or whiteout
      const h = P[4];
      o.wind = Math.min(o.wind, h.wind); o.streak = Math.min(o.streak, h.streak);
      o.fog = Math.min(o.fog, h.fog + 0.04); o.gust = Math.min(o.gust, h.gust);
    }
    return o;
  }

  function levelFor(rateIn, gustMph) {
    if (!(rateIn > 0.001)) return LEVELS[0];
    if (rateIn < 0.1) return LEVELS[1];
    if (rateIn < 0.5) return LEVELS[2];
    if (rateIn < 1) return LEVELS[3];
    if (rateIn < 2 || !(gustMph >= BLIZZARD_GUST_MPH)) return LEVELS[4];
    return LEVELS[5];
  }

  const hasDOM = typeof document !== "undefined";
  const reduceMotion = hasDOM && root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DPR = hasDOM ? Math.min(root.devicePixelRatio || 1, 2) : 1;

  function makeSprite() { // soft flake with a faint dark rim so it reads against bright snow
    const c = document.createElement("canvas"); c.width = c.height = 32; const g = c.getContext("2d");
    const r = g.createRadialGradient(16, 16, 0, 16, 16, 16);
    r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.45, "rgba(255,255,255,.95)");
    r.addColorStop(0.62, "rgba(255,255,255,.5)"); r.addColorStop(0.78, "rgba(40,60,80,.18)"); r.addColorStop(1, "rgba(40,60,80,0)");
    g.fillStyle = r; g.fillRect(0, 0, 32, 32); return c;
  }

  const all = [];
  let sprite = null, running = false, last = 0;

  class Field {
    constructor(canvas) {
      sprite = sprite || makeSprite();
      this.c = canvas; this.g = canvas.getContext("2d"); this.flakes = [];
      this.p = paramsFor(0, false); this.target = this.p; this.t = Math.random() * 100; this.visible = true; this.windNow = 0;
      if (root.ResizeObserver) new ResizeObserver(() => this.resize()).observe(canvas);
      if (root.IntersectionObserver) new IntersectionObserver((es) => { this.visible = es[0].isIntersecting; }).observe(canvas);
      this.resize();
      all.push(this);
    }
    resize() {
      const r = this.c.getBoundingClientRect(); this.w = Math.max(1, r.width); this.h = Math.max(1, r.height);
      this.c.width = Math.round(this.w * DPR); this.c.height = Math.round(this.h * DPR);
      if (reduceMotion) this.still();
    }
    set(rateIn, gustMph) {
      const windy = gustMph >= BLIZZARD_GUST_MPH;
      this.target = paramsFor(rateIn, windy);
      if (!this.p.dens) this.p = { ...this.target };
      if (reduceMotion) this.still(); else start();
      return this.target;
    }
    spawn(top) {
      return { x: Math.random() * (this.w + 200) - 100, y: top ? -10 - Math.random() * 40 : Math.random() * this.h,
        z: Math.random(), ph: Math.random() * Math.PI * 2, fq: 0.6 + Math.random() * 1.2, vr: Math.random(), vx: 0, vy: 0 };
    }
    step(dt) {
      const p = this.p, T = this.target;
      for (const k in T) p[k] += (T[k] - p[k]) * Math.min(1, dt * 1.5);
      this.t += dt;
      const want = Math.min(1800, Math.round(p.dens * (this.w * this.h / 10000) * (this.w < 500 ? 0.7 : 1)));
      while (this.flakes.length < want) this.flakes.push(this.spawn(this.started && this.flakes.length > 0));
      if (this.flakes.length > want) this.flakes.length = Math.max(want, this.flakes.length - 6);
      this.started = true;
      const gustNow = 1 + p.gust * (0.55 * Math.sin(this.t * 0.9) + 0.35 * Math.sin(this.t * 2.3 + 1.7));
      this.windNow = p.wind * Math.max(0.2, gustNow);
      for (const f of this.flakes) {
        const depth = 0.35 + f.z * 0.65;
        f.vy = (p.vy0 + (p.vy1 - p.vy0) * f.vr) * depth;
        f.vx = this.windNow * depth + Math.cos(this.t * f.fq + f.ph) * p.wob * f.fq;
        f.x += f.vx * dt; f.y += f.vy * dt;
        if (f.y > this.h + 12) { Object.assign(f, this.spawn(true)); if (this.windNow > 60) f.x = Math.random() * this.w - this.windNow * 0.6; }
        if (f.x > this.w + 110) f.x -= this.w + 200; else if (f.x < -110) f.x += this.w + 200;
      }
    }
    draw() {
      const g = this.g, p = this.p;
      g.setTransform(DPR, 0, 0, DPR, 0, 0); g.clearRect(0, 0, this.w, this.h);
      if (p.fog > 0.005) {
        const a = p.fog * (0.85 + 0.15 * Math.sin(this.t * 1.3));
        const grd = g.createLinearGradient(0, 0, this.w, 0);
        grd.addColorStop(0, `rgba(232,238,244,${a * 1.1})`); grd.addColorStop(0.5, `rgba(232,238,244,${a * 0.75})`); grd.addColorStop(1, `rgba(232,238,244,${a})`);
        g.fillStyle = grd; g.fillRect(0, 0, this.w, this.h);
      }
      g.lineCap = "round";
      for (const f of this.flakes) {
        const size = p.s0 + (p.s1 - p.s0) * f.z, a = 0.45 + 0.55 * f.z;
        if (p.streak > 0.04 && f.z > 0.25) {
          const len = p.streak * 0.045;
          g.strokeStyle = `rgba(255,255,255,${a * (0.35 + 0.4 * p.streak)})`; g.lineWidth = Math.max(0.6, size * 0.55);
          g.beginPath(); g.moveTo(f.x, f.y); g.lineTo(f.x - f.vx * len, f.y - f.vy * len); g.stroke();
        }
        g.globalAlpha = a; const d = size * 2.4; g.drawImage(sprite, f.x - d / 2, f.y - d / 2, d, d);
      }
      g.globalAlpha = 1;
    }
    still() { this.p = { ...this.target }; this.flakes = []; this.started = false; this.step(0); this.draw(); }
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    let busy = false;
    if (!document.hidden) for (const f of all) {
      if (!f.visible) continue;
      if (f.target.dens > 0 || f.p.dens > 0.01 || f.flakes.length) { f.step(dt); f.draw(); busy = true; }
    }
    if (busy || document.hidden) requestAnimationFrame(frame); else running = false;
  }
  function start() { if (!running && !reduceMotion) { running = true; last = performance.now(); requestAnimationFrame(frame); } }

  const api = { LEVELS, PRESET_RATE, BLIZZARD_GUST_MPH, paramsFor, levelFor, Field, reduceMotion };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Snowfall = api;
})(typeof window !== "undefined" ? window : globalThis);
