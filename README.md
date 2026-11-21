# Snowcast

Live site: https://swzerfoss-lab.github.io/2027snowforecast/

Daily, storm and season snowfall predictions for Killington, VT and Taos Ski Valley, NM, built on free data.

## How it works
1. `pipeline/fetch_meteo.py` downloads daily Open-Meteo historical weather (ERA5-based) for 4 observing stations and the 2 resorts.
2. Observed snowfall (ground truth), in `data/obs/`:
   - NOAA GHCN-Daily measured 24 h snowfall: Mt Mansfield, VT (USC00435416, 1204 m, 1995-2017) and Chittenden, VT (USC00431433, 354 m).
   - NRCS SNOTEL snow depth: Taos Powderhorn (1168:NM:SNTL, 3359 m) and Red River Pass #2 (715:NM:SNTL, 2999 m). Daily new snow = depth gain over 1 inch.
3. `pipeline/prepare.py` joins weather features (today, yesterday, tomorrow) with observed snow.
4. `pipeline/train.py` fits a gradient-boosted tree model (Poisson loss) pooled across stations, scores it with leave-seasons-out CV against Open-Meteo's raw `snowfall_sum`, and exports the trees to `app/model.json`.
5. `pipeline/build_app_data.py` writes `app/climatology.json` (model snowfall at each resort for past seasons), `app/meta.json` (scores, storm ranges) and `app/snapshot.json` (fallback forecast).

## The app
`app/` is a static site with no backend: the browser calls the Open-Meteo forecast and archive APIs and runs the model in JavaScript (`snow.js`). Serve it from any static host (GitHub Pages, Netlify), or locally:

    cd app && python3 -m http.server 8000

## Rebuild
    pip install pandas scikit-learn
    cd pipeline && python3 fetch_meteo.py && python3 train.py && python3 build_app_data.py

Open-Meteo's free tier has a daily request limit per IP; the history download is large, so run it once and keep `data/meteo/`.

## Forecast vs actual calibration
`pipeline/verify.py` runs daily in GitHub Actions. It saves the day's 16-day forecast for both resorts and for nearby measuring stations to `data/forecast_log.csv`, pulls recent measured snow (SNOTEL at Taos Powderhorn and Red River Pass; NWS COOP and CoCoRaHS observers at Chittenden, Shrewsbury, Pittsfield and Barnard, VT), and writes `app/calibration.json`: a correction factor per region and lead time (days 1-3, 4-7, 8-16) over the last 120 days, shrunk toward 1.0 with a 60 cm prior and clamped to 0.5-2.0. The app multiplies future days by that factor.

## Hosting
`.github/workflows/pages.yml` deploys `app/` to GitHub Pages on every push and after the daily check (Settings → Pages → Source: GitHub Actions).

## Resort photos and live snowfall
The top card shows a photo of the selected resort. When Open-Meteo's hourly forecast has snow falling at the resort right now, `app/snowfall.js` animates it over the photo, scaled to the rate: Flurries (under 0.1 in/hr), Light (0.1-0.5), Moderate (0.5-1), Heavy (1-2) and Blizzard (over 2 in/hr with gusts over 35 mph). It checks every 15 minutes, pauses when the tab is hidden, and shows a still frame for people who turn on reduced motion. Add `?snow=0` to `?snow=5` to the URL to preview a level.

Photos, from Wikimedia Commons, shown unedited:
- `app/img/killington.jpg`: [Bear Mountain Killington](https://commons.wikimedia.org/wiki/File:Bear_Mountain_Killington.jpg) by NHRHS2010, [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)
- `app/img/taos.jpg`: [Taos ski area](https://commons.wikimedia.org/wiki/File:Taos_ski_area.jpg) by Paul Sableman, [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/)
