"""Daily forecast-vs-actual loop. Run once a day (GitHub Actions does this).

1. Log today's 16-day model forecast for the two resorts and for the stations where snow is measured.
2. Pull recent measured snow at those stations.
3. Score every logged forecast that now has a measurement, grouped by region and lead time.
4. Write app/calibration.json: a correction factor per region and lead-time bucket, shrunk toward 1.0
   until enough snow has been verified, so one odd storm can't swing the forecast.

The resorts themselves have no free daily snow measurement, so the model is checked at the nearest
measuring stations (same model, their location and elevation) and that region's correction is applied
to the resort.
"""
import datetime as dt, json, pathlib, time, urllib.parse, urllib.request
import numpy as np, pandas as pd
import prepare, model_io
from sites import SITES, RESORTS, DAILY, VERIFY_SITES

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "forecast_log.csv"
RECENT = ROOT / "data" / "obs_recent"
APP = ROOT / "app"

# Where we can check the model, and which region's correction each station feeds.
VERIFY = {
    "chittenden": dict(region="VT", kind="ghcn", id="USC00431433"),
    "shrewsbury": dict(region="VT", kind="ghcn", id="US1VTRT0028"),
    "pittsfield": dict(region="VT", kind="ghcn", id="US1VTRT0034"),
    "barnard": dict(region="VT", kind="ghcn", id="US1VTWR0036"),
    "taos_powderhorn": dict(region="NM", kind="snotel", id="1168"),
    "red_river_pass": dict(region="NM", kind="snotel", id="715"),
}
BUCKETS = [(0, 2, "Days 1–3"), (3, 6, "Days 4–7"), (7, 15, "Days 8–16")]
PRIOR_CM = 60.0          # shrinkage: act as if 60 cm had already verified perfectly
WINDOW_DAYS = 120        # only recent verification counts (this season, roughly)
CLAMP = (0.5, 2.0)


def get(url, as_json=True, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                body = r.read()
            return json.loads(body) if as_json else body
        except Exception as e:  # network blips and rate limits
            print("retry", url.split("?")[0], e)
            time.sleep(15 * (i + 1))
    raise RuntimeError("failed: " + url)


def log_forecasts(issued):
    model = model_io.load()
    rows = []
    ALL = {**SITES, **VERIFY_SITES}
    for name, s in {**RESORTS, **{k: ALL[k] for k in VERIFY}}.items():
        q = dict(latitude=s["lat"], longitude=s["lon"], elevation=s["elev"], daily=",".join(DAILY),
                 timezone=s["tz"], past_days=1, forecast_days=16)
        d = get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))["daily"]
        m = pd.DataFrame(d)[["time"] + DAILY]
        m["date"] = pd.to_datetime(m.pop("time"))
        m = m.set_index("date").astype(float)
        f = prepare.features(m, s)
        pred = model_io.predict(model, f)
        today = m.index[1]  # index 0 is yesterday (past_days=1), kept only for the "previous day" features
        for date, p, raw in zip(m.index[1:], pred[1:], m["snowfall_sum"].values[1:]):
            rows.append(dict(issued=issued, site=name, target=date.date().isoformat(),
                             lead=(date - today).days, pred_cm=round(float(p), 2), raw_cm=float(raw)))
    new = pd.DataFrame(rows)
    old = pd.read_csv(LOG) if LOG.exists() else pd.DataFrame(columns=new.columns)
    out = pd.concat([old[old.issued != issued], new]).sort_values(["issued", "site", "lead"])
    out.to_csv(LOG, index=False)
    print("logged", len(new), "forecast days; log has", len(out))


def fetch_obs(today):
    RECENT.mkdir(parents=True, exist_ok=True)
    start = (today - dt.timedelta(days=WINDOW_DAYS + 20)).isoformat()
    obs = {}
    for name, v in VERIFY.items():
        if v["kind"] == "snotel":
            body = get("https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?" + urllib.parse.urlencode(dict(
                stationTriplets=f"{v['id']}:NM:SNTL", elements="SNWD,WTEQ", duration="DAILY",
                beginDate=start, endDate=today.isoformat())), as_json=False)
            p = RECENT / f"sntl_{v['id']}.json"
            p.write_bytes(body)
            obs[name] = prepare.obs_snotel(v["id"], path=p)
        else:
            body = get("https://www.ncei.noaa.gov/access/services/data/v1?" + urllib.parse.urlencode(dict(
                dataset="daily-summaries", stations=v["id"], startDate=start, endDate=today.isoformat(),
                dataTypes="SNOW,SNWD,PRCP", units="metric", format="csv")), as_json=False)
            p = RECENT / f"ghcn_{v['id']}.csv"
            p.write_bytes(body)
            obs[name] = prepare.obs_ghcn(v["id"], path=p) if len(body) > 60 else pd.Series(dtype=float)
        print(name, "measured days:", int(obs[name].notna().sum()))
    return obs


def calibrate(obs, today):
    log = pd.read_csv(LOG)
    log = log[log.site.isin(VERIFY)]
    pairs = []
    for name, s in obs.items():
        s = s.dropna()
        s.index = s.index.strftime("%Y-%m-%d")
        g = log[log.site == name].copy()
        g["obs_cm"] = g.target.map(s)
        pairs.append(g.dropna(subset=["obs_cm"]))
    pairs = pd.concat(pairs) if pairs else pd.DataFrame()
    cutoff = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    if len(pairs):
        pairs = pairs[(pairs.target >= cutoff) & (pairs.target < today.isoformat())]
        pairs["region"] = pairs.site.map({k: v["region"] for k, v in VERIFY.items()})

    out = {"updated": today.isoformat(), "window_days": WINDOW_DAYS, "prior_cm": PRIOR_CM, "regions": {}}
    for region in ["VT", "NM"]:
        rows = []
        for lo, hi, label in BUCKETS:
            g = pairs[(pairs.region == region) & pairs.lead.between(lo, hi)] if len(pairs) else pairs
            o, p = (float(g.obs_cm.sum()), float(g.pred_cm.sum())) if len(g) else (0.0, 0.0)
            factor = float(np.clip((o + PRIOR_CM) / (p + PRIOR_CM), *CLAMP))
            rows.append(dict(min_lead=lo, max_lead=hi, label=label, factor=round(factor, 3),
                             days=int(len(g)), obs_cm=round(o, 1), pred_cm=round(p, 1),
                             snow_days=int((g.obs_cm >= 2.5).sum()) if len(g) else 0))
        out["regions"][region] = rows
    (APP / "calibration.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["regions"], indent=1))


if __name__ == "__main__":
    today = dt.datetime.now(dt.timezone.utc).date()
    log_forecasts(today.isoformat())
    calibrate(fetch_obs(today), today)
