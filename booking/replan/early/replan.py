"""Shift later same-day plans when a segment ends early.

Sandbox only: no network, no AWS, and no wall-clock read. The caller passes
``now``. This module does not run the master loop, book a segment, check
email, or replan a cancellation or a late segment.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

EVENT = "ended_early"

_BUCKETS = (
    ("flights", "flight"),
    ("hotels", "hotel"),
    ("attractions", "attraction"),
)
_KINDS = frozenset(kind for _bucket, kind in _BUCKETS)
_START_KEYS = ("start", "startsAt", "startAt")
_END_KEYS = ("end", "endsAt", "endAt")


def replan_early(*args, **kwargs) -> dict:
    """Return the early-finish replan. Never raises.

    Call with ``tripId``, ``now``, ``plan``, and ``disruption``, or with one
    object that carries those fields. ``now`` is an ISO-8601 timestamp.
    ``disruption`` is ``{segmentId, kind, event, deltaMinutes}`` with
    ``event`` ``ended_early``.
    """
    try:
        trip_id, now, plan, disruption = _bind(args, kwargs)
        return _replan(trip_id, now, plan, disruption)
    except Exception:
        return _result("", False, _empty_plan(), ["replan_early could not read its input"])


def idle_result(tool_input=None, note: str = "replan_early did not change the plan") -> dict:
    """Return the caller's plan unchanged. Used when the runtime tool name mismatches."""
    try:
        _trip_id, _now, plan, disruption = _bind((tool_input,), {})
        segment_id = _disruption_segment_id(disruption)
        plan_out = copy.deepcopy(plan) if isinstance(plan, dict) else _empty_plan()
        return _result(segment_id, False, plan_out, [note])
    except Exception:
        return _result("", False, _empty_plan(), [note])


def _replan(trip_id, now, plan, disruption) -> dict:
    del trip_id  # The plan keeps its own tripId. A missing id does not raise.
    segment_id = _disruption_segment_id(disruption)
    if not isinstance(plan, dict):
        return _result(segment_id, False, _empty_plan(), ["plan is missing"])

    plan_out = copy.deepcopy(plan)
    if not isinstance(disruption, dict):
        return _result(segment_id, False, plan_out, ["disruption is missing"])
    if not segment_id:
        return _result("", False, plan_out, ["disruption is missing segmentId"])

    event = _disruption_event(disruption)
    if event != EVENT:
        return _result(segment_id, False, plan_out, ["disruption event is not ended_early; plan unchanged"])

    delta_minutes = _delta_minutes(disruption)
    if delta_minutes is None:
        return _result(segment_id, False, plan_out, ["deltaMinutes is missing"])
    if delta_minutes <= 0:
        return _result(segment_id, False, plan_out, ["deltaMinutes is not positive; plan unchanged"])

    now_at = _parse_instant(now)
    if now_at is None:
        return _result(segment_id, False, plan_out, ["now is not an ISO-8601 timestamp"])

    finished, finished_kind = _find_finished(plan_out, segment_id, _disruption_kind(disruption))
    if finished is None:
        return _result(segment_id, False, plan_out, [f"segment {segment_id} is not on the plan"])

    finished_start, finished_end = _window(finished, finished_kind)
    if finished_start is None or finished_end is None or finished_end < finished_start:
        return _result(segment_id, False, plan_out, [f"kept {segment_id}; it has no schedule"])

    delta = timedelta(minutes=delta_minutes)
    notes = [f"kept {segment_id}"]
    changed = False
    for segment, kind in _iter_segments(plan_out):
        if segment is finished or _segment_id(segment) == segment_id:
            continue
        start, end = _window(segment, kind)
        if start is None or end is None or end < start:
            continue
        # Later same-day: on the UTC date the finished segment ends, at or after that end.
        if not _same_day(start, finished_end) or start < finished_end:
            continue
        label = _label(segment)
        if start < now_at:
            notes.append(f"left {label} in place; it already started before now")
            continue
        applied = min(delta, start - now_at)
        if applied <= timedelta(0):
            notes.append(f"left {label} in place; it would start before now")
            continue
        _place(segment, kind, start - applied, end - applied)
        minutes = _minute_label(applied)
        if applied < delta:
            notes.append(f"shifted {label} earlier by {minutes} minutes so it does not start before now")
        else:
            notes.append(f"shifted {label} earlier by {minutes} minutes")
        changed = True

    if not changed and len(notes) == 1:
        notes.append("no later same-day segment to shift")
    return _result(segment_id, changed, plan_out, notes)


