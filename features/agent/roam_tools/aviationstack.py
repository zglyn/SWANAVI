"""Aviationstack flight schedules. No fares. Key: AVIATIONSTACK_ACCESS_KEY."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode

import httpx

from roam_contracts.models import (
    FareConditions,
    FlightOffer,
    PlaceRef,
    SegmentMode,
    SegmentStatus,
    TravelSegment,
)

BASE = "https://api.aviationstack.com/v1"
_AIRPORT_CACHE: dict[str, list[str]] = {}


def access_key() -> str:
    return (os.environ.get("AVIATIONSTACK_ACCESS_KEY") or os.environ.get("AVIATIONSTACK_API_KEY") or "").strip()


def _get(path: str, params: dict) -> dict:
    key = access_key()
    if not key:
        raise RuntimeError("AVIATIONSTACK_ACCESS_KEY is not set")
    query = {**params, "access_key": key}
    url = f"{BASE}{path}?{urlencode(query)}"
    response = httpx.get(url, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        message = payload["error"].get("message") or payload["error"].get("code") or "aviationstack error"
        raise RuntimeError(str(message))
    return payload


def airports_for_place(place: str) -> list[str]:
    """IATA codes for a city or region name. Empty when none match."""
    token = place.split(",")[0].strip().lower()
    if not token:
        return []
    if token in _AIRPORT_CACHE:
        return _AIRPORT_CACHE[token]
    codes: list[str] = []
    try:
        payload = _get("/airports", {"search": token, "limit": 20})
    except Exception:
        _AIRPORT_CACHE[token] = []
        return []
    for row in payload.get("data") or []:
        iata = (row.get("iata_code") or "").upper()
        if not iata or len(iata) != 3:
            continue
        city = (row.get("city_name") or row.get("city_iata_code") or "").lower()
        name = (row.get("airport_name") or "").lower()
        if token in city or token in name or city.startswith(token[:4]):
            codes.append(iata)
    # Prefer unique order, major first by keeping API order.
    seen: set[str] = set()
    ordered = []
    for code in codes:
        if code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    _AIRPORT_CACHE[token] = ordered[:6]
    return _AIRPORT_CACHE[token]


def _parse_time(value: str | None, fallback_day: str, hour: int) -> datetime:
    if value:
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.fromisoformat(f"{fallback_day}T{hour:02d}:00:00+00:00")


def _duration_min(depart: datetime, arrive: datetime) -> int:
    minutes = int((arrive - depart).total_seconds() // 60)
    if minutes <= 0:
        minutes += 24 * 60
    return max(30, minutes)


def _place(code: str, name: str | None = None) -> PlaceRef:
    return PlaceRef(code=code.upper(), name=name or code.upper(), location=None)


def _flight_rows(dep: str, arr: str, day: str) -> list[dict]:
    rows: list[dict] = []
    # Real-time / historical flights for the date (free plan can return today's traffic).
    try:
        payload = _get("/flights", {"dep_iata": dep, "arr_iata": arr, "flight_date": day, "limit": 40})
        rows.extend(payload.get("data") or [])
    except Exception:
        pass
    # Future schedules on paid plans.
    try:
        payload = _get("/flightsFuture", {"iataCode": dep, "type": "departure", "date": day, "limit": 40})
        for row in payload.get("data") or []:
            arrival = ((row.get("arrival") or {}).get("iataCode") or "").upper()
            if arrival and arrival != arr.upper():
                continue
            rows.append(row)
    except Exception:
        pass
    return rows


def _offer_from_row(row: dict, *, direction: str, day: str, dep: str, arr: str) -> FlightOffer | None:
    departure = row.get("departure") or {}
    arrival = row.get("arrival") or {}
    airline = row.get("airline") or {}
    flight = row.get("flight") or {}
    dep_code = (departure.get("iata") or departure.get("iataCode") or dep or "").upper()
    arr_code = (arrival.get("iata") or arrival.get("iataCode") or arr or "").upper()
    # Drop rows that clearly name a different OD pair; allow missing codes (use params).
    if dep_code and dep_code != dep.upper():
        return None
    if arr_code and arr_code != arr.upper():
        return None
    dep_code = dep_code or dep.upper()
    arr_code = arr_code or arr.upper()
    carrier = (airline.get("iata") or airline.get("iataCode") or airline.get("name") or "XX")[:3].upper()
    number = str(flight.get("iata") or flight.get("number") or flight.get("iataNumber") or f"{carrier}0")
    if number.isdigit():
        number = f"{carrier}{number}"
    depart_at = _parse_time(
        departure.get("scheduled") or departure.get("estimated") or departure.get("scheduledTime"),
        day,
        9 if direction == "outbound" else 18,
    )
    arrive_raw = arrival.get("scheduled") or arrival.get("estimated") or arrival.get("scheduledTime")
    arrive_at = _parse_time(arrive_raw, day, 18 if direction == "outbound" else 12)
    if arrive_at <= depart_at:
        arrive_at = depart_at + timedelta(hours=11)
    offer_id = f"avs-{direction}-{number}-{day}-{dep_code}{arr_code}".lower().replace(" ", "")
    segment = TravelSegment(
        mode=SegmentMode.FLIGHT,
        carrier=carrier,
        number=number,
        from_place=_place(dep_code, departure.get("airport")),
        to_place=_place(arr_code, arrival.get("airport")),
        depart_at=depart_at if depart_at.tzinfo else depart_at.replace(tzinfo=timezone.utc),
        arrive_at=arrive_at if arrive_at.tzinfo else arrive_at.replace(tzinfo=timezone.utc),
        status=SegmentStatus.SCHEDULED,
        source="aviationstack",
        terminal=departure.get("terminal"),
    )
    return FlightOffer(
        id=offer_id,
        segments=[segment],
        carrier=carrier,
        stops=0,
        duration_min=_duration_min(segment.depart_at, segment.arrive_at),
        price=Decimal("0"),
        currency="USD",
        fare_conditions=FareConditions(refundable=False, changeable=False),
        why=["schedule only, fare not quoted"],
        deep_link=None,
        direction=direction,  # type: ignore[arg-type]
    )


def fetch_schedule_offers(
    origin_codes: list[str],
    destination_codes: list[str],
    depart_date: str,
    return_date: str | None,
) -> list[FlightOffer]:
    found: dict[str, FlightOffer] = {}
    for origin in origin_codes:
        for dest in destination_codes:
            for row in _flight_rows(origin, dest, depart_date):
                offer = _offer_from_row(row, direction="outbound", day=depart_date, dep=origin, arr=dest)
                if offer:
                    found.setdefault(offer.id, offer)
            if return_date:
                for row in _flight_rows(dest, origin, return_date):
                    offer = _offer_from_row(row, direction="return", day=return_date, dep=dest, arr=origin)
                    if offer:
                        found.setdefault(offer.id, offer)
    return list(found.values())
