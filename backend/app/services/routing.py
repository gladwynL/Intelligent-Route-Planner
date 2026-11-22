"""Route-alternative estimation for newly planned trips.

Two sources, always labelled so the UI never presents them as live navigation:

* ``osrm``      - driving distance/duration from the public OSRM demo server
                  (router.project-osrm.org, car profile only).  Optional; any
                  failure falls back to the heuristic.
* ``heuristic`` - straight-line (haversine) distance multiplied by a detour
                  factor, divided by a typical urban speed for the mode, plus
                  a fixed access/wait time.  These are planning estimates only.

Scoring is NOT done here: the database View 6 is the single source of truth
for the weighted recommendation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import requests
from flask import current_app

# mode -> (detour factor, average speed km/h, fixed overhead minutes)
MODE_PROFILES = {
    "driving": (1.30, 38.0, 3),
    "transit": (1.40, 22.0, 8),
    "cycling": (1.25, 15.0, 2),
    "walking": (1.20, 4.8, 0),
}
MAX_WALKING_KM = 15.0   # do not suggest walking alternatives longer than this
MAX_CYCLING_KM = 40.0

SOURCE_LABELS = {
    "osrm": "OSRM driving route (public demo server)",
    "heuristic": "Heuristic estimate (straight-line x detour factor)",
}


@dataclass
class RouteEstimate:
    travel_mode: str
    distance_km: float
    duration_min: int
    source: str          # 'osrm' | 'heuristic'

    @property
    def label(self) -> str:
        return SOURCE_LABELS[self.source]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def heuristic(mode: str, straight_km: float) -> RouteEstimate:
    detour, speed, overhead = MODE_PROFILES[mode]
    dist = max(0.1, round(straight_km * detour, 2))
    minutes = max(1, round(dist / speed * 60 + overhead))
    return RouteEstimate(mode, dist, minutes, "heuristic")


def osrm_driving(origin: dict, dest: dict) -> RouteEstimate | None:
    cfg = current_app.config
    if not cfg.get("ENABLE_OSRM"):
        return None
    url = (f"{cfg['OSRM_URL'].rstrip('/')}/route/v1/driving/"
           f"{float(origin['longitude']):.6f},{float(origin['latitude']):.6f};"
           f"{float(dest['longitude']):.6f},{float(dest['latitude']):.6f}")
    try:
        resp = requests.get(url, params={"overview": "false"}, timeout=cfg["EXTERNAL_TIMEOUT_SECONDS"],
                            headers={"User-Agent": "IntelligentRoutePlanner/1.0 (educational project)"})
        data = resp.json()
        if resp.status_code != 200 or data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        dist = round(route["distance"] / 1000.0, 2)
        minutes = max(1, round(route["duration"] / 60.0))
        if dist <= 0:
            return None
        return RouteEstimate("driving", dist, minutes, "osrm")
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def estimate_alternatives(origin: dict, dest: dict, modes=None) -> list[RouteEstimate]:
    """Return estimates for each requested mode (skipping unrealistic walk/cycle lengths)."""
    straight = haversine_km(origin["latitude"], origin["longitude"], dest["latitude"], dest["longitude"])
    out: list[RouteEstimate] = []
    for mode in modes or MODE_PROFILES:
        if mode == "driving":
            est = osrm_driving(origin, dest) or heuristic("driving", straight)
        else:
            est = heuristic(mode, straight)
        if mode == "walking" and est.distance_km > MAX_WALKING_KM:
            continue
        if mode == "cycling" and est.distance_km > MAX_CYCLING_KM:
            continue
        out.append(est)
    return out
