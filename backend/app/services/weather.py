"""Open-Meteo current-weather client and the application-defined risk mapping.

Open-Meteo (https://open-meteo.com) is a free REST/JSON weather API that needs
no API key.  We request *current* conditions for a coordinate and translate
the WMO weather code plus wind into a 0-5 severity so it can be stored in
``condition_observation.severity`` and feed View 6's safety score.

IMPORTANT: the severity is an application-defined heuristic for ranking route
alternatives.  It is NOT an authoritative road-safety assessment.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime

import requests
from flask import current_app

CURRENT_FIELDS = "temperature_2m,precipitation,weather_code,wind_speed_10m,wind_gusts_10m"

# WMO weather interpretation codes (as documented by Open-Meteo) -> (label, base severity 0-5)
WMO_CODES: dict[int, tuple[str, int]] = {
    0: ("Clear sky", 0), 1: ("Mainly clear", 0), 2: ("Partly cloudy", 0), 3: ("Overcast", 0),
    45: ("Fog", 2), 48: ("Depositing rime fog", 3),
    51: ("Light drizzle", 1), 53: ("Moderate drizzle", 1), 55: ("Dense drizzle", 2),
    56: ("Light freezing drizzle", 3), 57: ("Dense freezing drizzle", 4),
    61: ("Slight rain", 1), 63: ("Moderate rain", 2), 65: ("Heavy rain", 3),
    66: ("Light freezing rain", 4), 67: ("Heavy freezing rain", 5),
    71: ("Slight snowfall", 2), 73: ("Moderate snowfall", 3), 75: ("Heavy snowfall", 4),
    77: ("Snow grains", 2),
    80: ("Slight rain showers", 1), 81: ("Moderate rain showers", 2), 82: ("Violent rain showers", 3),
    85: ("Slight snow showers", 3), 86: ("Heavy snow showers", 4),
    95: ("Thunderstorm", 4), 96: ("Thunderstorm with slight hail", 5), 99: ("Thunderstorm with heavy hail", 5),
}


class WeatherServiceError(Exception):
    """Raised when Open-Meteo cannot be reached or returns unusable data."""


@dataclass
class CurrentWeather:
    latitude: float
    longitude: float
    observed_at: datetime
    temperature_c: float | None
    precipitation_mm: float | None
    weather_code: int
    condition: str
    wind_speed_kmh: float | None
    wind_gusts_kmh: float | None
    severity: int
    risk_reasons: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["observed_at"] = self.observed_at.isoformat()
        return d

    def description(self) -> str:
        """Short text for condition_observation.description (VARCHAR(200))."""
        parts = [self.condition]
        if self.temperature_c is not None:
            parts.append(f"{self.temperature_c:.1f} C")
        if self.wind_speed_kmh is not None:
            parts.append(f"wind {self.wind_speed_kmh:.0f} km/h")
        if self.precipitation_mm:
            parts.append(f"precip {self.precipitation_mm:.1f} mm")
        text = ", ".join(parts) + f" (app risk estimate {self.severity}/5)"
        return text[:200]


def map_severity(code: int, wind_kmh: float | None, gusts_kmh: float | None,
                 temp_c: float | None) -> tuple[int, str, list[str]]:
    """Deterministic mapping of current conditions to a 0-5 risk severity."""
    label, sev = WMO_CODES.get(int(code), (f"Weather code {code}", 1))
    reasons = [f"{label} (WMO {code}) -> base {sev}"]
    if gusts_kmh is not None and gusts_kmh >= 70:
        if sev < 3:
            reasons.append(f"gusts {gusts_kmh:.0f} km/h >= 70 -> raised to 3")
        sev = max(sev, 3)
    elif wind_kmh is not None and wind_kmh >= 50:
        if sev < 2:
            reasons.append(f"wind {wind_kmh:.0f} km/h >= 50 -> raised to 2")
        sev = max(sev, 2)
    if temp_c is not None and temp_c <= -15:
        if sev < 2:
            reasons.append(f"temperature {temp_c:.0f} C <= -15 -> raised to 2")
        sev = max(sev, 2)
    return max(0, min(5, sev)), label, reasons


def fetch_current(latitude: float, longitude: float) -> CurrentWeather:
    """Call Open-Meteo for current weather at one coordinate and parse the JSON."""
    cfg = current_app.config
    params = {
        "latitude": f"{float(latitude):.5f}",
        "longitude": f"{float(longitude):.5f}",
        "current": CURRENT_FIELDS,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    }
    try:
        resp = requests.get(cfg["OPEN_METEO_URL"], params=params,
                            timeout=cfg["EXTERNAL_TIMEOUT_SECONDS"],
                            headers={"User-Agent": "IntelligentRoutePlanner/1.0 (educational project)"})
    except requests.RequestException as exc:
        raise WeatherServiceError(f"Could not reach Open-Meteo ({exc.__class__.__name__}).") from exc
    if resp.status_code != 200:
        reason = ""
        try:
            reason = resp.json().get("reason", "")
        except ValueError:
            pass
        raise WeatherServiceError(f"Open-Meteo returned HTTP {resp.status_code}. {reason}".strip())
    try:
        payload = resp.json()
        cur = payload["current"]
        code = int(cur["weather_code"])
        observed = datetime.fromisoformat(cur["time"])
    except (ValueError, KeyError, TypeError) as exc:
        raise WeatherServiceError("Open-Meteo returned an unexpected response format.") from exc

    def num(key):
        v = cur.get(key)
        return float(v) if isinstance(v, (int, float)) else None

    temp, wind, gusts = num("temperature_2m"), num("wind_speed_10m"), num("wind_gusts_10m")
    severity, label, reasons = map_severity(code, wind, gusts, temp)
    return CurrentWeather(
        latitude=float(payload.get("latitude", latitude)),
        longitude=float(payload.get("longitude", longitude)),
        observed_at=observed,
        temperature_c=temp,
        precipitation_mm=num("precipitation"),
        weather_code=code,
        condition=label,
        wind_speed_kmh=wind,
        wind_gusts_kmh=gusts,
        severity=severity,
        risk_reasons=reasons,
    )
