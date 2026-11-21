"""Produce the data files the web app reads:
  app/climatology.json  model snowfall at each resort for every past season (Oct 1 - May 31)
  app/meta.json         accuracy scores + storm ranges for the "How good is this" panel
  app/snapshot.json     raw Open-Meteo responses, used when the page can't reach the API (e.g. a sandboxed preview)
"""
import json, pathlib, datetime as dt, urllib.request, urllib.parse
import numpy as np, pandas as pd
import prepare
from sites import RESORTS, DAILY

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
model = json.loads((APP / "model.json").read_text())

def js_like_predict(df):
    raw = np.full(len(df), model["baseline"])
    X = df[model["features"]].values
    for t in model["trees"]:
        for i, x in enumerate(X):
            n = 0
            while not t[n][5]:
                f, thr, l, r, _, _, ml = t[n]
                v = x[f]
                n = (l if ml else r) if np.isnan(v) else (l if v <= thr else r)
            raw[i] += t[n][4]
    return np.exp(raw)

clim = {}
for key, site in RESORTS.items():
    m = prepare.meteo(key)
    f = prepare.features(m, dict(site, region=site["region"]))
    f["pred"] = js_like_predict(f)
    seasons = {}
    for y in range(2005, 2026):
        s = f.loc[f"{y}-10-01":f"{y+1}-05-31", "pred"]
        if len(s) >= 240 and s.notna().all():
            seasons[str(y)] = [round(v, 2) for v in s.values]
    tot = {k: sum(v) for k, v in seasons.items()}
    clim[key] = dict(seasons=seasons)
    print(key, "seasons", len(seasons), "median season in:", round(np.median(list(tot.values())) / 2.54))
# ENSO phase by season (Dec-Feb Oceanic Nino Index from NOAA CPC; weak events included)
ENSO = {2005: "nina", 2006: "nino", 2007: "nina", 2008: "nina", 2009: "nino", 2010: "nina", 2011: "nina",
        2012: "neutral", 2013: "neutral", 2014: "nino", 2015: "nino", 2016: "nina", 2017: "nina", 2018: "nino",
        2019: "neutral", 2020: "nina", 2021: "nina", 2022: "nina", 2023: "nino", 2024: "nina", 2025: "nina"}
clim["enso"] = {str(k): v for k, v in ENSO.items()}
(APP / "climatology.json").write_text(json.dumps(clim, separators=(",", ":")))

# accuracy + storm ranges from out-of-fold predictions
oof = pd.read_csv(ROOT / "data" / "oof.csv", index_col=0, parse_dates=True)
scores = pd.read_csv(ROOT / "data" / "scores.csv", index_col=0)
ratios = []
for site, g in oof.groupby("site"):
    g = g.sort_index()
    on = g.pred >= 1.0
    grp = (on != on.shift()).cumsum()
    for _, s in g[on].groupby(grp[on]):
        if s.pred.sum() >= 5:  # storms of at least ~2 inches predicted
            ratios.append(s.obs_snow_cm.sum() / s.pred.sum())
ratios = np.array(ratios)
meta = dict(
    generated=dt.date.today().isoformat(),
    storm_range=dict(low=float(np.quantile(ratios, 0.25)), high=float(np.quantile(ratios, 0.75)), n=int(len(ratios))),
    scores=json.loads(scores.reset_index().to_json(orient="records")),
)
(APP / "meta.json").write_text(json.dumps(meta, indent=1))
print("storm range x", meta["storm_range"])

def fetch(url):
    import time
    for i in range(5):
        try:
            return json.load(urllib.request.urlopen(url, timeout=60))
        except Exception as e:
            print("retry", e); time.sleep(15 * (i + 1))
    raise SystemExit("fetch failed: " + url)

snap = {"fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "resorts": {}}
today = dt.date.today()
y = today.year if today.month >= 7 else today.year - 1
for key, s in RESORTS.items():
    common = dict(latitude=s["lat"], longitude=s["lon"], elevation=s["elev"], daily=",".join(DAILY), timezone=s["tz"])
    arch = fetch("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(
        dict(common, start_date=f"{y}-10-01", end_date=(today - dt.timedelta(days=5)).isoformat())))
    fc = fetch("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(dict(common, past_days=7, forecast_days=16)))
    snap["resorts"][key] = dict(archive=arch["daily"], forecast=fc["daily"])
(APP / "snapshot.json").write_text(json.dumps(snap, separators=(",", ":")))
print("snapshot ok")
