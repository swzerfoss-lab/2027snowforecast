// Snowcast core: turns Open-Meteo daily weather into model snowfall, storms and season numbers.
// Runs in the browser (window.Snow) and in Node (module.exports) so the Python pipeline can be cross-checked.
(function (root) {
  const DAILY = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum",
    "snowfall_sum", "precipitation_hours", "wind_speed_10m_max", "wind_direction_10m_dominant",
    "relative_humidity_2m_mean", "pressure_msl_mean"];
  const SHIFTED = ["precipitation_sum", "snowfall_sum", "temperature_2m_mean", "temperature_2m_max", "precipitation_hours"];

  const RESORTS = {
    killington: { name: "Killington", state: "Vermont", lat: 43.6045, lon: -72.8201, elev: 1100, tz: "America/New_York", isNM: 0 },
    taos: { name: "Taos Ski Valley", state: "New Mexico", lat: 36.5960, lon: -105.4545, elev: 3200, tz: "America/Denver", isNM: 1 },
  };

  const num = (v) => (v === null || v === undefined ? NaN : v);

  function dayOfYear(iso) {
    const d = new Date(iso + "T00:00:00Z");
    return Math.floor((d - Date.UTC(d.getUTCFullYear(), 0, 1)) / 864e5) + 1;
  }

  // Same feature recipe as pipeline/prepare.py:features()
  function featureRows(daily, resort) {
    const n = daily.time.length;
    const col = (c) => daily[c].map(num);
    const cols = Object.fromEntries(DAILY.map((c) => [c, col(c)]));
    const rows = [];
    for (let i = 0; i < n; i++) {
      const f = {};
      for (const c of DAILY) {
        if (c === "wind_direction_10m_dominant") {
          const r = (cols[c][i] * Math.PI) / 180;
          f.wdir_sin = Math.sin(r); f.wdir_cos = Math.cos(r);
        } else f[c] = cols[c][i];
      }
      for (const c of SHIFTED) {
        f[c + "_prev"] = i > 0 ? cols[c][i - 1] : NaN;
        f[c + "_next"] = i < n - 1 ? cols[c][i + 1] : NaN;
      }
      const p = cols.precipitation_sum;
      f.precip_3d = i > 0 && i < n - 1 ? p[i - 1] + p[i] + p[i + 1] : NaN;
      const doy = dayOfYear(daily.time[i]);
      f.doy_sin = Math.sin((2 * Math.PI * doy) / 365.25);
      f.doy_cos = Math.cos((2 * Math.PI * doy) / 365.25);
      f.elev = resort.elev;
      f.is_nm = resort.isNM;
      rows.push(f);
    }
    return rows;
  }

  function predictOne(model, f) {
    const x = model.features.map((k) => f[k]);
    let raw = model.baseline;
    for (const t of model.trees) {
      let n = 0;
      while (!t[n][5]) {
        const [fi, thr, l, r, , , ml] = t[n];
        const v = x[fi];
        n = Number.isNaN(v) ? (ml ? l : r) : v <= thr ? l : r;
      }
      raw += t[n][4];
    }
    return Math.exp(raw);
  }

  // Returns [{date, cm, rawCm, tmax, tmin, precipMm}]
  function predictDaily(model, daily, resort) {
    const rows = featureRows(daily, resort);
    return rows.map((f, i) => ({
      date: daily.time[i],
      cm: predictOne(model, f),
      rawCm: num(daily.snowfall_sum[i]),
      tmax: num(daily.temperature_2m_max[i]),
      tmin: num(daily.temperature_2m_min[i]),
      precipMm: num(daily.precipitation_sum[i]),
    }));
  }

  // Storm = run of days with >= threshold cm, bridging up to `gap` lighter days.
  function storms(days, threshold = 1.0, gap = 1) {
    const out = [];
    let cur = null, dry = 0;
    for (const d of days) {
      if (d.cm >= threshold) {
        if (!cur) cur = { start: d.date, end: d.date, cm: 0, days: [] };
        cur.cm += d.cm; cur.end = d.date; cur.days.push(d); dry = 0;
      } else if (cur) {
        dry++;
        if (dry > gap) { out.push(cur); cur = null; dry = 0; }
      }
    }
    if (cur) out.push(cur);
    return out;
  }

  // Merge archive (older) and forecast (newer) daily blocks, forecast wins on overlapping dates.
  function mergeDaily(older, newer) {
    const map = new Map();
    for (const blk of [older, newer]) {
      if (!blk) continue;
      blk.time.forEach((t, i) => {
        const row = {};
        for (const c of DAILY) row[c] = blk[c] ? blk[c][i] : null;
        if (row.precipitation_sum === null && map.has(t)) return; // don't overwrite with empty
        map.set(t, row);
      });
    }
    const time = [...map.keys()].sort();
    const out = { time };
    for (const c of DAILY) out[c] = time.map((t) => map.get(t)[c]);
    return out;
  }

  function seasonStartYear(iso) {
    const [y, m] = iso.split("-").map(Number);
    return m >= 7 ? y : y - 1;
  }

  const SEASON_START = (y) => `${y}-10-01`;
  const SEASON_END = (y) => `${y + 1}-05-31`;

  // Season outlook: to-date + forecast + historical remainder distribution.
  // clim.seasons: {"2010": [cm per day from Oct 1 ...], ...}
  function seasonOutlook(days, today, clim, enso, phase) {
    const y = seasonStartYear(today);
    const start = SEASON_START(y), end = SEASON_END(y);
    const inSeason = days.filter((d) => d.date >= start && d.date <= end);
    const toDate = inSeason.filter((d) => d.date < today).reduce((s, d) => s + d.cm, 0);
    const fc = inSeason.filter((d) => d.date >= today);
    const fcTotal = fc.reduce((s, d) => s + d.cm, 0);
    const lastFc = fc.length ? fc[fc.length - 1].date : today;
    const idxAfter = Math.max(0, Math.round((Date.parse(lastFc) - Date.parse(start)) / 864e5) + 1);
    const idxToday = Math.max(0, Math.round((Date.parse(today) - Date.parse(start)) / 864e5));
    const remain = [], totals = [], toDateHist = [];
    for (const [season, arr] of Object.entries(clim.seasons)) {
      if (Number(season) === y) continue;
      if (phase && phase !== "all" && enso && enso[season] !== phase) continue;
      remain.push(arr.slice(idxAfter).reduce((s, v) => s + v, 0));
      totals.push(arr.reduce((s, v) => s + v, 0));
      toDateHist.push(arr.slice(0, idxToday).reduce((s, v) => s + v, 0));
    }
    const q = (a, p) => { const s = [...a].sort((x, z) => x - z); const k = (s.length - 1) * p; const lo = Math.floor(k); return s[lo] + (s[Math.min(lo + 1, s.length - 1)] - s[lo]) * (k - lo); };
    const base = toDate + fcTotal;
    return {
      season: y, toDate, forecast: fcTotal,
      projected: { p10: base + q(remain, 0.1), p50: base + q(remain, 0.5), p90: base + q(remain, 0.9) },
      normalTotal: q(totals, 0.5), normalToDate: q(toDateHist, 0.5),
      dayIndex: idxToday, nSeasons: totals.length,
    };
  }

  const api = { DAILY, RESORTS, featureRows, predictOne, predictDaily, storms, mergeDaily, seasonOutlook, seasonStartYear, SEASON_START, SEASON_END };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Snow = api;
})(typeof window !== "undefined" ? window : globalThis);
