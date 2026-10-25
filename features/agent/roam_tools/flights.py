from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx

from roam_contracts.models import GeoPoint, PlaceRef, SegmentMode, SegmentStatus, TravelSegment

ROOT = Path(__file__).resolve().parents[3]
FLIGHTS = ROOT / "contracts" / "fixtures" / "flights.json"


def lookup_fixture_flight(number: str, date: str) -> TravelSegment:
    if FLIGHTS.exists():
        payload = json.loads(FLIGHTS.read_text())
        for segment in payload.values():
            if segment.get("number") == number and str(segment["depart_at"]).startswith(date):
                return TravelSegment.model_validate(segment)
    return _unverified(number, date, "user")

# AeroDataBox on RapidAPI. Recorded as the paid provider for ticket 12.
AERODATABOX_HOST = "aerodatabox.p.rapidapi.com"
CACHE_SECONDS = 24 * 60 * 60

_cache: dict[tuple[str, str], tuple[float, TravelSegment]] = {}
_calls = 0


def flight_call_count() -> int:
    return _calls


def reset_flight_lookup() -> None:
    global _calls
    _cache.clear()
    _calls = 0


def lookup_flight(number: str, date: str) -> TravelSegment:
    provider = os.environ.get("FLIGHT_API_PROVIDER")
    if not provider:
        provider = "aerodatabox" if os.environ.get("FLIGHT_API_KEY") else "fixture"
    if provider == "fixture":
        return lookup_fixture_flight(number, date)
    if provider != "aerodatabox":
        return _unverified(number, date, provider)
    if not os.environ.get("FLIGHT_API_KEY"):
        return _unverified(number, date, "user")
    key = (number.upper().replace(" ", ""), date)
    cached = _cache.get(key)
    now = time.time()
    if cached is not None and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    limit = int(os.environ.get("FLIGHT_API_MAX_CALLS", "50"))
    if _calls >= limit:
        return _unverified(number, date, "aerodatabox")
    segment = _fetch_aerodatabox(number, date)
    _remember(key, segment)
    return segment


def _remember(key: tuple[str, str], segment: TravelSegment) -> None:
    global _calls
    _calls += 1
    _cache[key] = (time.time(), segment)


def _fetch_aerodatabox(number: str, date: str) -> TravelSegment:
    try:
        response = httpx.get(
            f"https://{AERODATABOX_HOST}/flights/number/{number}/{date}",
            params={"dateLocalRole": "Both"},
            headers={
                "X-RapidAPI-Key": os.environ["FLIGHT_API_KEY"],
                "X-RapidAPI-Host": AERODATABOX_HOST,
            },
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        return _unverified(number, date, "aerodatabox")
    flights = body if isinstance(body, list) else []
    if not flights:
        return _unverified(number, date, "aerodatabox")
    return _from_aerodatabox(flights[0], number, date)


def _from_aerodatabox(flight: dict, number: str, date: str) -> TravelSegment:
    departure = flight.get("departure") or {}
    arrival = flight.get("arrival") or {}
    depart_at = _local_time(departure)
    arrive_at = _local_time(arrival)
    if depart_at is None or arrive_at is None:
        return _unverified(number, date, "aerodatabox")
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
        source="aerodatabox",
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


def _unverified(number: str, date: str, source: str) -> TravelSegment:
    return TravelSegment(
        mode=SegmentMode.FLIGHT,
        number=number,
        from_place=PlaceRef(name="Unknown"),
        to_place=PlaceRef(name="Unknown"),
        depart_at=datetime.fromisoformat(f"{date}T00:00:00+09:00"),
        arrive_at=datetime.fromisoformat(f"{date}T00:00:00+09:00"),
        status=SegmentStatus.UNVERIFIED,
        source=source,
    )
