"""Deterministic flight bookings. No network, AWS, or airline credentials."""

from __future__ import annotations

import hashlib
import os

from .errors import FlightProviderError
from .result import booking_result

# Set to "1" to make the sandbox raise. `book` must return status failed.
FORCE_ERROR_ENV = "ROAM_FLIGHT_FORCE_ERROR"

_CABIN_PERCENT = {
    "economy": 100,
    "premium_economy": 160,
    "business": 280,
    "first": 450,
}


class SandboxFlightProvider:
    """Quotes and confirms a flight locally. The same inputs always book the same way."""

    def book(self, segment: dict, travelers: list, trip_id: str) -> dict:
        if os.environ.get(FORCE_ERROR_ENV) == "1":
            raise FlightProviderError("sandbox flight provider forced error")
        party = _party(segment, travelers)
        round_trip = segment.get("returnDate") is not None
        return booking_result(
            segment_id=segment["segmentId"].strip(),
            status="booked",
            confirmation_code=_confirmation_code(segment, party, trip_id),
            price=_price(
                segment["from"],
                segment["to"],
                segment["cabin"],
                round_trip,
                len(party),
            ),
            error=None,
        )


def _party(segment: dict, travelers: list) -> list[tuple[str, str]]:
    index: dict[str, dict] = {}
    for traveler in travelers:
        if not isinstance(traveler, dict):
            continue
        traveler_id = traveler.get("id", traveler.get("travelerId"))
        if isinstance(traveler_id, str) and traveler_id.strip():
            index[traveler_id.strip()] = traveler
    party: list[tuple[str, str]] = []
    for traveler_id in segment["travelerIds"]:
        party.append((traveler_id.strip(), _name(index[traveler_id.strip()])))
    return party


def _name(traveler: dict) -> str:
    name = traveler.get("name")
    if isinstance(name, str) and name.strip():
        return " ".join(name.split())
    given = traveler.get("givenName") if isinstance(traveler.get("givenName"), str) else ""
    family = traveler.get("familyName") if isinstance(traveler.get("familyName"), str) else ""
    return " ".join(f"{given} {family}".split())


def _confirmation_code(segment: dict, party: list[tuple[str, str]], trip_id: str) -> str:
    return_date = "" if segment.get("returnDate") is None else str(segment["returnDate"])
    raw = "|".join(
        [
            trip_id.strip(),
            segment["segmentId"].strip(),
            str(segment["from"]).strip().upper(),
            str(segment["to"]).strip().upper(),
            str(segment["departDate"]),
            return_date,
            str(segment["cabin"]),
            ",".join(f"{traveler_id}:{name}" for traveler_id, name in sorted(party)),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-{digest}"


def _price(origin: str, destination: str, cabin: str, round_trip: bool, count: int) -> dict:
    key = f"{origin.strip().upper()}|{destination.strip().upper()}|{cabin}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    base = 120 + (int(digest[:8], 16) % 400)
    amount = base * _CABIN_PERCENT[cabin] // 100
    if round_trip:
        amount = amount * 185 // 100
    amount *= count
    return {"amount": f"{amount}.00", "currency": "USD"}
