# Training sites (where snowfall is observed) and target resorts.
SITES = {
    # Vermont training stations (NOAA GHCN-Daily COOP, measured 24h snowfall)
    "mt_mansfield": dict(lat=44.5247, lon=-72.8153, elev=1204, tz="America/New_York", region="VT"),
    "chittenden":   dict(lat=43.7064, lon=-72.9617, elev=354,  tz="America/New_York", region="VT"),
    # New Mexico training stations (NRCS SNOTEL, snow depth sensor)
    "taos_powderhorn": dict(lat=36.582, lon=-105.456, elev=3359, tz="America/Denver", region="NM"),
    "red_river_pass":  dict(lat=36.699, lon=-105.341, elev=2999, tz="America/Denver", region="NM"),
}
RESORTS = {
    # elevation = roughly mid-mountain
    "killington": dict(name="Killington, VT", lat=43.6045, lon=-72.8201, elev=1100, tz="America/New_York", region="VT"),
    "taos":       dict(name="Taos Ski Valley, NM", lat=36.5960, lon=-105.4545, elev=3200, tz="America/Denver", region="NM"),
}
DAILY = ["temperature_2m_max","temperature_2m_min","temperature_2m_mean","precipitation_sum",
         "snowfall_sum","precipitation_hours","wind_speed_10m_max","wind_direction_10m_dominant",
         "relative_humidity_2m_mean","pressure_msl_mean"]
# Extra places used only to check forecasts against measured snow (NWS CoCoRaHS volunteer observers near
# Killington; their reports reach NOAA within about a week, unlike the Chittenden COOP record).
VERIFY_SITES = {
    "shrewsbury": dict(lat=43.5081, lon=-72.8824, elev=446, tz="America/New_York", region="VT"),
    "pittsfield": dict(lat=43.7361, lon=-72.8166, elev=348, tz="America/New_York", region="VT"),
    "barnard":    dict(lat=43.7522, lon=-72.6629, elev=491, tz="America/New_York", region="VT"),
}
