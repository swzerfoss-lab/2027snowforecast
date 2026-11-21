"""Train the daily snowfall model and score it on held-out seasons.

Baseline A: Open-Meteo's own snowfall_sum, used as-is.
Baseline B: gradient-boosted trees on Open-Meteo features, pooled over all four observing sites,
            Poisson loss (lots of zero days, skewed amounts).
"""
import json, pathlib
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
import prepare

ROOT = pathlib.Path(__file__).resolve().parent.parent
df = prepare.build()
FEATS = prepare.FEATURES
df = df[df.index.month.isin([10, 11, 12, 1, 2, 3, 4, 5])]  # snow season only
lab = df.dropna(subset=["obs_snow_cm"])


def model():
    return HistGradientBoostingRegressor(loss="poisson", max_iter=400, learning_rate=0.05, max_leaf_nodes=24,
                                         min_samples_leaf=40, l2_regularization=1.0, random_state=0)

# Leave-seasons-out cross-validation: every season is predicted by a model that never saw it.
from sklearn.model_selection import GroupKFold
oof = pd.Series(np.nan, index=range(len(lab)))
for tri, tei in GroupKFold(n_splits=6).split(lab, groups=lab.season):
    mm = model().fit(lab.iloc[tri][FEATS], lab.iloc[tri].obs_snow_cm)
    oof.iloc[tei] = mm.predict(lab.iloc[tei][FEATS])
te = lab.assign(pred=oof.values, raw=lab.snowfall_sum)
te.to_csv(ROOT / "data" / "oof.csv")

def storms(s, thresh=1.0, gap=1):
    """Group consecutive snowy days (allowing `gap` dry days) into storms; return list of totals."""
    tot, cur, dry = [], 0.0, 0
    for v in s.fillna(0).values:
        if v >= thresh:
            cur += v; dry = 0
        elif cur > 0:
            dry += 1
            if dry > gap:
                tot.append(cur); cur, dry = 0.0, 0
    if cur > 0: tot.append(cur)
    return tot

rows = []
for site, g in te.groupby("site"):
    r = dict(site=site, days=len(g))
    for k in ["raw", "pred"]:
        r[f"{k}_mae"] = (g[k] - g.obs_snow_cm).abs().mean()
        r[f"{k}_corr"] = np.corrcoef(g[k], g.obs_snow_cm)[0, 1]
        snow = g.obs_snow_cm >= 2.5
        r[f"{k}_hit"] = ((g[k] >= 2.5) & snow).sum() / max(snow.sum(), 1)
    # season totals, only seasons with near-complete observations
    seas = g.groupby("season").agg(n=("obs_snow_cm", "size"), obs=("obs_snow_cm", "sum"), raw=("raw", "sum"), pred=("pred", "sum"))
    seas = seas[seas.n > 0.95 * 243]
    r["seasons"] = len(seas)
    r["season_obs_mean"] = seas.obs.mean()
    for k in ["raw", "pred"]:
        r[f"{k}_season_bias_pct"] = 100 * (seas[k].sum() / seas.obs.sum() - 1) if len(seas) else np.nan
        r[f"{k}_season_mape"] = 100 * ((seas[k] - seas.obs).abs() / seas.obs).mean() if len(seas) else np.nan
    # storm totals: compare per-storm totals on observed storm windows
    so, sp = storms(g.obs_snow_cm), storms(g.pred)
    r["storms_obs"], r["storms_pred"] = len(so), len(sp)
    r["storm_obs_median"] = float(np.median(so)) if so else np.nan
    r["storm_pred_median"] = float(np.median(sp)) if sp else np.nan
    rows.append(r)
score = pd.DataFrame(rows).set_index("site").round(2)
print(score.T.to_string())

# Refit on all labelled seasons for the app
final = model().fit(lab[FEATS], lab.obs_snow_cm)

def export(est, feats):
    """Dump the boosted trees to JSON so the browser can run the model without a server."""
    trees = []
    for it in est._predictors:
        nodes = it[0].nodes
        trees.append([[int(n["feature_idx"]), float(n["num_threshold"]), int(n["left"]), int(n["right"]),
                       float(n["value"]), int(n["is_leaf"]), int(n["missing_go_to_left"])] for n in nodes])
    return dict(features=feats, baseline=float(est._baseline_prediction.ravel()[0]), link="log", trees=trees)

out = ROOT / "app" / "model.json"
out.write_text(json.dumps(export(final, FEATS), separators=(",", ":")))
print("model ->", out, round(out.stat().st_size / 1e6, 2), "MB")
score.to_csv(ROOT / "data" / "scores.csv")

# sanity check: JS-style evaluation matches sklearn
def js_predict(mj, X):
    raw = np.full(len(X), mj["baseline"])
    Xv = X[mj["features"]].values
    for t in mj["trees"]:
        for i, x in enumerate(Xv):
            n = 0
            while not t[n][5]:
                f, thr, l, r_, _, _, ml = t[n]
                v = x[f]
                n = (l if ml else r_) if np.isnan(v) else (l if v <= thr else r_)
            raw[i] += t[n][4]
    return np.exp(raw)
mj = json.loads(out.read_text())
smp = te.sample(50, random_state=1)
print("export max abs diff:", np.abs(js_predict(mj, smp) - final.predict(smp[FEATS])).max())
