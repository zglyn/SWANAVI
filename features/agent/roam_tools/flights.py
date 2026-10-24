"""Fixture flight lookup. The paid provider is ticket 12 and is not wired here."""

from __future__ import annotations

import json
from pathlib import Path

from roam_contracts.models import PlaceRef, SegmentMode, SegmentStatus, TravelSegment

ROOT = Path(__file__).resolve().parents[3]
FLIGHTS = ROOT / "contracts" / "fixtures" / "flights.json"


def lookup_flight(number: str, date: str) -> TravelSegment:
    if FLIGHTS.exists():
        payload = json.loads(FLIGHTS.read_text())
        for segment in payload.values():
            if segment.get("number") == number and segment["depart_at"].startswith(date):
                return TravelSegment.model_validate(segment)
    return TravelSegment(
        mode=SegmentMode.FLIGHT,
        number=number,
        from_place=PlaceRef(name="Unknown"),
        to_place=PlaceRef(name="Unknown"),
        depart_at=f"{date}T00:00:00+09:00",
        arrive_at=f"{date}T00:00:00+09:00",
        status=SegmentStatus.UNVERIFIED,
        source="user",
    )
