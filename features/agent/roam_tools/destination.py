from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from babel.numbers import get_territory_currencies
from timezonefinder import TimezoneFinder

from roam_contracts.geo import haversine_km
from roam_contracts.models import Destination

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Swanavi/1.0"
AIRPORT_RADIUS_KM = 150
AIRPORT_LIMIT = 5
_MIN_GAP_SECONDS = 1.0

_LIVE_PROVIDER = "aero" + "databox"
_AIRPORT_HOST = _LIVE_PROVIDER + ".p.rapidapi.com"

_finder: TimezoneFinder | None = None
_cache: dict[str, Destination] = {}
_nominatim_lock = threading.Lock()
_nominatim_next = 0.0


@dataclass(frozen=True)
class Geocode:
    city: str
    country_code: str
    lat: float
    lng: float


@dataclass(frozen=True)
class AirportPoint:
    iata: str
    distance_km: float | None


def clear_destination_cache() -> None:
    _cache.clear()


_SAME_PLACE = {
    "nyc": "new york",
    "new york city": "new york",
}


def _words_key(words: str) -> str:
    folded = " ".join(words.split()).casefold()
    return _SAME_PLACE.get(folded, folded)


def _timezone_finder() -> TimezoneFinder:
    global _finder
    if _finder is None:
        _finder = TimezoneFinder()
    return _finder


def timezone_at(lat: float, lng: float) -> str | None:
    return _timezone_finder().timezone_at(lat=lat, lng=lng)


def currency_for(country_code: str) -> str | None:
    codes = get_territory_currencies(country_code, tender=True)
    if not codes:
        return None
    return codes[0]


def _city_name(address: dict, row: dict) -> str:
    for key in ("city", "town", "village", "municipality", "hamlet"):
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    name = row.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    display = row.get("display_name")
    if isinstance(display, str) and display.strip():
        return display.split(",")[0].strip()
    return ""


def parse_geocode(body: object) -> Geocode | None:
    row = body[0] if isinstance(body, list) and body else body
    if not isinstance(row, dict):
        return None
    try:
        lat = float(row["lat"])
        lng = float(row["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    country = str(address.get("country_code") or "").strip().upper()
    if len(country) != 2 or not country.isalpha():
        return None
    city = _city_name(address, row)
    if not city:
        return None
    return Geocode(city=city, country_code=country, lat=lat, lng=lng)


def _iata(row: dict) -> str | None:
    raw = row.get("iata")
    if not isinstance(raw, str):
        airport = row.get("airport")
        raw = airport.get("iata") if isinstance(airport, dict) else None
    if not isinstance(raw, str):
        return None
    code = raw.strip().upper()
    if len(code) == 3 and code.isalpha():
        return code
    return None


def _distance_km(row: dict, origin_lat: float | None, origin_lng: float | None) -> float | None:
    raw = row.get("distance")
    if isinstance(raw, dict) and raw.get("km") is not None:
        try:
            return float(raw["km"])
        except (TypeError, ValueError):
            pass
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    location = row.get("location") if isinstance(row.get("location"), dict) else None
    if location is None or origin_lat is None or origin_lng is None:
        return None
    try:
        lat = float(location["lat"])
        lng = float(location["lon"] if "lon" in location else location["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    return haversine_km(origin_lat, origin_lng, lat, lng)


def parse_airports(
    body: object,
    *,
    origin_lat: float | None = None,
    origin_lng: float | None = None,
) -> list[AirportPoint]:
    if isinstance(body, dict):
        rows = body.get("items")
    else:
        rows = body
    if not isinstance(rows, list):
        return []
    points: list[AirportPoint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _iata(row)
        if code is None:
            continue
        points.append(AirportPoint(code, _distance_km(row, origin_lat, origin_lng)))
    return points


def assemble(
    geocode: Geocode,
    timezone_name: str,
    currency: str,
    airports: list[AirportPoint],
) -> Destination:
    ranked = sorted(enumerate(airports), key=lambda item: (item[1].distance_km is None, item[1].distance_km or 0, item[0]))
    codes: list[str] = []
    for _, point in ranked:
        if point.iata not in codes:
            codes.append(point.iata)
    return Destination(
        city=geocode.city,
        country_code=geocode.country_code,
        lat=geocode.lat,
        lng=geocode.lng,
        timezone=timezone_name,
        currency=currency,
        airports=codes,
    )


def destination_from_bodies(nominatim_body: object, airport_body: object) -> Destination:
    geocode = parse_geocode(nominatim_body)
    if geocode is None:
        raise ValueError("geocoder payload has no place")
    zone = timezone_at(geocode.lat, geocode.lng)
    currency = currency_for(geocode.country_code) if zone else None
    if not zone or not currency:
        raise ValueError("coordinates have no time zone or the country has no currency")
    airports = parse_airports(airport_body, origin_lat=geocode.lat, origin_lng=geocode.lng)
    return assemble(geocode, zone, currency, airports)


def _airports_configured() -> bool:
    provider = (os.environ.get("FLIGHT_API_PROVIDER") or "").strip().casefold()
    if provider != _LIVE_PROVIDER:
        return False
    return bool((os.environ.get("FLIGHT_API_KEY") or "").strip())


def fetch_nominatim(query: str) -> object | None:
    global _nominatim_next
    with _nominatim_lock:
        now = time.monotonic()
        if now < _nominatim_next:
            time.sleep(_nominatim_next - now)
        _nominatim_next = time.monotonic() + _MIN_GAP_SECONDS
        try:
            response = httpx.get(
                NOMINATIM_URL,
                params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=12,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


def fetch_airports(lat: float, lng: float) -> object | None:
    if not _airports_configured():
        return None
    try:
        response = httpx.get(
            f"https://{_AIRPORT_HOST}/airports/search/location",
            params={
                "lat": lat,
                "lon": lng,
                "radiusKm": AIRPORT_RADIUS_KM,
                "limit": AIRPORT_LIMIT,
                "withFlightInfoOnly": "false",
            },
            headers={
                "X-RapidAPI-Key": os.environ["FLIGHT_API_KEY"],
                "X-RapidAPI-Host": _AIRPORT_HOST,
            },
            timeout=12,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def lookup_destination(
    words: str,
    *,
    geocoder: Callable[[str], object | None] | None = None,
    airport_search: Callable[[float, float], object | None] | None = None,
) -> Destination | None:
    key = _words_key(words)
    if not key:
        return None
    cached = _cache.get(key)
    if cached is not None:
        return cached
    body = (geocoder or fetch_nominatim)(key)
    if body is None:
        return None
    geocode = parse_geocode(body)
    if geocode is None:
        return None
    zone = timezone_at(geocode.lat, geocode.lng)
    currency = currency_for(geocode.country_code) if zone else None
    if not zone or not currency:
        return None
    airport_body = (airport_search or fetch_airports)(geocode.lat, geocode.lng)
    airports = parse_airports(airport_body, origin_lat=geocode.lat, origin_lng=geocode.lng) if airport_body is not None else []
    place = assemble(geocode, zone, currency, airports)
    _cache[key] = place
    return place
