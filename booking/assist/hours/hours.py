"""Check one stop against opening hours.

Sandbox only. The caller supplies the segment window and the hours. This
module does not read the wall clock, open the network, or call AWS. It does
not book, replan, or change the stop. The master agent calls ``check_hours``
after a replan moves a stop.

Weekday is Monday=0 through Sunday=6, taken from the start timestamp's own
calendar date. The clock is the time written on each ISO timestamp. Offsets
are not converted to UTC or to the machine timezone. Hours are half-open
``[open, close)``: the start may equal ``open``, and touching ``close`` is
not inside hours.
"""

from __future__ import annotations

import json
from datetime import datetime

_FIELDS = ("segmentId", "start", "end", "open", "close", "closedWeekdays")
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_MISSING = "missing fields"


def check_hours(*args, **kwargs) -> dict:
    """Return whether one stop sits inside opening hours. Never raises.

    Call with ``segmentId``, ``start``, ``end``, ``open``, ``close``, and
    ``closedWeekdays``, or with one object of those fields. ``start`` and
    ``end`` are ISO-8601 timestamps. ``open`` and ``close`` are ``HH:MM``.
    ``closedWeekdays`` is a list of ints, Monday=0.
    """
    try:
        return _evaluate(_bind(args, kwargs))
    except Exception:
        return _result("", False, _MISSING)


def _bind(args, kwargs) -> dict:
    payload: dict = {}
    if len(args) == 1 and not any(key in kwargs for key in _FIELDS):
        return _from_value(args[0])
    if len(args) == 1:
        payload = _from_value(args[0])
    elif len(args) > 1:
        payload = {key: value for key, value in zip(_FIELDS, args)}
    elif not any(key in kwargs for key in _FIELDS) and kwargs:
        return _from_value(kwargs)
    for key in _FIELDS:
        if key in kwargs:
            payload[key] = kwargs[key]
    return payload


def _from_value(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}
    source = _unwrap(value)
    return {key: source[key] for key in _FIELDS if key in source}


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _FIELDS):
        return nested
    return payload


def _evaluate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return _result("", False, _MISSING)
    segment_id = _segment_id(payload.get("segmentId"))
    shown = segment_id or ""
    if segment_id is None or any(key not in payload for key in _FIELDS):
        return _result(shown, False, _MISSING)

    start = _parse_instant(payload.get("start"))
    end = _parse_instant(payload.get("end"))
    open_clock = _parse_hhmm(payload.get("open"))
    close_clock = _parse_hhmm(payload.get("close"))
    closed = _weekdays(payload.get("closedWeekdays"))
    if (
        start is None
        or end is None
        or open_clock is None
        or close_clock is None
        or closed is None
        or open_clock >= close_clock
    ):
        return _result(shown, False, _MISSING)

    weekday = start.weekday()
    if weekday in closed:
        return _result(shown, False, f"closed on {_WEEKDAYS[weekday]}")

    start_clock = _clock(start)
    end_clock = _clock(end)
    if end_clock <= start_clock:
        return _result(shown, False, "end is not after start")
    if start_clock < open_clock:
        return _result(shown, False, "starts before opening")
    if start_clock >= close_clock:
        return _result(
            shown,
            False,
            "touches closing time" if start_clock == close_clock else "starts at or after closing",
        )
    if end_clock > close_clock:
        return _result(shown, False, "ends after closing")
    if end_clock == close_clock:
        return _result(shown, False, "touches closing time")
    return _result(shown, True, "within opening hours")


def _result(segment_id: str, ok: bool, reason: str) -> dict:
    return {"segmentId": segment_id, "ok": ok, "reason": reason}


def _segment_id(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text


def _parse_instant(value) -> datetime | None:
    """Parse an ISO timestamp and keep the clock written on it.

    Aware values stay on their offset. Naive values stay naive. Nothing is
    converted with the machine timezone.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if "T" not in text and " " not in text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _clock(value: datetime) -> tuple[int, int, int, int]:
    return (value.hour, value.minute, value.second, value.microsecond)


def _parse_hhmm(value) -> tuple[int, int, int, int] | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    parts = text.split(":")
    if len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if hour > 23 or minute > 59 or hour < 0 or minute < 0:
        return None
    return (hour, minute, 0, 0)


def _weekdays(value) -> set[int] | None:
    if not isinstance(value, list):
        return None
    days: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            return None
        if item < 0 or item > 6:
            return None
        days.add(item)
    return days
