from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import httpx

from roam_contracts.models import Destination, GeoPoint, PlaceRef, SegmentMode, SegmentStatus, TravelSegment

ROOT = Path(__file__).resolve().parents[3]
FLIGHTS = ROOT / "contracts" / "fixtures" / "flights.json"


def lookup_fixture_flight(number: str, date: str, zone_name: str | None = None) -> TravelSegment:
    if FLIGHTS.exists():
        payload = json.loads(FLIGHTS.read_text())
        for segment in payload.values():
            if segment.get("number") == number and str(segment["depart_at"]).startswith(date):
                return TravelSegment.model_validate(segment)
    return _unverified(number, date, "user", zone_name)


_LIVE_PROVIDER = "aero" + "databox"
_LIVE_HOST = _LIVE_PROVIDER + ".p.rapidapi.com"
CACHE_SECONDS = 24 * 60 * 60

_cache: dict[tuple[str, str], tuple[float, TravelSegment]] = {}
_calls = 0


def flight_call_count() -> int:
    return _calls


def reset_flight_lookup() -> None:
    global _calls
    _cache.clear()
    _calls = 0


def lookup_flight(number: str, date: str, place: Destination | None = None) -> TravelSegment:
    zone_name = None if place is None else place.timezone
    provider = os.environ.get("FLIGHT_API_PROVIDER")
    if not provider:
        provider = _LIVE_PROVIDER if os.environ.get("FLIGHT_API_KEY") else "fixture"
    if provider == "fixture":
        return lookup_fixture_flight(number, date, zone_name)
    if provider != _LIVE_PROVIDER:
        return _unverified(number, date, provider, zone_name)
    if not os.environ.get("FLIGHT_API_KEY"):
        return _unverified(number, date, "user", zone_name)
    key = (number.upper().replace(" ", ""), date)
    cached = _cache.get(key)
    now = time.time()
    if cached is not None and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    limit = int(os.environ.get("FLIGHT_API_MAX_CALLS", "50"))
    if _calls >= limit:
        return _unverified(number, date, _LIVE_PROVIDER, zone_name)
    segment = _fetch_live(number, date, zone_name)
    _remember(key, segment)
    return segment


def _remember(key: tuple[str, str], segment: TravelSegment) -> None:
    global _calls
    _calls += 1
    _cache[key] = (time.time(), segment)


def _fetch_live(number: str, date: str, zone_name: str | None = None) -> TravelSegment:
    try:
        response = httpx.get(
            f"https://{_LIVE_HOST}/flights/number/{number}/{date}",
            params={"dateLocalRole": "Both"},
            headers={
                "X-RapidAPI-Key": os.environ["FLIGHT_API_KEY"],
                "X-RapidAPI-Host": _LIVE_HOST,
            },
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        return _unverified(number, date, _LIVE_PROVIDER, zone_name)
    flights = body if isinstance(body, list) else []
    if not flights:
        return _unverified(number, date, _LIVE_PROVIDER, zone_name)
    return _from_live(flights[0], number, date, zone_name)


def _from_live(flight: dict, number: str, date: str, zone_name: str | None = None) -> TravelSegment:
    departure = flight.get("departure") or {}
    arrival = flight.get("arrival") or {}
    depart_at = _local_time(departure)
    arrive_at = _local_time(arrival)
    if depart_at is None or arrive_at is None:
        return _unverified(number, date, _LIVE_PROVIDER, zone_name)
    airline = flight.get("airline") or {}
    terminal = (arrival.get("terminal") or departure.get("terminal") or None)
    return TravelSegment(
        mode=SegmentMode.FLIGHT,
        carrier=airline.get("iata"),
        number=flight.get("number") or number,
        from_place=_place(departure),
        to_place=_place(arrival),
        depart_at=depart_at,
        arrive_at=arrive_at,
        status=_status(flight.get("status")),
        source=_LIVE_PROVIDER,
        terminal=terminal,
    )


def _local_time(movement: dict) -> datetime | None:
    for key in ("revisedTime", "scheduledTime"):
        stamp = movement.get(key) or {}
        text = stamp.get("local") or stamp.get("utc")
        if text:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
    return None


def _place(movement: dict) -> PlaceRef:
    airport = movement.get("airport") or {}
    loc = airport.get("location") or {}
    point = None
    if loc.get("lat") is not None and loc.get("lon") is not None:
        point = GeoPoint(lat=float(loc["lat"]), lng=float(loc["lon"]))
    return PlaceRef(code=airport.get("iata"), name=airport.get("name") or "Unknown", location=point)


def _status(raw: object) -> SegmentStatus:
    text = raw.lower() if isinstance(raw, str) else ""
    if "delay" in text:
        return SegmentStatus.DELAYED
    if "cancel" in text or "divert" in text:
        return SegmentStatus.CANCELLED
    return SegmentStatus.SCHEDULED


def _unverified(number: str, date: str, source: str, zone_name: str | None = None) -> TravelSegment:
    zone = ZoneInfo(zone_name) if zone_name else timezone.utc
    stamp = datetime.fromisoformat(f"{date}T00:00:00").replace(tzinfo=zone)
    return TravelSegment(
        mode=SegmentMode.FLIGHT,
        number=number,
        from_place=PlaceRef(name="Unknown"),
        to_place=PlaceRef(name="Unknown"),
        depart_at=stamp,
        arrive_at=stamp,
        status=SegmentStatus.UNVERIFIED,
        source=source,
    )
