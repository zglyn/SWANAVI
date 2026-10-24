"""Report schedule overlaps on a trip plan.

Sandbox only: the caller supplies ``now``. This module does not read the wall
clock, open the network, or call AWS. It does not book, replan, or change the
plan. The master agent calls ``check_conflicts`` after a replan.

Two segments conflict when their half-open windows ``[start, end)`` overlap.
Touching endpoints do not conflict. A segment with ``removed`` true is ignored.
A partial plan returns a result and does not raise.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

_KINDS = ("flight", "hotel", "attraction")
_LISTS = (("flights", "flight"), ("hotels", "hotel"), ("attractions", "attraction"))


def check_conflicts(*args, **kwargs) -> dict:
    """Return overlapping segment pairs. Never raises.

    Call with ``now`` and ``plan``, or with one object ``{now, plan}``.
    ``now`` is the caller-supplied ISO-8601 instant. ``plan`` has ``flights``,
    ``hotels``, and ``attractions``. Missing clocks are filled the same way
    the replan tools fill them.
    """
    try:
        _now, plan = _bind(args, kwargs)
        return {"conflicts": _conflicts(plan)}
    except Exception:
        return {"conflicts": []}


def _bind(args, kwargs):
    now_set = "now" in kwargs
    plan_set = "plan" in kwargs
    now = kwargs.get("now") if now_set else None
    plan = kwargs.get("plan") if plan_set else None

    if len(args) == 1 and not now_set and not plan_set:
        return _from_value(args[0])
    if len(args) >= 1 and not now_set:
        now = args[0]
        now_set = True
    if len(args) >= 2 and not plan_set:
        plan = args[1]
        plan_set = True
    if not args and not now_set and not plan_set and kwargs:
        return _from_value(kwargs)
    if len(args) == 1 and not plan_set:
        parsed_now, parsed_plan = _from_value(args[0])
        if not now_set:
            now = parsed_now
        plan = parsed_plan
    return now, plan


def _from_value(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None, None
    if not isinstance(value, dict):
        return None, None
    source = _unwrap(value)
    now = source.get("now")
    if "plan" in source:
        plan = source.get("plan")
        return now, plan if isinstance(plan, dict) else None
    if _looks_like_plan(source):
        return now, source
    return now, None


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and "plan" not in payload and "now" not in payload and not _looks_like_plan(payload):
        return nested
    return payload


def _looks_like_plan(value: dict) -> bool:
    return any(key in value for key in ("flights", "hotels", "attractions"))


def _conflicts(plan) -> list:
    if not isinstance(plan, dict):
        return []
    located = []
    for list_key, list_kind in _LISTS:
        items = plan.get(list_key)
        if not isinstance(items, list):
            continue
        for segment in items:
            if not isinstance(segment, dict) or segment.get("removed") is True:
                continue
            start, end = _window(segment, _kind(segment, list_kind))
            if start is None or end is None or end <= start:
                continue
            located.append((_segment_id(segment), start, end))

    conflicts = []
    for index, left in enumerate(located):
        left_id, left_start, left_end = left
        for right_id, right_start, right_end in located[index + 1 :]:
            minutes = _overlap_minutes(left_start, left_end, right_start, right_end)
            if minutes is None:
                continue
            conflicts.append(
                {
                    "segmentA": left_id,
                    "segmentB": right_id,
                    "overlapMinutes": minutes,
                }
            )
    return conflicts


def _window(segment: dict, kind: str) -> tuple[datetime | None, datetime | None]:
    start = _explicit_instant(segment.get("start"))
    end = _explicit_instant(segment.get("end"))
    if start is None:
        start = _derived_start(segment, kind)
    if end is None:
        end = _derived_end(segment, kind, start)
    if start is not None:
        start = start.astimezone(timezone.utc)
    if end is not None:
        end = end.astimezone(timezone.utc)
    return start, end


def _derived_start(segment: dict, kind: str) -> datetime | None:
    if kind == "flight":
        return _on_clock(segment.get("departDate"), 9, 0)
    if kind == "hotel":
        return _on_clock(segment.get("checkIn"), 15, 0)
    if kind == "attraction":
        return _attraction_start(segment)
    return None


def _derived_end(segment: dict, kind: str, start: datetime | None) -> datetime | None:
    if kind == "flight":
        return None if start is None else start + timedelta(hours=3)
    if kind == "hotel":
        return _on_clock(segment.get("checkOut"), 11, 0)
    if kind == "attraction":
        return None if start is None else start + timedelta(hours=2)
    return None


def _attraction_start(segment: dict) -> datetime | None:
    """``date`` plus ``time`` when ``time`` is set, otherwise ``date`` at 10:00 UTC.

    A ``date`` that already carries a time is that instant when ``time`` is absent.
    """
    clock = _parse_clock(segment.get("time"))
    date_value = segment.get("date")
    if clock is None:
        if isinstance(date_value, str) and "T" in date_value:
            return _instant(date_value)
        return _on_clock(date_value, 10, 0)
    day = _calendar_day(date_value)
    if day is None:
        return None
    hour, minute, second = clock
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def _calendar_day(value) -> datetime | None:
    day = _parse_date(value)
    if day is not None:
        return day
    instant = _instant(value)
    if instant is None:
        return None
    return instant.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _on_clock(value, hour: int, minute: int) -> datetime | None:
    if isinstance(value, str) and "T" in value:
        return _instant(value)
    day = _parse_date(value)
    if day is None:
        return _instant(value)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _explicit_instant(value) -> datetime | None:
    if isinstance(value, str) and _date_only(value):
        return None
    return _instant(value)


def _overlap_minutes(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime):
    """Minutes in the intersection of two ``[start, end)`` windows, or None."""
    latest_start = max(start_a, start_b)
    earliest_end = min(end_a, end_b)
    if latest_start >= earliest_end:
        return None
    minutes = (earliest_end - latest_start).total_seconds() / 60.0
    if minutes <= 0:
        return None
    nearest = round(minutes)
    if abs(minutes - nearest) < 1e-6:
        return int(nearest)
    return minutes


def _kind(segment: dict, list_kind: str) -> str:
    raw = segment.get("kind")
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in _KINDS:
            return text
    return list_kind


def _segment_id(segment: dict) -> str:
    raw = segment.get("segmentId")
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if _date_only(text):
        return _parse_date(text)
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _date_only(text):
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _date_only(value) -> bool:
    return isinstance(value, str) and len(value.strip()) == 10 and value.strip()[4] == "-" and value.strip()[7] == "-"


def _parse_clock(value) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return None
    if hour > 23 or minute > 59 or second > 59 or min(hour, minute, second) < 0:
        return None
    return hour, minute, second
