"""Deterministic attraction tickets. No network, AWS, or ticket-provider credentials."""

from __future__ import annotations

import hashlib
import os

from .errors import AttractionProviderError
from .result import booking_result

# Set to "1" to make the sandbox raise. `book` must return status failed.
FORCE_ERROR_ENV = "ROAM_ATTRACTION_FORCE_ERROR"


class SandboxAttractionProvider:
    """Quotes and confirms a ticket locally. The same inputs always book the same way."""

    def book(self, segment: dict, travelers: list, trip_id: str) -> dict:
        if os.environ.get(FORCE_ERROR_ENV) == "1":
            raise AttractionProviderError("sandbox attraction provider forced error")
        return booking_result(
            segment_id=segment["segmentId"],
            status="booked",
            confirmation_code=_confirmation_code(segment, travelers, trip_id),
            price=_price(segment["name"], segment["city"], segment["partySize"]),
            error=None,
        )


def _confirmation_code(segment: dict, travelers: list, trip_id: str) -> str:
    traveler_names = ",".join(_traveler_name(traveler) for traveler in travelers)
    time = "" if segment.get("time") is None else str(segment["time"])
    raw = "|".join(
        [
            trip_id.strip(),
            str(segment["segmentId"]).strip(),
            str(segment["name"]).strip(),
            str(segment["city"]).strip(),
            str(segment["date"]),
            time,
            str(segment["partySize"]),
            traveler_names,
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-{digest}"


def _price(name: str, city: str, party_size: int) -> dict:
    key = f"{name.strip().lower()}|{city.strip().lower()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    unit_dollars = 18 + (int(digest[:8], 16) % 50)
    total = unit_dollars * party_size
    return {"amount": f"{total}.00", "currency": "USD"}


def _traveler_name(traveler: object) -> str:
    if isinstance(traveler, dict):
        name = traveler.get("name")
        return name.strip() if isinstance(name, str) else ""
    return str(traveler)
