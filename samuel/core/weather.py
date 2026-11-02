"""Current weather from Open-Meteo (free, no API key, non-commercial use).

Docs: https://open-meteo.com/en/docs and https://open-meteo.com/en/docs/geocoding-api
Off until `weather_city` or `weather_lat`/`weather_lon` is set in the config.
"""
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

import requests

HEADERS = {"User-Agent": "SAMUEL-assistant/5.0 (personal, non-commercial)"}

# WMO weather interpretation codes, from the Open-Meteo docs
WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog",
    48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle", 61: "Slight rain", 63: "Moderate rain",
    65: "Heavy rain", 66: "Light freezing rain", 67: "Heavy freezing rain", 71: "Slight snowfall",
    73: "Moderate snowfall", 75: "Heavy snowfall", 77: "Snow grains", 80: "Slight rain showers",
    81: "Moderate rain showers", 82: "Violent rain showers", 85: "Slight snow showers",
    86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    97: "Heavy thunderstorm", 99: "Thunderstorm with heavy hail",
}


class Weather:
    def __init__(self, city: str = "", lat: Optional[float] = None, lon: Optional[float] = None,
                 ttl: float = 900):
        self.city = (city or "").strip()
        self.coords: Optional[Tuple[float, float]] = (lat, lon) if lat is not None and lon is not None else None
        self.place = self.city
        self.ttl = ttl
        self._cache: Optional[Dict] = None
        self._cache_t = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.city or self.coords)

    def _geocode(self) -> None:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": self.city, "count": 1, "language": "en", "format": "json"},
                         headers=HEADERS, timeout=6)
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            raise LookupError(f"Open-Meteo has no place called {self.city!r}")
        top = results[0]
        self.coords = (top["latitude"], top["longitude"])
        self.place = ", ".join(x for x in (top.get("name"), top.get("country_code")) if x)

    def current(self, force: bool = False) -> Dict:
        if not self.configured:
            return {"ok": False, "reason": "not configured"}
        if self._cache and not force and time.time() - self._cache_t < self.ttl:
            return self._cache
        try:
            if self.coords is None:
                self._geocode()
            lat, lon = self.coords
            r = requests.get("https://api.open-meteo.com/v1/forecast", headers=HEADERS, timeout=6, params={
                "latitude": lat, "longitude": lon, "timezone": "auto",
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 1,
            })
            r.raise_for_status()
            data = r.json()
            cur = data["current"]
            daily = data.get("daily", {})
            first = lambda k: (daily.get(k) or [None])[0]   # noqa: E731
            self._cache = {
                "ok": True,
                "place": self.place or f"{lat:.2f}, {lon:.2f}",
                "temp": cur.get("temperature_2m"),
                "feels": cur.get("apparent_temperature"),
                "humidity": cur.get("relative_humidity_2m"),
                "wind": cur.get("wind_speed_10m"),
                "code": cur.get("weather_code"),
                "text": WMO.get(cur.get("weather_code"), "Unknown"),
                "is_day": bool(cur.get("is_day", 1)),
                "high": first("temperature_2m_max"),
                "low": first("temperature_2m_min"),
                "rain_chance": first("precipitation_probability_max"),
                "time": time.time(),
            }
            self._cache_t = time.time()
            return self._cache
        except Exception as exc:   # network down, bad city, API change
            if self._cache:
                stale = dict(self._cache)
                stale["stale"] = True
                return stale
            return {"ok": False, "reason": str(exc)}


def spoken(w: Dict) -> str:
    if not w.get("ok"):
        return ""
    parts = [f"In {w['place'].split(',')[0]} it's {round(w['temp'])} degrees, {w['text'].lower()}"]
    if w.get("feels") is not None and abs(w["feels"] - w["temp"]) >= 2:
        parts.append(f"feeling like {round(w['feels'])}")
    s = ", ".join(parts) + "."
    if w.get("rain_chance") is not None and w["rain_chance"] >= 40:
        s += f" {round(w['rain_chance'])} percent chance of rain today."
    return s
