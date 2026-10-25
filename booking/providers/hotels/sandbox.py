"""Deterministic hotel sandbox. No network, no AWS, no API key."""

from __future__ import annotations

import hashlib
import os
from decimal import Decimal, ROUND_HALF_UP

from .errors import HotelProviderError
from .segment import HotelStay, traveler_names

# Fixed nightly room rates so a demo segment always prices the same way.
_KNOWN_NIGHTLY_USD = {
    "kyoto": Decimal("220.00"),
    "tokyo": Decimal("250.00"),
    "osaka": Decimal("180.00"),
    "new york": Decimal("320.00"),
    "nyc": Decimal("320.00"),
    "paris": Decimal("280.00"),
    "london": Decimal("270.00"),
}

_FORCED_FAULTS = {"error", "provider_error", "fail", "true", "1"}


class SandboxHotelProvider:
    """Book a hotel segment locally. The same stay always yields the same code."""

    name = "sandbox"

    def book(
        self,
        stay: HotelStay,
        travelers: list,
        trip_id: str,
        fault: object = None,
    ) -> dict:
        _raise_if_fault(fault)
        _raise_if_fault(os.environ.get("HOTEL_SANDBOX_FAULT"))
        nights = stay.nights
        if nights < 1:
            raise HotelProviderError("stay must include at least one night")
        total = (_nightly_rate(stay.city) * nights * stay.rooms).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return {
            "segmentId": stay.segment_id,
            "kind": "hotel",
            "status": "booked",
            "confirmationCode": _confirmation_code(stay, travelers, trip_id),
            "price": {"amount": f"{total:.2f}", "currency": "USD"},
            "error": None,
        }


def _raise_if_fault(fault: object) -> None:
    if fault is None or fault is False:
        return
    if isinstance(fault, str):
        text = fault.strip()
        if not text:
            return
        if text.lower() in _FORCED_FAULTS:
            raise HotelProviderError("sandbox hotel provider failed")
        raise HotelProviderError(text)
    raise HotelProviderError("sandbox hotel provider failed")


def _nightly_rate(city: str) -> Decimal:
    known = _KNOWN_NIGHTLY_USD.get(city)
    if known is not None:
        return known
    digest = hashlib.sha256(city.encode("utf-8")).digest()
    dollars = 120 + int.from_bytes(digest[:2], "big") % 161
    return Decimal(dollars).quantize(Decimal("0.01"))


def _confirmation_code(stay: HotelStay, travelers: list, trip_id: str) -> str:
    payload = "|".join(
        [
            trip_id.strip(),
            stay.segment_id,
            stay.city,
            stay.check_in.isoformat(),
            stay.check_out.isoformat(),
            str(stay.rooms),
            str(stay.guests),
            ",".join(traveler_names(travelers)),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-{digest}"
