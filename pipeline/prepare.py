"""Build one training table: Open-Meteo weather features + observed daily new snow (cm) per site."""
import json, pathlib
import numpy as np, pandas as pd
from sites import SITES, DAILY

ROOT = pathlib.Path(__file__).resolve().parent.parent / "data"

def meteo(name):
    d = json.loads((ROOT / "meteo" / f"{name}.json").read_text())["daily"]
    df = pd.DataFrame(d)[["time"] + DAILY]
    df["date"] = pd.to_datetime(df.pop("time"))
    return df.set_index("date")

def obs_ghcn(station, path=None):
    df = pd.read_csv(path or ROOT / "obs" / f"ghcn_{station}.csv", parse_dates=["DATE"]).set_index("DATE")
    # COOP observers read the gauge in the morning: the value on day D is mostly snow that fell on D-1.
    # Shift so the target lines up with the calendar day the snow fell.
    snow_cm = df["SNOW"] / 10.0
    return snow_cm.shift(-1).rename("obs_snow_cm")

def obs_snotel(sid, path=None):
    raw = json.loads(pathlib.Path(path or ROOT / "obs" / f"sntl_{sid}.json").read_text())
    series = {}
    for el in raw[0]["data"]:
        code = el["stationElement"]["elementCode"]
        series[code] = pd.Series({pd.Timestamp(v["date"]): v.get("value") for v in el["values"]}, dtype=float)
    df = pd.DataFrame(series).asfreq("D")
    # SNOTEL daily = midnight reading. New snow on day D ~ rise in depth from D to D+1 (inches -> cm).
    d_depth = (df["SNWD"].shift(-1) - df["SNWD"]) * 2.54
    d_swe = (df["WTEQ"].shift(-1) - df["WTEQ"]) * 2.54
    new = d_depth.where(d_depth >= 2.54, 0.0)          # ignore sensor jitter under 1 inch
    new = new.where(new < 90)                            # drop sensor spikes
    # Depth sensors miss snow that settles the same day; when SWE rose but depth didn't, keep NaN (unknown)
    new = new.mask((new == 0) & (d_swe >= 0.5))
    new[(df["SNWD"].isna()) | (df["SNWD"].shift(-1).isna())] = np.nan
    return new.rename("obs_snow_cm")

def features(m, site):
    f = pd.DataFrame(index=m.index)
    for c in m.columns:
        if c == "wind_direction_10m_dominant":
            rad = np.deg2rad(m[c])
            f["wdir_sin"], f["wdir_cos"] = np.sin(rad), np.cos(rad)
        else:
            f[c] = m[c]
    for c in ["precipitation_sum", "snowfall_sum", "temperature_2m_mean", "temperature_2m_max", "precipitation_hours"]:
        f[c + "_prev"] = m[c].shift(1)
        f[c + "_next"] = m[c].shift(-1)
    f["precip_3d"] = m["precipitation_sum"].rolling(3, center=True).sum()
    f["doy_sin"] = np.sin(2 * np.pi * f.index.dayofyear / 365.25)
    f["doy_cos"] = np.cos(2 * np.pi * f.index.dayofyear / 365.25)
    f["elev"] = site["elev"]
    f["is_nm"] = 1.0 if site["region"] == "NM" else 0.0
    return f

FEATURES = None

def build():
    global FEATURES
    obs = {
        "mt_mansfield": obs_ghcn("USC00435416"),
        "chittenden": obs_ghcn("USC00431433"),
        "taos_powderhorn": obs_snotel("1168"),
        "red_river_pass": obs_snotel("715"),
    }
    frames = []
    for name, site in SITES.items():
        if not (ROOT / "meteo" / f"{name}.json").exists():
            print("skipping", name, "(no weather yet)"); continue
        f = features(meteo(name), site)
        f = f.join(obs[name], how="left")
        f["site"] = name
        frames.append(f)
    df = pd.concat(frames)
    df["season"] = np.where(df.index.month >= 7, df.index.year, df.index.year - 1)  # season 2023 = Jul 2023-Jun 2024
    FEATURES = [c for c in df.columns if c not in ("obs_snow_cm", "site", "season")]
    return df

if __name__ == "__main__":
    df = build()
    df.to_csv(ROOT / "train.csv")
    print(df.groupby("site")["obs_snow_cm"].agg(["count", "mean", "max"]))
    print(df.groupby(["site", "season"])["obs_snow_cm"].sum().unstack(0).tail(12).round(0))
