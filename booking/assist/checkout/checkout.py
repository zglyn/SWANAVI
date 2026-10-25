"""Decide whether a hotel room needs a late checkout on departure morning.

Sandbox only: no network and no AWS. The master calls ``late_checkout`` on
the Amazon Bedrock AgentCore runtime on departure morning so the room is held
when the flight is late in the day. This module does not run that loop and
does not contact the hotel. A partial input returns a result and does not raise.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

STATUS_REQUESTED = "requested"
STATUS_NOT_NEEDED = "not_needed"
STATUS_FAILED = "failed"

REASON_MISSING_TIMES = "checkoutAt or departAt is missing"
REASON_BAD_TIMES = "checkoutAt or departAt is not an ISO timestamp"
REASON_UNREADABLE = "late_checkout could not read the input"

_HOLD = timedelta(hours=2)
_ENVELOPE_KEYS = (
    "hotelSegmentId",
    "hotel_segment_id",
    "checkoutAt",
    "checkout_at",
    "departAt",
    "depart_at",
    "travelerName",
    "traveler_name",
)


def late_checkout(
    hotelSegmentId=None,
    checkoutAt=None,
    departAt=None,
    travelerName=None,
) -> dict:
    """Return a late-checkout decision for one hotel segment.

    ``hotelSegmentId`` may be the id, or one object with ``hotelSegmentId``,
    ``checkoutAt``, ``departAt``, and ``travelerName``. When ``departAt`` is
    more than 2 hours after ``checkoutAt``, ``status`` is ``requested`` and
    ``until`` is ``checkoutAt`` plus 2 hours. The reason names the traveler.
    When ``departAt`` is within 2 hours after checkout or before it, ``status``
    is ``not_needed``. Missing times return ``failed``. Never raises.
    """
    try:
        bare_payload = (
            _is_payload(hotelSegmentId)
            and checkoutAt is None
            and departAt is None
            and travelerName is None
        )
        if bare_payload:
            data = _load(hotelSegmentId)
            if not isinstance(data, dict):
                return _result("", STATUS_FAILED, None, REASON_UNREADABLE)
        else:
            data = {
                "hotelSegmentId": hotelSegmentId,
                "checkoutAt": checkoutAt,
                "departAt": departAt,
                "travelerName": travelerName,
            }
        return _decide(data)
    except Exception:
        return _result("", STATUS_FAILED, None, REASON_UNREADABLE)


def _is_payload(value) -> bool:
    return isinstance(value, (dict, str))


def _load(payload):
    if isinstance(payload, str):
        loaded = json.loads(payload)
        if not isinstance(loaded, dict):
            return None
        payload = loaded
    if not isinstance(payload, dict):
        return None
    return _unwrap(payload)


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _ENVELOPE_KEYS):
        return nested
    return payload


def _decide(data: dict) -> dict:
    segment_id = _text(_field(data, "hotelSegmentId", "hotel_segment_id"))
    checkout_raw = _field(data, "checkoutAt", "checkout_at")
    depart_raw = _field(data, "departAt", "depart_at")
    traveler = _text(_field(data, "travelerName", "traveler_name"))

    checkout_state, checkout_at = _classify(checkout_raw)
    depart_state, depart_at = _classify(depart_raw)
    if checkout_state == "missing" or depart_state == "missing":
        return _result(segment_id, STATUS_FAILED, None, REASON_MISSING_TIMES)
    if checkout_at is None or depart_at is None:
        return _result(segment_id, STATUS_FAILED, None, REASON_BAD_TIMES)

    if depart_at - checkout_at > _HOLD:
        return _result(
            segment_id,
            STATUS_REQUESTED,
            _format_until(checkout_raw, checkout_at + _HOLD),
            _requested_reason(traveler),
        )
    return _result(segment_id, STATUS_NOT_NEEDED, None, _not_needed_reason(traveler))


def _field(data: dict, *keys):
    for key in keys:
        if key in data:
            return data[key]
    return None


def _classify(value) -> tuple[str, datetime | None]:
    if value is None:
        return "missing", None
    if isinstance(value, str):
        text = value.strip()
        if not text or _date_only(text):
            return "missing", None
        parsed = _instant(text)
        if parsed is None:
            return "bad", None
        return "ok", parsed
    if isinstance(value, datetime):
        parsed = _instant(value)
        if parsed is None:
            return "bad", None
        return "ok", parsed
    return "bad", None


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _date_only(value: str) -> bool:
    text = value.strip()
    return len(text) == 10 and text[4] == "-" and text[7] == "-"


def _format_until(original, held: datetime) -> str:
    if isinstance(original, str):
        text = original.strip()
        if text.endswith(("Z", "z")):
            return _format_z(held)
        if held.tzinfo is not None:
            timespec = "microseconds" if held.microsecond else "seconds"
            return held.isoformat(timespec=timespec)
    return _format_z(held)


def _format_z(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        return value.strftime("%Y-%m-%dT%H:%M:%S.%f").rstrip("0") + "Z"
    return value.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _requested_reason(traveler: str) -> str:
    who = traveler if traveler else "The traveler"
    return (
        f"{who}'s flight departs more than 2 hours after checkout, "
        "so the room is held for 2 extra hours."
    )


def _not_needed_reason(traveler: str) -> str:
    who = traveler if traveler else "The traveler"
    return (
        f"{who}'s flight is within 2 hours after checkout or before it, "
        "so late checkout is not needed."
    )


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _result(hotel_segment_id: str, status: str, until, reason: str) -> dict:
    return {
        "hotelSegmentId": hotel_segment_id,
        "status": status,
        "until": until,
        "reason": reason,
    }
