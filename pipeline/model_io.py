"""Evaluate the exported tree model (app/model.json) exactly the way the browser does."""
import json, pathlib
import numpy as np

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

def load():
    return json.loads((APP / "model.json").read_text())

def predict(model, df):
    raw = np.full(len(df), model["baseline"])
    X = df[model["features"]].values.astype(float)
    for t in model["trees"]:
        for i, x in enumerate(X):
            n = 0
            while not t[n][5]:
                f, thr, l, r, _, _, ml = t[n]
                v = x[f]
                n = (l if ml else r) if np.isnan(v) else (l if v <= thr else r)
            raw[i] += t[n][4]
    return np.exp(raw)
