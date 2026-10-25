"""Book one attraction segment from a finished trip plan.

The AgentCore runtime invokes ``book_attraction``, which calls ``book``.
Sandbox is the default. ``ROAM_ATTRACTION_PROVIDER=live`` selects Amadeus
Tours and Activities on the test host.
"""

from __future__ import annotations

import os
import re
from datetime import date

from .errors import AttractionProviderError
from .result import booking_result

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")
PROVIDER_ENV = "ROAM_ATTRACTION_PROVIDER"


def book(segment: dict, travelers: list, trip_id: str) -> dict:
    """Book an attraction ticket.

    Returns segmentId, kind, status (`booked`, `failed`, or `needs_user`),
    confirmationCode, price, and error. Provider failures are returned as
    `status: failed` and are not raised. The default provider is the local sandbox.
    """
    segment_id = _segment_id(segment)
    try:
        problems = _problems(segment, travelers, trip_id)
        if problems:
            return booking_result(segment_id, "needs_user", error="; ".join(problems))
        result = _select_provider().book(segment, travelers, trip_id)
        return _normalize(result, segment_id)
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        return booking_result(segment_id, "failed", error=message)


def _select_provider():
    """Sandbox unless `ROAM_ATTRACTION_PROVIDER=live`."""
    mode = os.environ.get(PROVIDER_ENV, "sandbox").strip().lower() or "sandbox"
    if mode == "sandbox":
        from .sandbox import SandboxAttractionProvider

        return SandboxAttractionProvider()
    if mode == "live":
        from .live import AmadeusToursActivitiesClient

        return AmadeusToursActivitiesClient()
    raise AttractionProviderError(f"unknown attraction provider: {mode}")


def _normalize(payload: object, segment_id: str | None) -> dict:
    if not isinstance(payload, dict):
        raise AttractionProviderError("attraction provider returned an invalid result")
    status = payload.get("status")
    if status not in {"booked", "failed", "needs_user"}:
        raise AttractionProviderError("attraction provider returned an invalid status")
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
            result["error"] = "attraction booking was not completed"
        return result
    code = result["confirmationCode"]
    price = result["price"]
    if not isinstance(code, str) or not code.startswith("SANDBOX-"):
        raise AttractionProviderError("sandbox confirmation code must start with SANDBOX-")
    if not _valid_price(price):
        raise AttractionProviderError("booked attraction is missing a price")
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
    if segment.get("kind") != "attraction":
        problems.append('kind must be "attraction"')
    if not isinstance(segment.get("name"), str) or not segment["name"].strip():
        problems.append("name is required")
    if not isinstance(segment.get("city"), str) or not segment["city"].strip():
        problems.append("city is required")
    if not _valid_date(segment.get("date")):
        problems.append("date must be YYYY-MM-DD")
    if not _valid_party_size(segment.get("partySize")):
        problems.append("partySize must be a positive integer")
    if "time" in segment and segment["time"] is not None and not _valid_time(segment["time"]):
        problems.append("time must be HH:MM or null")
    return problems


def _echoed_segment_id(payload: dict, segment_id: str | None) -> str | None:
    candidate = payload.get("segmentId", segment_id)
    if isinstance(candidate, str):
        return candidate
    return segment_id


def _segment_id(segment: object) -> str | None:
    if isinstance(segment, dict) and isinstance(segment.get("segmentId"), str):
        return segment["segmentId"]
    return None


def _valid_date(value: object) -> bool:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_time(value: object) -> bool:
    if not isinstance(value, str) or _TIME.fullmatch(value) is None:
        return False
    parts = [int(part) for part in value.split(":")]
    hour, minute = parts[0], parts[1]
    second = parts[2] if len(parts) == 3 else 0
    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59


def _valid_party_size(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _valid_price(price: object) -> bool:
    if not isinstance(price, dict):
        return False
    amount = price.get("amount")
    currency = price.get("currency")
    if isinstance(amount, bool) or not isinstance(amount, str):
        return False
    if not isinstance(currency, str) or not currency.strip():
        return False
    return re.fullmatch(r"\d+\.\d{2}", amount) is not None