def _bind(args, kwargs):
    trip_id = _first(kwargs, "tripId", "trip_id")
    now = kwargs.get("now")
    plan = kwargs.get("plan")
    disruption = kwargs.get("disruption")
    if len(args) == 1 and trip_id is None and now is None and plan is None and disruption is None:
        return _from_value(args[0])
    if len(args) >= 1 and trip_id is None:
        trip_id = args[0]
    if len(args) >= 2 and now is None:
        now = args[1]
    if len(args) >= 3 and plan is None:
        plan = args[2]
    if len(args) >= 4 and disruption is None:
        disruption = args[3]
    return trip_id, now, plan, disruption


def _from_value(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None, None, None, None
    if not isinstance(value, dict):
        return None, None, None, None
    source = value
    arguments = value.get("arguments")
    if isinstance(arguments, dict):
        source = arguments
    elif isinstance(value.get("input"), dict) and not _looks_like_plan(value) and "disruption" not in value:
        source = value["input"]
    trip_id = source.get("tripId", source.get("trip_id"))
    now = source.get("now")
    disruption = source.get("disruption")
    nested = source.get("plan")
    if isinstance(nested, dict):
        plan = nested
    elif _looks_like_plan(source):
        plan = source
    else:
        plan = nested if isinstance(nested, dict) else None
    return trip_id, now, plan, disruption


def _looks_like_plan(value: dict) -> bool:
    return any(key in value for key in ("flights", "hotels", "attractions"))


def _find_finished(plan: dict, segment_id: str, kind_hint: str):
    matches = [(segment, kind) for segment, kind in _iter_segments(plan) if _segment_id(segment) == segment_id]
    if not matches:
        return None, ""
    if kind_hint:
        for segment, kind in matches:
            if kind == kind_hint:
                return segment, kind
    return matches[0]


def _iter_segments(plan: dict):
    for bucket, fallback in _BUCKETS:
        items = plan.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                yield item, _kind(item, fallback)


def _window(segment: dict, kind: str) -> tuple[datetime | None, datetime | None]:
    start = _explicit(segment, _START_KEYS)
    end = _explicit(segment, _END_KEYS)
    if kind == "flight":
        if start is None:
            start = _at_clock(segment.get("departDate"), 9, 0)
        if end is None and start is not None:
            end = start + timedelta(hours=3)
        if start is None and end is not None:
            start = end - timedelta(hours=3)
    elif kind == "hotel":
        if start is None:
            start = _at_clock(segment.get("checkIn"), 15, 0)
        if end is None:
            end = _at_clock(segment.get("checkOut"), 11, 0)
    elif kind == "attraction":
        if start is None:
            start = _attraction_start(segment)
        if end is None and start is not None:
            end = start + timedelta(hours=2)
        if start is None and end is not None:
            start = end - timedelta(hours=2)
    if start is not None:
        start = start.astimezone(timezone.utc)
    if end is not None:
        end = end.astimezone(timezone.utc)
    return start, end


def _attraction_start(segment: dict) -> datetime | None:
    clock = _parse_clock(segment.get("time"))
    if clock is None:
        return _at_clock(segment.get("date"), 10, 0)
    day = _parse_date(segment.get("date"))
    if day is None:
        instant = _parse_instant(segment.get("date"))
        if instant is None:
            return None
        day = instant.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    hour, minute, second = clock
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def _place(segment: dict, kind: str, new_start: datetime, new_end: datetime) -> None:
    _set_instant(segment, _START_KEYS, "start", new_start)
    _set_instant(segment, _END_KEYS, "end", new_end)
    if kind == "attraction":
        if "date" in segment or "time" in segment:
            segment["date"] = new_start.date().isoformat()
            segment["time"] = new_start.strftime("%H:%M")
        return
    if kind == "flight":
        _set_date_field(segment, "departDate", new_start)
        return
    if kind == "hotel":
        _set_date_field(segment, "checkIn", new_start)
        _set_date_field(segment, "checkOut", new_end)


def _set_instant(segment: dict, keys: tuple[str, ...], default: str, instant: datetime) -> None:
    text = _format(instant)
    found = False
    for key in keys:
        if key in segment:
            segment[key] = text
            found = True
    if not found:
        segment[default] = text


def _set_date_field(segment: dict, key: str, instant: datetime) -> None:
    if key not in segment:
        return
    current = segment.get(key)
    new_date = instant.date().isoformat()
    if _is_date_only(current):
        if str(current).strip() != new_date:
            segment[key] = new_date
        return
    segment[key] = _format(instant)


def _explicit(segment: dict, keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        if key not in segment:
            continue
        parsed = _parse_instant(segment.get(key))
        if parsed is not None:
            return parsed
    return None


def _at_clock(value, hour: int, minute: int) -> datetime | None:
    if _is_date_only(value):
        day = _parse_date(value)
        if day is None:
            return None
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return _parse_instant(value)


def _format(value: datetime) -> str:
    utc = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _is_date_only(text):
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


def _parse_date(value) -> datetime | None:
    if not _is_date_only(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _is_date_only(value) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


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
    if hour > 23 or minute > 59 or second > 59 or hour < 0 or minute < 0 or second < 0:
        return None
    return hour, minute, second


def _same_day(start: datetime, finished_end: datetime) -> bool:
    return start.astimezone(timezone.utc).date() == finished_end.astimezone(timezone.utc).date()


def _kind(segment: dict, fallback: str) -> str:
    kind = segment.get("kind")
    if isinstance(kind, str) and kind.strip().lower() in _KINDS:
        return kind.strip().lower()
    return fallback


def _segment_id(segment: dict) -> str:
    segment_id = segment.get("segmentId")
    if isinstance(segment_id, str):
        return segment_id.strip()
    return ""


def _label(segment: dict) -> str:
    segment_id = _segment_id(segment)
    if segment_id:
        return segment_id
    return "a segment"


def _disruption_segment_id(disruption) -> str:
    if not isinstance(disruption, dict):
        return ""
    for key in ("segmentId", "segment_id"):
        segment_id = disruption.get(key)
        if isinstance(segment_id, str) and segment_id.strip():
            return segment_id.strip()
    return ""


def _disruption_kind(disruption: dict) -> str:
    kind = disruption.get("kind")
    if isinstance(kind, str) and kind.strip().lower() in _KINDS:
        return kind.strip().lower()
    return ""


def _disruption_event(disruption: dict) -> str:
    event = disruption.get("event")
    if not isinstance(event, str) or not event.strip():
        return EVENT
    return event.strip().lower()


def _delta_minutes(disruption: dict) -> float | None:
    if "deltaMinutes" in disruption:
        value = disruption.get("deltaMinutes")
    elif "delta_minutes" in disruption:
        value = disruption.get("delta_minutes")
    else:
        return None
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _minute_label(applied: timedelta) -> str:
    minutes = applied.total_seconds() / 60
    if minutes.is_integer():
        return str(int(minutes))
    return f"{minutes:g}"


def _first(mapping: dict, *keys: str):
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _empty_plan() -> dict:
    return {"flights": [], "hotels": [], "attractions": []}


def _result(segment_id: str, changed: bool, plan, notes: list) -> dict:
    if not isinstance(plan, dict):
        plan = _empty_plan()
    return {
        "segmentId": segment_id if isinstance(segment_id, str) else "",
        "event": EVENT,
        "changed": bool(changed),
        "plan": plan,
        "notes": [note for note in notes if isinstance(note, str)],
    }
