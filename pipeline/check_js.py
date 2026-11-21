"""Cross-check: browser feature+model code (snow.js) vs the Python pipeline on the snapshot data."""
import json, subprocess, pathlib, numpy as np, pandas as pd
import prepare
from sites import RESORTS, DAILY
APP = pathlib.Path(__file__).resolve().parent.parent / "app"
snap = json.loads((APP / "snapshot.json").read_text())
model = json.loads((APP / "model.json").read_text())
js = subprocess.run(["node", "-e", """
const S=require('%s/snow.js'); const m=require('%s/model.json'); const snap=require('%s/snapshot.json');
const out={}; for (const k of Object.keys(snap.resorts)) { const d=S.mergeDaily(snap.resorts[k].archive, snap.resorts[k].forecast);
 out[k]={daily:d, pred:S.predictDaily(m,d,S.RESORTS[k]).map(x=>x.cm)}; } console.log(JSON.stringify(out));""" % (APP, APP, APP)],
    capture_output=True, text=True, check=True)
res = json.loads(js.stdout)
for k, r in res.items():
    df = pd.DataFrame(r["daily"]); df["date"] = pd.to_datetime(df.pop("time")); df = df.set_index("date")[DAILY].astype(float)
    f = prepare.features(df, RESORTS[k])
    raw = np.full(len(f), model["baseline"]); X = f[model["features"]].values
    for t in model["trees"]:
        for i, x in enumerate(X):
            n = 0
            while not t[n][5]:
                fi, thr, l, rr, _, _, ml = t[n]; v = x[fi]
                n = (l if ml else rr) if np.isnan(v) else (l if v <= thr else rr)
            raw[i] += t[n][4]
    print(k, "days", len(f), "max abs diff cm", float(np.nanmax(np.abs(np.exp(raw) - np.array(r["pred"])))))
