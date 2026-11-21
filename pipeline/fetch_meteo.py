"""Download daily Open-Meteo historical (ERA5-based) weather for every site and resort."""
import json, sys, time, urllib.request, urllib.parse, pathlib
from sites import SITES, RESORTS, DAILY
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "meteo"
OUT.mkdir(parents=True, exist_ok=True)
def get(name, s, start, end):
    q = dict(latitude=s["lat"], longitude=s["lon"], elevation=s["elev"], start_date=start, end_date=end,
             daily=",".join(DAILY), timezone=s["tz"])
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(q)
    for i in range(6):
        try:
            return json.load(urllib.request.urlopen(url, timeout=180))
        except Exception as e:
            print(name, "retry", e); time.sleep(70 * (i + 1))
    raise SystemExit("failed " + name)
if __name__ == "__main__":
    for name, s in {**SITES, **RESORTS}.items():
        f = OUT / f"{name}.json"
        if f.exists(): continue
        d = get(name, s, "2005-07-01", sys.argv[1] if len(sys.argv) > 1 else "2026-11-15")
        f.write_text(json.dumps(d)); print(name, len(d["daily"]["time"]), "days", flush=True); time.sleep(65)
