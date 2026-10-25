"""Hold a dinner table when the traveler will miss the reservation.

Sandbox only: the caller supplies both clocks. This module does not call
OpenTable, open the network, or call AWS. It does not read the wall clock.
The master agent calls ``hold_table`` on the Amazon Bedrock AgentCore runtime
when the traveler is late to a meal so the table is held. This module does
not run that loop.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

HOLD_MINUTES = 15

STATUS_ON_TIME = "on_time"
STATUS_HELD = "held"
STATUS_FAILED = "failed"

REASON_ON_TIME = "arrival is at or before the reservation"
REASON_HELD = "traveler is late; table held until 15 minutes after arrival"
REASON_MISSING = "reservationAt or arriveAt is missing"
REASON_UNREADABLE = "reservationAt or arriveAt is not an ISO timestamp"
REASON_FAILED = "hold_table failed"

_FIELDS = ("segmentId", "venue", "reservationAt", "arriveAt", "partySize")


def hold_table(
    segmentId=None,
    venue=None,
    reservationAt=None,
    arriveAt=None,
    partySize=None,
) -> dict:
    """Return ``segmentId``, ``status``, ``heldUntil``, and ``reason``. Never raises.

    ``segmentId`` may be the id, or one object with ``segmentId``, ``venue``,
    ``reservationAt``, ``arriveAt``, and ``partySize``. ``status`` is
    ``on_time`` when ``arriveAt`` is at or before ``reservationAt``, and
    ``heldUntil`` is that ``reservationAt`` string. ``status`` is ``held``
    when arrival is later, and ``heldUntil`` is ``arriveAt`` plus 15 minutes.
    A missing clock is ``failed``.
    """
    try:
        data = _normalize(segmentId, venue, reservationAt, arriveAt, partySize)
        return _decide(data)
    except Exception:
        return _result(_safe_segment_id(segmentId), STATUS_FAILED, None, REASON_FAILED)


def _normalize(segmentId, venue, reservationAt, arriveAt, partySize) -> dict:
    if venue is None and reservationAt is None and arriveAt is None and partySize is None:
        if isinstance(segmentId, dict):
            return _unwrap(segmentId)
        if isinstance(segmentId, str):
            loaded = _load_json(segmentId)
            if isinstance(loaded, dict):
                return _unwrap(loaded)
            return {"segmentId": segmentId}
        return {}
    return {
        "segmentId": segmentId,
        "venue": venue,
        "reservationAt": reservationAt,
        "arriveAt": arriveAt,
        "partySize": partySize,
    }


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _FIELDS):
        return nested
    return payload


def _decide(data: dict) -> dict:
    if not isinstance(data, dict):
        return _result("", STATUS_FAILED, None, REASON_MISSING)
    segment_id = _text(data.get("segmentId"))
    reservation_raw = data.get("reservationAt")
    arrive_raw = data.get("arriveAt")
    if _blank(reservation_raw) or _blank(arrive_raw):
        return _result(segment_id, STATUS_FAILED, None, REASON_MISSING)

    reservation = _instant(reservation_raw)
    arrive = _instant(arrive_raw)
    if reservation is None or arrive is None:
        return _result(segment_id, STATUS_FAILED, None, REASON_UNREADABLE)

    if arrive <= reservation:
        return _result(
            segment_id,
            STATUS_ON_TIME,
            _echo_time(reservation_raw, reservation),
            REASON_ON_TIME,
        )

    held_until = _format_utc(arrive + timedelta(minutes=HOLD_MINUTES))
    return _result(segment_id, STATUS_HELD, held_until, REASON_HELD)


def _echo_time(raw, instant: datetime) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _format_utc(instant)


def _blank(value) -> bool:
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
    if not text or "T" not in text.upper():
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _load_json(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _safe_segment_id(segmentId) -> str:
    try:
        if isinstance(segmentId, dict):
            return _text(_unwrap(segmentId).get("segmentId"))
        if isinstance(segmentId, str):
            text = segmentId.strip()
            if text.startswith("{"):
                loaded = _load_json(text)
                if isinstance(loaded, dict):
                    return _text(_unwrap(loaded).get("segmentId"))
            return text
    except Exception:
        return ""
    return ""


def _result(segment_id: str, status: str, held_until, reason: str) -> dict:
    return {
        "segmentId": segment_id if isinstance(segment_id, str) else "",
        "status": status,
        "heldUntil": held_until,
        "reason": reason if isinstance(reason, str) else REASON_FAILED,
    }
