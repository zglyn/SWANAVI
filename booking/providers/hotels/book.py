"""Book one hotel segment from a trip plan.

The AgentCore ``handler`` is the supported invoke path and calls ``book``.
The default provider is a deterministic sandbox. Amadeus test (Hotel Search,
then Hotel Booking) runs only when ``ROAM_HOTEL_PROVIDER=live`` and
``AMADEUS_CLIENT_ID``, ``AMADEUS_CLIENT_SECRET``, and ``AMADEUS_HOSTNAME=test``
are all set.
"""

from __future__ import annotations

import os
import re
from typing import Protocol, TypedDict

from .errors import HotelProviderError
from .safety import contains_payment_instrument
from .sandbox import SandboxHotelProvider
from .segment import parse_hotel_request, read_segment_id

_SANDBOX_CODE = re.compile(r"^SANDBOX-[A-F0-9]{12}$")
_AMOUNT = re.compile(r"^\d+\.\d{2}$")
_CARD_ERROR = "Remove card or payment details. Hotel booking never charges a card."


class HotelPrice(TypedDict):
    amount: str
    currency: str


class HotelBookingResult(TypedDict):
    segmentId: str | None
    kind: str
    status: str
    confirmationCode: str | None
    price: HotelPrice | None
    error: str | None


def book(segment: dict, travelers: list, trip_id: str) -> HotelBookingResult:
    """Book a hotel segment.

    Provider failures return ``status="failed"`` and do not raise. Incomplete
    input returns ``status="needs_user"``. Sandbox confirmation codes start
    with ``SANDBOX-``.
    """
    segment_id = read_segment_id(segment)
    try:
        problems: list[str] = []
        if contains_payment_instrument(segment) or contains_payment_instrument(travelers):
            problems.append(_CARD_ERROR)
        stay, parse_problems = parse_hotel_request(segment, travelers, trip_id)
        problems.extend(parse_problems)
        if problems or stay is None:
            return _result(segment_id, "needs_user", error="; ".join(problems) or "hotel segment is incomplete")
        provider = _resolve_provider()
        fault = segment.get("sandboxFault") if isinstance(segment, dict) else None
        raw = provider.book(stay, travelers, trip_id, fault=fault)
        return _accept(provider, raw, stay.segment_id)
    except HotelProviderError as exc:
        return _result(segment_id, "failed", error=str(exc))


class _Provider(Protocol):
    name: str

    def book(self, stay: object, travelers: list, trip_id: str, fault: object = None) -> dict: ...


def _resolve_provider() -> _Provider:
    mode = os.environ.get("ROAM_HOTEL_PROVIDER", "sandbox").strip().lower() or "sandbox"
    if mode == "sandbox":
        return SandboxHotelProvider()
    if mode != "live":
        raise HotelProviderError(f"unknown ROAM_HOTEL_PROVIDER {mode!r}")
    client_id, client_secret = _amadeus_credentials()
    # Import only after the test-host gate so a missing or production config
    # never loads the Amadeus client.
    from .live import AmadeusHotelClient

    return AmadeusHotelClient(client_id, client_secret)


def _amadeus_credentials() -> tuple[str, str]:
    hostname = os.environ.get("AMADEUS_HOSTNAME", "").strip().lower()
    client_id = os.environ.get("AMADEUS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("AMADEUS_CLIENT_SECRET", "").strip()
    if hostname in {"production", "prod", "api.amadeus.com"}:
        raise HotelProviderError("refusing production Amadeus host")
    if hostname != "test" or not client_id or not client_secret:
        raise HotelProviderError(
            "Amadeus live hotel booking requires AMADEUS_CLIENT_ID, "
            "AMADEUS_CLIENT_SECRET, and AMADEUS_HOSTNAME=test"
        )
    return client_id, client_secret


def _accept(provider: object, raw: object, segment_id: str) -> HotelBookingResult:
    if not isinstance(raw, dict):
        raise HotelProviderError("hotel provider returned an invalid result")
    status = raw.get("status")
    if status not in {"booked", "failed", "needs_user"}:
        raise HotelProviderError("hotel provider returned an unknown status")
    if status != "booked":
        error = raw.get("error")
        if not isinstance(error, str) or not error.strip():
            error = "hotel booking failed" if status == "failed" else "hotel booking needs user input"
        return _result(segment_id, status, error=error)

    code = raw.get("confirmationCode")
    price = raw.get("price")
    if not isinstance(code, str) or not code:
        raise HotelProviderError("booked hotel is missing a confirmation code")
    if getattr(provider, "name", "") == "sandbox" and _SANDBOX_CODE.fullmatch(code) is None:
        raise HotelProviderError("sandbox confirmation code must start with SANDBOX-")
    if not _valid_price(price):
        raise HotelProviderError("booked hotel is missing a price")
    return _result(segment_id, "booked", confirmation_code=code, price=price, error=None)


def _valid_price(price: object) -> bool:
    if not isinstance(price, dict):
        return False
    amount = price.get("amount")
    currency = price.get("currency")
    if not isinstance(amount, str) or _AMOUNT.fullmatch(amount) is None:
        return False
    if not isinstance(currency, str) or not currency.isalpha() or currency != currency.upper() or len(currency) != 3:
        return False
    return True


def _result(
    segment_id: str | None,
    status: str,
    confirmation_code: str | None = None,
    price: HotelPrice | None = None,
    error: str | None = None,
) -> HotelBookingResult:
    return {
        "segmentId": segment_id,
        "kind": "hotel",
        "status": status,
        "confirmationCode": confirmation_code,
        "price": price,
        "error": error,
    }
