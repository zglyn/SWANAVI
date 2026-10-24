"""Book one flight segment from a finished trip plan."""

from __future__ import annotations

import os
import re
from datetime import date

from .errors import FlightProviderError
from .result import booking_result

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CABINS = {"economy", "premium_economy", "business", "first"}
PROVIDER_ENV = "ROAM_FLIGHT_PROVIDER"
_PRICE = re.compile(r"^\d+\.\d{2}$")


def book(segment: dict, travelers: list, trip_id: str) -> dict:
    """Book a flight segment.

    Returns segmentId, kind, status (`booked`, `failed`, or `needs_user`),
    confirmationCode, price, and error. Provider failures are returned as
    `status: failed` and are not raised. The default provider is the local sandbox.

    The supported product invoke path is the `book_flight` AgentCore tool,
    whose handler calls this function.
    """
    if isinstance(segment, dict):
        segment = dict(segment)
    segment_id = _segment_id(segment)
    try:
        problems = _problems(segment, travelers, trip_id)
        if problems:
            return booking_result(segment_id, "needs_user", error="; ".join(problems))
        provider = _select_provider()
        result = provider.book(segment, travelers, trip_id)
        return _normalize(result, segment_id, sandbox=provider.__class__.__name__.startswith("Sandbox"))
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        return booking_result(segment_id, "failed", error=message)


def _select_provider():
    """Sandbox unless `ROAM_FLIGHT_PROVIDER=live`."""
    mode = os.environ.get(PROVIDER_ENV, "sandbox").strip().lower() or "sandbox"
    if mode == "sandbox":
        from .sandbox import SandboxFlightProvider

        return SandboxFlightProvider()
    if mode == "live":
        from .live import LiveFlightAdapter

        return LiveFlightAdapter()
    raise FlightProviderError(f"unknown flight provider: {mode}")


def _normalize(payload: object, segment_id: str | None, *, sandbox: bool) -> dict:
    if not isinstance(payload, dict):
        raise FlightProviderError("flight provider returned an invalid result")
    status = payload.get("status")
    if status not in {"booked", "failed", "needs_user"}:
        raise FlightProviderError("flight provider returned an invalid status")
    result = booking_result(
        _echoed_segment_id(payload, segment_id),
        status,
        payload.get("confirmationCode"),
        payload.get("price"),
        payload.get("error"),
    )
    if status != "booked":
        result["confirmationCode"] = None
        result["price"] = None
        if not isinstance(result["error"], str) or not result["error"].strip():
            result["error"] = "flight booking was not completed"
        return result
    code = result["confirmationCode"]
    price = result["price"]
    if not isinstance(code, str) or not code.strip():
        raise FlightProviderError("flight booking returned no confirmation")
    if sandbox and not code.startswith("SANDBOX-"):
        raise FlightProviderError("sandbox confirmation code must start with SANDBOX-")
    if not _valid_price(price):
        raise FlightProviderError("booked flight is missing a price")
    result["confirmationCode"] = code.strip()
    result["error"] = None
    return result


def _problems(segment: object, travelers: object, trip_id: object) -> list[str]:
    problems: list[str] = []
    if not isinstance(segment, dict):
        problems.append("segment must be an object")
    if not isinstance(travelers, list):
        problems.append("travelers must be a list")
    if not isinstance(trip_id, str) or not trip_id.strip():
        problems.append("trip_id is required")
    if not isinstance(segment, dict):
        return problems
    if not isinstance(segment.get("segmentId"), str) or not segment["segmentId"].strip():
        problems.append("segmentId is required")
    if segment.get("kind") != "flight":
        problems.append('kind must be "flight"')
    origin = segment.get("from")
    destination = segment.get("to")
    if not isinstance(origin, str) or not origin.strip():
        problems.append("from is required")
    if not isinstance(destination, str) or not destination.strip():
        problems.append("to is required")
    if (
        isinstance(origin, str)
        and isinstance(destination, str)
        and origin.strip()
        and origin.strip().upper() == destination.strip().upper()
    ):
        problems.append("from and to must differ")
    depart = _valid_date(segment.get("departDate"))
    if depart is None:
        problems.append("departDate must be YYYY-MM-DD")
    if "returnDate" in segment and segment.get("returnDate") is not None:
        return_date = _valid_date(segment.get("returnDate"))
        if return_date is None:
            problems.append("returnDate must be YYYY-MM-DD or null")
        elif depart is not None and return_date < depart:
            problems.append("returnDate must be on or after departDate")
    cabin = _cabin(segment.get("cabin"))
    if cabin is None:
        problems.append("cabin must be economy, premium_economy, business, or first")
    else:
        segment["cabin"] = cabin
    traveler_ids = segment.get("travelerIds")
    if (
        not isinstance(traveler_ids, list)
        or not traveler_ids
        or not all(isinstance(item, str) and item.strip() for item in traveler_ids)
    ):
        problems.append("travelerIds must be a non-empty list of ids")
    elif len({item.strip() for item in traveler_ids}) != len(traveler_ids):
        problems.append("travelerIds must be unique")
    elif isinstance(travelers, list):
        index = _traveler_index(travelers)
        for traveler_id in traveler_ids:
            traveler = index.get(traveler_id.strip())
            if traveler is None:
                problems.append(f"traveler {traveler_id.strip()} was not provided")
            elif not _has_name(traveler):
                problems.append(f"traveler {traveler_id.strip()} needs a name")
    return problems


def _traveler_index(travelers: list) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for traveler in travelers:
        if not isinstance(traveler, dict):
            continue
        traveler_id = traveler.get("id", traveler.get("travelerId"))
        if isinstance(traveler_id, str) and traveler_id.strip():
            index[traveler_id.strip()] = traveler
    return index


def _has_name(traveler: dict) -> bool:
    name = traveler.get("name")
    if isinstance(name, str) and name.strip():
        return True
    given = traveler.get("givenName")
    family = traveler.get("familyName")
    return isinstance(given, str) and bool(given.strip()) and isinstance(family, str) and bool(family.strip())


def _cabin(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = "_".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    if key in _CABINS:
        return key
    return None


def _echoed_segment_id(payload: dict, segment_id: str | None) -> str | None:
    candidate = payload.get("segmentId", segment_id)
    if isinstance(candidate, str):
        return candidate
    return segment_id


def _segment_id(segment: object) -> str | None:
    if isinstance(segment, dict) and isinstance(segment.get("segmentId"), str):
        return segment["segmentId"]
    return None


def _valid_date(value: object) -> date | None:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _valid_price(price: object) -> bool:
    if not isinstance(price, dict):
        return False
    amount = price.get("amount")
    currency = price.get("currency")
    if isinstance(amount, bool) or not isinstance(amount, str) or _PRICE.fullmatch(amount) is None:
        return False
    return isinstance(currency, str) and bool(currency.strip())
