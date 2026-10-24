"""Ask a hotel desk to hold bags when the traveler arrives before check-in.

Sandbox only: no network and no AWS. The master agent calls ``luggage_drop``
on the Amazon Bedrock AgentCore runtime when a flight lands before hotel
check-in. This module does not run that loop, does not book the hotel, and
does not read the wall clock. A partial input returns a result and does not
raise.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

REASON_NO_ARRIVE = "arriveAt is missing"
REASON_NO_CHECKIN = "checkInAt is missing"
REASON_BAD_ARRIVE = "arriveAt is not an ISO-8601 timestamp"
REASON_BAD_CHECKIN = "checkInAt is not an ISO-8601 timestamp"
REASON_NO_NAME = "travelerName is missing"
REASON_UNREADABLE = "luggage_drop could not read the input"

_ENVELOPE_KEYS = (
    "hotelSegmentId",
    "hotel_segment_id",
    "travelerName",
    "traveler_name",
    "arriveAt",
    "arrive_at",
    "checkInAt",
    "check_in_at",
)


def luggage_drop(
    hotelSegmentId=None,
    travelerName=None,
    arriveAt=None,
    checkInAt=None,
) -> dict:
    """Decide whether the hotel desk should hold bags. Never raises.

    ``hotelSegmentId`` may be the id, or one object with ``hotelSegmentId``,
    ``travelerName``, ``arriveAt``, and ``checkInAt``. ``arriveAt`` and
    ``checkInAt`` are ISO-8601 timestamps. An arrival before check-in asks
    the desk to hold bags. An arrival at or after check-in does not.
    """
    try:
        hotel_segment_id, traveler_name, arrive_at, check_in_at = _normalize(
            hotelSegmentId, travelerName, arriveAt, checkInAt
        )
        return _decide(hotel_segment_id, traveler_name, arrive_at, check_in_at)
    except Exception:
        return _result("", "failed", "", REASON_UNREADABLE)


def _normalize(hotelSegmentId, travelerName, arriveAt, checkInAt):
    if (
        isinstance(hotelSegmentId, str)
        and travelerName is None
        and arriveAt is None
        and checkInAt is None
    ):
        try:
            loaded = json.loads(hotelSegmentId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            hotelSegmentId = loaded
    if (
        isinstance(hotelSegmentId, dict)
        and travelerName is None
        and arriveAt is None
        and checkInAt is None
    ):
        source = hotelSegmentId
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        if isinstance(source, dict):
            return (
                source.get("hotelSegmentId", source.get("hotel_segment_id")),
                source.get("travelerName", source.get("traveler_name")),
                source.get("arriveAt", source.get("arrive_at")),
                source.get("checkInAt", source.get("check_in_at")),
            )
    return hotelSegmentId, travelerName, arriveAt, checkInAt


def _decide(hotel_segment_id, traveler_name, arrive_at, check_in_at) -> dict:
    echoed_id = hotel_segment_id.strip() if isinstance(hotel_segment_id, str) else ""
    name = traveler_name.strip() if isinstance(traveler_name, str) else ""

    arrive_state, arrive_dt, _arrive_text = _read_time(arrive_at)
    check_state, check_dt, check_text = _read_time(check_in_at)

    if arrive_state == "missing" and check_state == "missing":
        return _result(echoed_id, "failed", "", "arriveAt and checkInAt are missing")
    if arrive_state == "missing":
        return _result(echoed_id, "failed", "", REASON_NO_ARRIVE)
    if check_state == "missing":
        return _result(echoed_id, "failed", "", REASON_NO_CHECKIN)
    if arrive_state != "ok" or arrive_dt is None:
        return _result(echoed_id, "failed", "", REASON_BAD_ARRIVE)
    if check_state != "ok" or check_dt is None:
        return _result(echoed_id, "failed", "", REASON_BAD_CHECKIN)

    if arrive_dt < check_dt:
        if not name:
            return _result(echoed_id, "failed", "", REASON_NO_NAME)
        note = f"Desk: please hold bags for {name} until {check_text}."
        return _result(echoed_id, "drop_requested", note, None)
    return _result(echoed_id, "not_needed", "", None)


def _read_time(value):
    if value is None:
        return "missing", None, ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "missing", None, ""
        parsed = _parse_instant(text)
        if parsed is None:
            return "bad", None, text
        return "ok", parsed, text
    if isinstance(value, datetime):
        parsed = _parse_instant(value)
        if parsed is None:
            return "bad", None, ""
        return "ok", parsed, _format_instant(parsed)
    return "bad", None, ""


def _parse_instant(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_instant(parsed: datetime) -> str:
    utc = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return utc.isoformat().replace("+00:00", "Z")


def _result(hotel_segment_id: str, status: str, desk_note: str, reason) -> dict:
    return {
        "hotelSegmentId": hotel_segment_id,
        "status": status,
        "deskNote": desk_note,
        "reason": reason,
    }
