"""Replan the rest of a day when one segment is cancelled.

Sandbox only: no network, no AWS, and no wall-clock read. The caller passes
``now``. This module does not run the master agent's loop, book a segment,
or check email.

The disrupted segment is marked ``removed``. Later segments that start on
that same UTC day move earlier by the cancelled segment's duration
(``end - start``). A segment whose start is already before ``now`` stays
where it is. A partial plan returns a result and does not raise.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

NOTE_NO_SEGMENT_ID = "disruption has no segmentId"
NOTE_BAD_EVENT = "disruption event is not cancelled"
NOTE_UNREADABLE_NOW = "now is not an ISO-8601 timestamp, so later segments were left in place"
NOTE_ALREADY_REMOVED = "segment {segment_id} is already removed"
NOTE_NOT_FOUND = "segment {segment_id} was not found on the plan"
NOTE_REMOVED = "marked {segment_id} removed"
NOTE_NO_DURATION = "segment {segment_id} has no positive duration, so later segments were left in place"
NOTE_SHIFTED = "shifted {segment_id} earlier by {minutes} minutes"
NOTE_STARTED = "left {segment_id} in place because it already started before now"
NOTE_NO_START = "left {segment_id} in place because its start could not be read"

_LISTS = (
    ("flights", "flight"),
    ("hotels", "hotel"),
    ("attractions", "attraction"),
)
_KINDS = frozenset(kind for _key, kind in _LISTS)
_ENVELOPE_KEYS = ("tripId", "trip_id", "now", "plan", "disruption")


def replan_cancel(tripId=None, now=None, plan=None, disruption=None) -> dict:
    """Return the cancelled segment, whether the plan changed, and the plan.

    ``tripId`` may be the id, or one object with ``tripId``, ``now``, ``plan``,
    and ``disruption``. Never raises.
    """
    try:
        _trip_id, now, plan, disruption = _normalize(tripId, now, plan, disruption)
        return _replan(now, plan, disruption)
    except Exception:
        return _result("", False, {}, ["replan_cancel could not read the input"])


def _normalize(tripId, now, plan, disruption):
    if isinstance(tripId, str) and now is None and plan is None and disruption is None:
        try:
            loaded = json.loads(tripId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            tripId = loaded
    if isinstance(tripId, dict) and now is None and plan is None and disruption is None:
        source = tripId
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        if isinstance(source, dict) and any(key in source for key in _ENVELOPE_KEYS):
            return (
                source.get("tripId", source.get("trip_id")),
                source.get("now"),
                source.get("plan"),
                source.get("disruption"),
            )
    return tripId, now, plan, disruption


def _replan(now, plan, disruption) -> dict:
    plan_out = copy.deepcopy(plan) if isinstance(plan, dict) else {}
    if not isinstance(disruption, dict):
        return _result("", False, plan_out, [NOTE_NO_SEGMENT_ID])

    segment_id = _segment_id(disruption.get("segmentId"))
    if not segment_id:
        return _result("", False, plan_out, [NOTE_NO_SEGMENT_ID])

    event = disruption.get("event")
    if event not in (None, "", "cancelled"):
        return _result(segment_id, False, plan_out, [NOTE_BAD_EVENT])

    matches = _matches(plan_out, segment_id)
    if not matches:
        return _result(segment_id, False, plan_out, [NOTE_NOT_FOUND.format(segment_id=segment_id)])

    if all(item["segment"].get("removed") is True for item in matches):
        return _result(segment_id, False, plan_out, [NOTE_ALREADY_REMOVED.format(segment_id=segment_id)])

    for item in matches:
        item["segment"]["removed"] = True

    notes = [NOTE_REMOVED.format(segment_id=segment_id)]
    cancelled = _duration_source(matches)
    start, end = (None, None) if cancelled is None else (cancelled["start"], cancelled["end"])
    duration = None if start is None or end is None or end <= start else end - start
    if duration is None:
        notes.append(NOTE_NO_DURATION.format(segment_id=segment_id))
        return _result(segment_id, True, plan_out, notes)

    now_at = _instant(now)
    if now_at is None:
        notes.append(NOTE_UNREADABLE_NOW)
        return _result(segment_id, True, plan_out, notes)

    day = start.date()
    minutes = _minutes(duration)
    later = [item for item in _located(plan_out) if _moves_with(item, start, day)]
    later.sort(key=lambda item: (item["start"], item["index"]))
    for item in later:
        other_id = _segment_id(item["segment"].get("segmentId")) or "segment"
        if item["start"] < now_at:
            notes.append(NOTE_STARTED.format(segment_id=other_id))
            continue
        _apply_shift(item["segment"], item["kind"], duration)
        notes.append(NOTE_SHIFTED.format(segment_id=other_id, minutes=minutes))

    for item in _located(plan_out):
        if item["segment"].get("removed") is True or item["start"] is not None:
            continue
        other_id = _segment_id(item["segment"].get("segmentId"))
        if other_id:
            notes.append(NOTE_NO_START.format(segment_id=other_id))

    return _result(segment_id, True, plan_out, notes)


def _moves_with(item: dict, cancelled_start: datetime, day) -> bool:
    if item["segment"].get("removed") is True:
        return False
    start = item["start"]
    if start is None:
        return False
    return start > cancelled_start and start.date() == day


def _matches(plan: dict, segment_id: str) -> list[dict]:
    return [item for item in _located(plan) if _segment_id(item["segment"].get("segmentId")) == segment_id]


def _duration_source(matches: list[dict]) -> dict | None:
    for item in matches:
        if item["start"] is not None and item["end"] is not None and item["end"] > item["start"]:
            return item
    return matches[0] if matches else None


def _located(plan: dict) -> list[dict]:
    located = []
    index = 0
    for key, list_kind in _LISTS:
        items = plan.get(key)
        if not isinstance(items, list):
            continue
        for segment in items:
            index += 1
            if not isinstance(segment, dict):
                continue
            kind = _kind(segment, list_kind)
            start, end = _window(segment, kind)
            located.append(
                {
                    "segment": segment,
                    "kind": kind,
                    "start": start,
                    "end": end,
                    "index": index,
                }
            )
    return located


def _apply_shift(segment: dict, kind: str, duration: timedelta) -> None:
    start, end = _window(segment, kind)
    if start is None or end is None:
        return
    new_start = start - duration
    new_end = end - duration
    segment["start"] = _iso(new_start)
    segment["end"] = _iso(new_end)
    if kind == "attraction":
        segment["date"] = new_start.strftime("%Y-%m-%d")
        segment["time"] = _format_clock(new_start)
    elif kind == "flight":
        segment["departDate"] = new_start.strftime("%Y-%m-%d")
    elif kind == "hotel":
        segment["checkIn"] = new_start.strftime("%Y-%m-%d")
        segment["checkOut"] = new_end.strftime("%Y-%m-%d")


def _window(segment: dict, kind: str) -> tuple[datetime | None, datetime | None]:
    start = _instant(segment.get("start"))
    end = _instant(segment.get("end"))
    if kind == "flight":
        if start is None:
            start = _default_start(segment.get("departDate"), 9, 0)
        if end is None and start is not None:
            end = start + timedelta(hours=3)
    elif kind == "hotel":
        if start is None:
            start = _default_start(segment.get("checkIn"), 15, 0)
        if end is None:
            end = _default_start(segment.get("checkOut"), 11, 0)
    elif kind == "attraction":
        if start is None:
            start = _attraction_start(segment)
        if end is None and start is not None:
            end = start + timedelta(hours=2)
    return start, end


def _attraction_start(segment: dict) -> datetime | None:
    raw_date = segment.get("date")
    if _has_clock(raw_date):
        return _instant(raw_date)
    day = _date(raw_date)
    if day is None:
        return None
    clock = _parse_clock(segment.get("time"))
    if clock is None:
        return _at(day, 10, 0)
    hour, minute, second = clock
    return _at(day, hour, minute).replace(second=second)


def _default_start(value, hour: int, minute: int) -> datetime | None:
    if _has_clock(value):
        return _instant(value)
    day = _date(value)
    if day is None:
        return None
    return _at(day, hour, minute)


def _kind(segment: dict, list_kind: str) -> str:
    raw = segment.get("kind")
    if isinstance(raw, str) and raw.strip().lower() in _KINDS:
        return raw.strip().lower()
    return list_kind


def _segment_id(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _has_clock(value) -> bool:
    return isinstance(value, str) and "T" in value


def _date(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _at(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=timezone.utc)


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return _date(text)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_clock(value) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1]
    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return None
    if hour > 23 or minute > 59 or second > 59 or hour < 0 or minute < 0 or second < 0:
        return None
    return hour, minute, second


def _format_clock(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    if utc.second or utc.microsecond:
        return utc.strftime("%H:%M:%S")
    return utc.strftime("%H:%M")


def _iso(value: datetime) -> str:
    utc = value.astimezone(timezone.utc).replace(tzinfo=None)
    text = utc.strftime("%Y-%m-%dT%H:%M:%S")
    if utc.microsecond:
        fraction = f"{utc.microsecond:06d}".rstrip("0")
        text = f"{text}.{fraction}"
    return text + "Z"


def _minutes(duration: timedelta) -> str:
    seconds = int(duration.total_seconds())
    if seconds % 60 == 0:
        return str(seconds // 60)
    whole, remainder = divmod(abs(seconds), 60)
    text = f"{whole}.{remainder:02d}".rstrip("0")
    return text if seconds >= 0 else f"-{text}"


def _result(segment_id: str, changed: bool, plan: dict, notes: list[str]) -> dict:
    return {
        "segmentId": segment_id,
        "event": "cancelled",
        "changed": changed,
        "plan": plan,
        "notes": notes,
    }
