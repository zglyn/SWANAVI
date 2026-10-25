"""Shift the rest of a day when one segment ends late.

Sandbox only: the caller supplies ``now``. This module does not read the wall
clock, open the network, or call AWS. It keeps the finished segment and moves
later segments on that same UTC day.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

_KINDS = ("flight", "hotel", "attraction")
_LISTS = (("flights", "flight"), ("hotels", "hotel"), ("attractions", "attraction"))
_CALL_KEYS = ("tripId", "now", "plan", "disruption", "flights", "hotels", "attractions")


def replan_late(tripId=None, now=None, plan=None, disruption=None) -> dict:
    """Return the plan with later same-day segments shifted by ``deltaMinutes``.

    Never raises. A partial plan, a missing clock, or ``deltaMinutes`` that is
    not positive comes back as ``changed`` false. ``event`` is always
    ``ended_late``. The finished segment is copied unchanged.
    """
    try:
        now, plan, disruption = _normalize(tripId, now, plan, disruption)
        return _replan(now, plan, disruption)
    except Exception:
        return _fallback(plan, disruption)


def _replan(now, plan, disruption) -> dict:
    plan_copy = _plan_copy(plan)
    disruption = _as_dict(disruption)
    segment_id = _text(disruption.get("segmentId"))
    if _event(disruption) != "ended_late":
        return _result(segment_id, False, plan_copy, ["disruption event is not ended_late; plan unchanged"])

    minutes = _delta_minutes(disruption.get("deltaMinutes"))
    if minutes is None or minutes <= 0:
        return _result(segment_id, False, plan_copy, ["deltaMinutes is not positive; plan unchanged"])
    if not segment_id:
        return _result("", False, plan_copy, ["segmentId is missing; plan unchanged"])

    located = _find(plan_copy, segment_id)
    if located is None:
        return _result(segment_id, False, plan_copy, [f"segment {segment_id} is not on the plan"])

    _list_key, _index, kind, finished = located
    start, end = _window(finished, kind)
    reference_end = end or start
    if reference_end is None:
        return _result(
            segment_id,
            False,
            plan_copy,
            [f"finished segment {segment_id} has no schedule; plan unchanged"],
        )

    now_at = _instant(now)
    if now_at is None:
        return _result(segment_id, False, plan_copy, ["now is not a timestamp; plan unchanged"])

    notes = [f"kept finished segment {segment_id}"]
    changed = False
    delta = timedelta(minutes=minutes)
    minute_text = _minute_text(minutes)
    for list_kind, segment in _segments(plan_copy):
        if _text(segment.get("segmentId")) == segment_id:
            continue
        seg_start, seg_end = _window(segment, _kind(segment, list_kind))
        if seg_start is None or seg_end is None:
            continue
        if not _same_day(seg_start, reference_end) or seg_start < reference_end:
            continue
        other_id = _text(segment.get("segmentId")) or "segment"
        if seg_start < now_at:
            notes.append(f"left {other_id} in place; it already started before now")
            continue
        _shift_segment(segment, seg_start, seg_end, delta, _kind(segment, list_kind))
        notes.append(f"shifted {other_id} later by {minute_text} minutes")
        changed = True
    return _result(segment_id, changed, plan_copy, notes)


def _normalize(tripId, now, plan, disruption):
    if not (isinstance(tripId, (dict, str)) and now is None and plan is None and disruption is None):
        return now, plan, disruption
    payload = tripId
    if isinstance(payload, str):
        loaded = _load_json(payload)
        if not isinstance(loaded, dict):
            return now, plan, disruption
        payload = loaded
    source = _unwrap(payload)
    if not isinstance(source, dict) or not any(key in source for key in _CALL_KEYS):
        return now, plan, disruption
    call_plan = source.get("plan")
    owns_plan = "disruption" not in source and "now" not in source
    if not isinstance(call_plan, dict) and _looks_like_plan(source) and owns_plan:
        call_plan = source
    return source.get("now"), call_plan, source.get("disruption")


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in ("plan", "disruption", "flights", "hotels", "attractions")):
        return nested
    return payload


def _looks_like_plan(value: dict) -> bool:
    return any(key in value for key in ("flights", "hotels", "attractions"))


def _find(plan: dict, segment_id: str):
    for list_key, list_kind in _LISTS:
        items = plan.get(list_key)
        if not isinstance(items, list):
            continue
        for index, segment in enumerate(items):
            if isinstance(segment, dict) and _text(segment.get("segmentId")) == segment_id:
                return list_key, index, _kind(segment, list_kind), segment
    return None


def _segments(plan: dict):
    for list_key, list_kind in _LISTS:
        items = plan.get(list_key)
        if not isinstance(items, list):
            continue
        for segment in items:
            if isinstance(segment, dict):
                yield list_kind, segment


def _kind(segment: dict, list_kind: str) -> str:
    raw = segment.get("kind")
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in _KINDS:
            return text
    return list_kind


def _window(segment: dict, kind: str) -> tuple[datetime | None, datetime | None]:
    start = _explicit_instant(segment.get("start"))
    end = _explicit_instant(segment.get("end"))
    if start is None:
        start = _derived_start(segment, kind)
    if end is None:
        end = _derived_end(segment, kind, start)
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
        checkout = _on_clock(segment.get("checkOut"), 11, 0)
        if checkout is not None:
            return checkout
        if start is None:
            return None
        day = start.astimezone(timezone.utc) + timedelta(days=1)
        return day.replace(hour=11, minute=0, second=0, microsecond=0)
    if kind == "attraction":
        return None if start is None else start + timedelta(hours=2)
    return None


def _attraction_start(segment: dict) -> datetime | None:
    date_value = segment.get("date")
    if isinstance(date_value, str) and "T" in date_value:
        return _instant(date_value)
    day = _parse_date(date_value)
    if day is None:
        return _instant(date_value)
    clock = _parse_clock(segment.get("time"))
    if clock is None:
        return day.replace(hour=10, minute=0, second=0, microsecond=0)
    hour, minute, second = clock
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def _on_clock(value, hour: int, minute: int) -> datetime | None:
    if isinstance(value, str) and "T" in value:
        return _instant(value)
    day = _parse_date(value)
    if day is None:
        return _instant(value)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _shift_segment(segment: dict, start: datetime, end: datetime, delta: timedelta, kind: str) -> None:
    new_start = start + delta
    new_end = end + delta
    segment["start"] = _format_utc(new_start)
    segment["end"] = _format_utc(new_end)
    if kind == "attraction":
        _shift_attraction_fields(segment, new_start)
    elif kind == "flight":
        _shift_dated_field(segment, "departDate", new_start)
    elif kind == "hotel":
        _shift_dated_field(segment, "checkIn", new_start)
        _shift_dated_field(segment, "checkOut", new_end)


def _shift_attraction_fields(segment: dict, new_start: datetime) -> None:
    raw_date = segment.get("date")
    if isinstance(raw_date, str):
        if _date_only(raw_date):
            segment["date"] = new_start.astimezone(timezone.utc).date().isoformat()
        elif "T" in raw_date:
            segment["date"] = _format_utc(new_start)
    raw_time = segment.get("time")
    if isinstance(raw_time, str) and _parse_clock(raw_time) is not None:
        segment["time"] = _format_clock(new_start, raw_time)


def _shift_dated_field(segment: dict, key: str, instant: datetime) -> None:
    raw = segment.get(key)
    if not isinstance(raw, str):
        return
    if _date_only(raw):
        shifted = instant.astimezone(timezone.utc).date().isoformat()
        if shifted != raw.strip():
            segment[key] = shifted
        return
    if "T" in raw:
        segment[key] = _format_utc(instant)


def _explicit_instant(value) -> datetime | None:
    if isinstance(value, str) and _date_only(value):
        return None
    return _instant(value)


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


def _same_day(left: datetime, right: datetime) -> bool:
    return left.astimezone(timezone.utc).date() == right.astimezone(timezone.utc).date()


def _format_utc(value: datetime) -> str:
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _format_clock(value: datetime, original: str) -> str:
    value = value.astimezone(timezone.utc)
    if original.strip().count(":") >= 2:
        return value.strftime("%H:%M:%S")
    return value.strftime("%H:%M")


def _delta_minutes(value) -> float | None:
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


def _minute_text(minutes: float) -> str:
    if minutes.is_integer():
        return str(int(minutes))
    return str(minutes)


def _event(disruption: dict) -> str:
    raw = disruption.get("event", "ended_late")
    if raw is None:
        return "ended_late"
    if not isinstance(raw, str):
        return ""
    return raw.strip() or "ended_late"


def _text(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _as_dict(value) -> dict:
    if isinstance(value, str):
        loaded = _load_json(value)
        return loaded if isinstance(loaded, dict) else {}
    return value if isinstance(value, dict) else {}


def _load_json(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _plan_copy(plan) -> dict:
    if isinstance(plan, dict):
        return copy.deepcopy(plan)
    return {"flights": [], "hotels": [], "attractions": []}


def _result(segment_id: str, changed: bool, plan, notes) -> dict:
    if not isinstance(plan, dict):
        plan = {"flights": [], "hotels": [], "attractions": []}
    clean_notes = [note for note in notes if isinstance(note, str)] if isinstance(notes, list) else []
    return {
        "segmentId": segment_id if isinstance(segment_id, str) else "",
        "event": "ended_late",
        "changed": bool(changed),
        "plan": plan,
        "notes": clean_notes,
    }


def _fallback(plan, disruption) -> dict:
    segment_id = ""
    try:
        parsed = _as_dict(disruption)
        segment_id = _text(parsed.get("segmentId"))
        plan_out = _plan_copy(plan)
    except Exception:
        plan_out = {"flights": [], "hotels": [], "attractions": []}
    return _result(segment_id, False, plan_out, ["plan unchanged"])
