"""Decide whether two flight segments leave enough time to connect.

Sandbox only. The caller supplies both clocks and both airports. This module
does not read the wall clock, call an airline API, open the network, or call
AWS. It does not change a plan. The master agent is wired by a later
integrator. This module does not run that loop.

``gapMinutes`` is ``departAt - arriveAt`` in whole minutes. A partial minute
does not count. An international connection needs 90 minutes. A domestic
connection needs 45. A partial input returns a result and does not raise.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

INTERNATIONAL_MINIMUM_MINUTES = 90
DOMESTIC_MINIMUM_MINUTES = 45

REASON_ENOUGH = "enough"
REASON_SHORT = "short"
REASON_INVERTED = "inverted"
REASON_AIRPORT_CHANGE = "airport_change"
REASON_INVALID = "invalid_input"

ACTION_NONE = "none"
ACTION_REPLAN = "replan"
ACTION_NEEDS_USER = "needs_user"

_FIELDS = ("inbound", "outbound", "international")
_MINUTE_MICROSECONDS = 60 * 1_000_000


def check_layover(inbound=None, outbound=None, international=None) -> dict:
    """Return whether the outbound flight can follow the inbound flight.

    Call with ``inbound``, ``outbound``, and ``international``, or with one
    object of those fields. ``inbound`` carries ``segmentId``, ``arriveAt``,
    and ``airport``. ``outbound`` carries ``segmentId``, ``departAt``, and
    ``airport``. ``arriveAt`` and ``departAt`` are ISO-8601 instants.
    ``international`` is a boolean.

    Same airport and a gap at least the minimum: ``ok`` true, ``action``
    ``none``, ``shortfallMinutes`` 0. Same airport and a shorter non-negative
    gap: ``ok`` false, ``action`` ``replan``, ``shortfallMinutes`` is
    ``minimumMinutes - gapMinutes``. A departure before arrival is inverted:
    ``ok`` false, ``action`` ``replan``, ``reason`` ``inverted``. Different
    airports: ``ok`` false, ``action`` ``needs_user``, ``reason``
    ``airport_change``, and the gap is still reported. Never raises. Does not
    change a plan.
    """
    try:
        bare_payload = _is_payload(inbound) and outbound is None and international is None
        data = _load(inbound) if bare_payload else {
            "inbound": inbound,
            "outbound": outbound,
            "international": international,
        }
        if not isinstance(data, dict):
            return _invalid()
        return _decide(data)
    except Exception:
        return _invalid()


def _decide(data: dict) -> dict:
    inbound = _leg(data.get("inbound"), "arriveAt", "arrive_at")
    outbound = _leg(data.get("outbound"), "departAt", "depart_at")
    international = _international(data.get("international"))
    if inbound is None or outbound is None or international is None:
        return _invalid()

    _inbound_id, arrive_at, inbound_airport = inbound
    _outbound_id, depart_at, outbound_airport = outbound
    minimum = INTERNATIONAL_MINIMUM_MINUTES if international else DOMESTIC_MINIMUM_MINUTES
    gap = _whole_minutes(arrive_at, depart_at)
    shortfall = max(0, minimum - gap)

    if inbound_airport != outbound_airport:
        return _result(False, gap, minimum, shortfall, ACTION_NEEDS_USER, REASON_AIRPORT_CHANGE)
    if gap < 0:
        return _result(False, gap, minimum, shortfall, ACTION_REPLAN, REASON_INVERTED)
    if gap >= minimum:
        return _result(True, gap, minimum, 0, ACTION_NONE, REASON_ENOUGH)
    return _result(False, gap, minimum, shortfall, ACTION_REPLAN, REASON_SHORT)


def _result(
    ok: bool,
    gap_minutes: int,
    minimum_minutes: int,
    shortfall_minutes: int,
    action: str,
    reason: str,
) -> dict:
    return {
        "ok": ok,
        "gapMinutes": gap_minutes,
        "minimumMinutes": minimum_minutes,
        "shortfallMinutes": shortfall_minutes,
        "action": action,
        "reason": reason,
    }


def _invalid() -> dict:
    return _result(False, 0, 0, 0, ACTION_NONE, REASON_INVALID)


def _leg(value, time_key: str, snake_key: str):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    segment_id = _segment_id(value.get("segmentId", value.get("segment_id")))
    instant = _instant(value.get(time_key, value.get(snake_key)))
    airport = _airport(value.get("airport"))
    if segment_id is None or instant is None or airport is None:
        return None
    return segment_id, instant, airport


def _segment_id(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text


def _airport(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    if not text:
        return None
    return text


def _international(value) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _whole_minutes(arrive_at: datetime, depart_at: datetime) -> int:
    """Signed whole minutes from arrival to departure. A partial minute is dropped."""
    delta = depart_at - arrive_at
    microseconds = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return microseconds // _MINUTE_MICROSECONDS


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "T" not in text:
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
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _FIELDS):
        return nested
    return payload
