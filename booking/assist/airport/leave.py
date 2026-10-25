"""Decide when to leave a hotel for a flight.

Sandbox only: no airline API, no network, and no AWS. The caller supplies
``departAt``. This module does not read the wall clock and does not run the
master agent's loop. A partial input returns a result and does not raise.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

INTERNATIONAL_BUFFER = timedelta(hours=3)
DOMESTIC_BUFFER = timedelta(hours=2)

REASON_MISSING_DEPART = "departAt is missing"
REASON_BAD_DEPART = "departAt is not a valid ISO-8601 timestamp"
REASON_BAD_INTERNATIONAL = "international is not a boolean"
REASON_BAD_CHECKOUT = "hotelCheckoutAt is not a valid ISO-8601 timestamp"
REASON_STILL_AT_HOTEL = (
    "hotel checkout is after leaveBy; the traveler would still be at the hotel when they need to be gone"
)
REASON_INTERNATIONAL = "leave 3 hours before an international departure"
REASON_DOMESTIC = "leave 2 hours before a domestic departure"
REASON_UNREADABLE = "airport_leave could not read the input"

_ENVELOPE_KEYS = (
    "flightSegmentId",
    "flight_segment_id",
    "departAt",
    "depart_at",
    "international",
    "hotelCheckoutAt",
    "hotel_checkout_at",
)


def airport_leave(
    flightSegmentId=None,
    departAt=None,
    international=None,
    hotelCheckoutAt=None,
) -> dict:
    """Return when to leave for a flight. Never raises.

    ``flightSegmentId`` may be the id, or one object with ``flightSegmentId``,
    ``departAt``, ``international``, and ``hotelCheckoutAt``. International
    flights use a 3 hour buffer. Domestic flights use 2 hours. ``leaveBy`` is
    ``departAt`` minus that buffer. ``ok`` is false when ``departAt`` is
    missing or when ``hotelCheckoutAt`` is after ``leaveBy``.
    """
    try:
        flight_segment_id, depart_at, international_flag, checkout_at = _normalize(
            flightSegmentId, departAt, international, hotelCheckoutAt
        )
        return _leave(flight_segment_id, depart_at, international_flag, checkout_at)
    except Exception:
        return _result("", "", False, REASON_UNREADABLE)


def _normalize(flightSegmentId, departAt, international, hotelCheckoutAt):
    if isinstance(flightSegmentId, str) and departAt is None and international is None and hotelCheckoutAt is None:
        try:
            loaded = json.loads(flightSegmentId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            flightSegmentId = loaded
    if isinstance(flightSegmentId, dict) and departAt is None and international is None and hotelCheckoutAt is None:
        source = flightSegmentId
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        if isinstance(source, dict):
            return (
                source.get("flightSegmentId", source.get("flight_segment_id")),
                source.get("departAt", source.get("depart_at")),
                source.get("international"),
                source.get("hotelCheckoutAt", source.get("hotel_checkout_at")),
            )
    return flightSegmentId, departAt, international, hotelCheckoutAt


def _leave(flight_segment_id, depart_at, international, hotel_checkout_at) -> dict:
    segment_id = flight_segment_id.strip() if isinstance(flight_segment_id, str) else ""

    if _missing(depart_at):
        return _result(segment_id, "", False, REASON_MISSING_DEPART)

    departs = _instant(depart_at)
    if departs is None:
        return _result(segment_id, "", False, REASON_BAD_DEPART)

    is_international = _international_flag(international)
    if is_international is None:
        return _result(segment_id, "", False, REASON_BAD_INTERNATIONAL)

    buffer = INTERNATIONAL_BUFFER if is_international else DOMESTIC_BUFFER
    leave_by = departs - buffer
    leave_by_text = _format(leave_by)
    reason = REASON_INTERNATIONAL if is_international else REASON_DOMESTIC

    if _missing(hotel_checkout_at):
        return _result(segment_id, leave_by_text, True, reason)

    checkout = _instant(hotel_checkout_at)
    if checkout is None:
        return _result(segment_id, leave_by_text, False, REASON_BAD_CHECKOUT)
    if checkout > leave_by:
        return _result(segment_id, leave_by_text, False, REASON_STILL_AT_HOTEL)
    return _result(segment_id, leave_by_text, True, reason)


def _international_flag(value) -> bool | None:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no", ""}:
            return False
    return None


def _missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "T" not in text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(flight_segment_id: str, leave_by: str, ok: bool, reason: str) -> dict:
    return {
        "flightSegmentId": flight_segment_id,
        "leaveBy": leave_by,
        "ok": ok,
        "reason": reason,
    }
