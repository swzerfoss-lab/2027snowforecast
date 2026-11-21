# Snowcast

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

## Hosting
Pushing to `main` deploys `app/` to GitHub Pages via `.github/workflows/pages.yml` (Settings → Pages → Source: GitHub Actions).
