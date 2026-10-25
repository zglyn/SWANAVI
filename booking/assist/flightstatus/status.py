"""Report whether one flight is on time, delayed, or cancelled.

Sandbox only. The master agent calls ``flight_status`` for a flight segment
on a tick, before it replans. The caller supplies ``now`` and an optional
``feed``. This function does not read the wall clock, open the network, call
AWS, or change the segment. A later integrator wires the call into the master
loop. A missing field returns a result and does not raise.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

ERROR_INVALID = "invalid_segment"
EVENT_ON_TIME = "on_time"
EVENT_DELAYED = "delayed"
EVENT_CANCELLED = "cancelled"
EVENT_NOT_FLIGHT = "not_a_flight"
ACTION_NONE = "none"
ACTION_REPLAN = "replan"
_FLIGHT = "flight"
_CALL_KEYS = ("tripId", "trip_id", "now", "segment", "feed")
_EVENTS = frozenset({EVENT_ON_TIME, EVENT_DELAYED, EVENT_CANCELLED})


def flight_status(tripId=None, now=None, segment=None, feed=None) -> dict:
    """Return the sandbox status for one segment. Never raises.

    Input is ``tripId``, ``now``, ``segment``, and an optional ``feed``.
    ``segment`` carries ``segmentId``, ``kind``, ``from``, ``to``,
    ``departAt`` or ``departDate``, and ``confirmationCode`` or null.
    An omitted feed is ``on_time`` with ``delayMinutes`` 0. ``delayed`` and
    ``cancelled`` set ``action`` to ``replan``. A delay that is not greater
    than 0 is reported as ``on_time``. A segment that is not a flight is
    ``not_a_flight``. This function does not write back onto ``segment``.
    """
    try:
        data = _payload(tripId, now, segment, feed)
        if not isinstance(data, dict):
            return _invalid()
        return _decide(data)
    except Exception:
        return _invalid()


def _decide(data: dict) -> dict:
    segment = data.get("segment")
    if not isinstance(segment, dict):
        return _invalid()

    kind = _token(segment.get("kind"))
    if kind and kind != _FLIGHT:
        return _result(
            _text(segment.get("segmentId")),
            EVENT_NOT_FLIGHT,
            0,
            ACTION_NONE,
            _departure(segment),
        )
    if kind != _FLIGHT:
        return _invalid(segment)

    if _text(data.get("tripId", data.get("trip_id"))) == "":
        return _invalid(segment)
    if _instant(data.get("now")) is None:
        return _invalid(segment)
    if _text(segment.get("segmentId")) == "":
        return _invalid(segment)
    if _text(segment.get("from")) == "" or _text(segment.get("to")) == "":
        return _invalid(segment)
    if not _confirmation_ok(segment):
        return _invalid(segment)

    depart_at = _departure(segment)
    if depart_at == "":
        return _invalid(segment)

    event, delay_minutes, invalid_feed = _feed(data.get("feed"))
    if invalid_feed:
        return _invalid(segment)

    action = ACTION_REPLAN if event in {EVENT_DELAYED, EVENT_CANCELLED} else ACTION_NONE
    return _result(_text(segment.get("segmentId")), event, delay_minutes, action, depart_at)


def _feed(feed) -> tuple[str, int | float, bool]:
    """Return ``event``, ``delayMinutes``, and whether the feed is unusable.

    ``None`` is an omitted feed. ``cancelled`` always reports 0 minutes.
    ``delayed`` keeps a positive delay and otherwise falls back to on time.
    """
    if feed is None:
        return EVENT_ON_TIME, 0, False
    if not isinstance(feed, dict):
        return EVENT_ON_TIME, 0, True

    if "event" not in feed or _blank(feed.get("event")):
        event = EVENT_ON_TIME
    else:
        event = _token(feed.get("event"))
        if event not in _EVENTS:
            return EVENT_ON_TIME, 0, True

    if event == EVENT_CANCELLED:
        return EVENT_CANCELLED, 0, False
    if event == EVENT_DELAYED:
        minutes = _minutes(feed.get("delayMinutes")) if "delayMinutes" in feed else None
        if minutes is None or minutes <= 0:
            return EVENT_ON_TIME, 0, False
        return EVENT_DELAYED, minutes, False
    return EVENT_ON_TIME, 0, False


def _invalid(segment: dict | None = None) -> dict:
    segment_id = ""
    depart_at = ""
    if isinstance(segment, dict):
        segment_id = _text(segment.get("segmentId"))
        depart_at = _departure(segment)
    return _result(segment_id, "", 0, ACTION_NONE, depart_at, ERROR_INVALID)


def _result(
    segment_id: str,
    event: str,
    delay_minutes,
    action: str,
    depart_at: str,
    error: str | None = None,
) -> dict:
    result = {
        "segmentId": segment_id,
        "event": event,
        "delayMinutes": delay_minutes,
        "action": action,
        "departAt": depart_at,
    }
    if error is not None:
        result["error"] = error
    return result


def _confirmation_ok(segment: dict) -> bool:
    if "confirmationCode" not in segment:
        return True
    code = segment.get("confirmationCode")
    return code is None or isinstance(code, str)


def _departure(segment: dict) -> str:
    for key in ("departAt", "departDate"):
        if key not in segment:
            continue
        formatted = _format_departure(segment.get(key))
        if formatted:
            return formatted
    return ""


def _format_departure(value) -> str:
    if isinstance(value, datetime):
        return _format_instant(value)
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    date_only = _date_text(text)
    if date_only:
        return date_only
    instant = _instant(text)
    if instant is None:
        return ""
    return _format_instant(instant)


def _minutes(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            amount = Decimal(text)
        except InvalidOperation:
            return None
        if not amount.is_finite():
            return None
        if amount == amount.to_integral_value():
            return int(amount)
        return float(amount)
    return None


def _payload(tripId, now, segment, feed):
    if isinstance(tripId, dict) and now is None and segment is None and feed is None:
        return _unwrap(tripId)
    if isinstance(tripId, str) and now is None and segment is None and feed is None:
        stripped = tripId.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            loaded = json.loads(stripped)
            if not isinstance(loaded, dict):
                return None
            return _unwrap(loaded)
        return {"tripId": tripId, "now": None, "segment": None, "feed": None}
    single_value = now is None and segment is None and feed is None
    if tripId is not None and single_value and not isinstance(tripId, (str, dict)):
        return None
    return {"tripId": tripId, "now": now, "segment": segment, "feed": feed}


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _CALL_KEYS):
        return nested
    return payload


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _token(value) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().lower().replace("-", " ").replace("_", " ")
    return "_".join(text.split())


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _date_text(text):
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


def _date_text(value: str) -> str:
    text = value.strip()
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return ""
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return ""
    return text


def _format_instant(value: datetime) -> str:
    utc = value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")
