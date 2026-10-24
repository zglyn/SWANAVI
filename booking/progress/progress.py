"""Compare a trip plan with booking results at a caller-supplied instant.

Sandbox only: no network, no AWS, and no wall-clock read. The caller passes
``now``. This module does not run the master agent's loop.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

GRACE = timedelta(minutes=45)

ISSUE_REBOOK = "segment end is more than 45 minutes before now and the segment is not finished"
ISSUE_EMAIL = "booked segment has emailVerified false"

_ENVELOPE_KEYS = ("plan", "trip", "results", "bookings", "bookingResults", "now")


def trip_progress(plan=None, results=None, now=None) -> dict:
    """Return ``phase``, ``onTrack``, and ``updates``. Never raises.

    ``plan`` may be the trip plan, or one object with ``plan``, ``results``,
    and ``now``. ``now`` is an ISO-8601 timestamp from the caller.
    """
    try:
        plan, results, now = _normalize(plan, results, now)
        return _evaluate(plan if isinstance(plan, dict) else {}, results, now)
    except Exception:
        return _result("pre_trip", True, [])


def _normalize(plan, results, now):
    if isinstance(plan, str):
        try:
            loaded = json.loads(plan)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            plan = loaded
    if isinstance(plan, dict) and results is None and now is None:
        source = plan
        arguments = plan.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(plan.get("input"), dict) and not _looks_like_plan(plan):
            source = plan["input"]
        if isinstance(source, dict) and any(key in source for key in _ENVELOPE_KEYS):
            return (
                source.get("plan", source.get("trip")),
                source.get("results", source.get("bookings", source.get("bookingResults"))),
                source.get("now"),
            )
    return plan, results, now


def _looks_like_plan(value: dict) -> bool:
    return any(key in value for key in ("flights", "hotels", "attractions", "segments", "tripId"))


def _evaluate(plan: dict, results, now) -> dict:
    segments = _segments(plan)
    by_id = _results_by_id(results)
    now_at = _instant(now, as_end=False)
    windows = [_window(segment) for segment in segments]

    if segments and all(_done_segment(by_id.get(_segment_id(segment))) for segment in segments):
        return _result("done", True, [])

    updates = []
    for segment, (_start, end) in zip(segments, windows):
        segment_id = _segment_id(segment)
        result = by_id.get(segment_id) if segment_id else None
        kind = _kind(segment, result)
        if now_at is not None and end is not None and not _finished(result) and _overdue(end, now_at):
            updates.append(_update(segment_id, kind, ISSUE_REBOOK, "rebook"))
        if _booked(result) and result.get("emailVerified") is False:
            updates.append(_update(segment_id, kind, ISSUE_EMAIL, "verify_email"))

    on_track = not any(item["action"] == "rebook" for item in updates)
    phase = _phase(plan, segments, windows, now_at)
    return _result(phase, on_track, updates)


def _phase(plan: dict, segments: list, windows: list, now_at: datetime | None) -> str:
    if not segments or now_at is None:
        return "pre_trip"
    starts = [start for start, _end in windows if start is not None]
    if not starts:
        dates = plan.get("dates")
        if isinstance(dates, dict):
            fallback = _instant(dates.get("start"), as_end=False)
            if fallback is not None:
                starts = [fallback]
    if starts and now_at < min(starts):
        return "pre_trip"
    return "in_progress"


def _segments(plan: dict) -> list:
    grouped = []
    for key in ("flights", "hotels", "attractions"):
        items = plan.get(key)
        if isinstance(items, list):
            grouped.extend(item for item in items if isinstance(item, dict))
    if grouped:
        return grouped
    items = plan.get("segments")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _results_by_id(results) -> dict:
    if isinstance(results, dict):
        nested = results.get("results")
        results = nested if isinstance(nested, list) else []
    if not isinstance(results, list):
        return {}
    found = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        segment_id = item.get("segmentId")
        if isinstance(segment_id, str) and segment_id:
            found[segment_id] = item
    return found


def _segment_id(segment: dict) -> str:
    segment_id = segment.get("segmentId")
    if isinstance(segment_id, str):
        return segment_id
    return ""


def _kind(segment: dict, result: dict | None) -> str:
    for source in (segment, result):
        if not isinstance(source, dict):
            continue
        kind = source.get("kind")
        if isinstance(kind, str) and kind.strip():
            return kind.strip()
    if "checkIn" in segment or "checkOut" in segment:
        return "hotel"
    if "departDate" in segment or "from" in segment:
        return "flight"
    if "date" in segment:
        return "attraction"
    return ""


def _done_segment(result: dict | None) -> bool:
    return _finished(result) and _verified(result)


def _finished(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("finished") is True:
        return True
    status = result.get("status")
    return isinstance(status, str) and status.strip().lower() == "finished"


def _booked(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    status = result.get("status")
    return isinstance(status, str) and status.strip().lower() == "booked"


def _verified(result: dict | None) -> bool:
    return isinstance(result, dict) and result.get("emailVerified") is True


def _overdue(end: datetime, now_at: datetime) -> bool:
    return now_at - end > GRACE


def _window(segment: dict) -> tuple[datetime | None, datetime | None]:
    kind = _kind(segment, None)
    start = _first(segment, ("start", "startsAt", "startAt"), as_end=False)
    end = _first(segment, ("end", "endsAt", "endAt"), as_end=True)
    if start is None:
        start = _start_for(segment, kind)
    if end is None:
        end = _end_for(segment, kind)
    return start, end


def _first(segment: dict, keys: tuple[str, ...], *, as_end: bool) -> datetime | None:
    for key in keys:
        if key not in segment:
            continue
        parsed = _instant(segment.get(key), as_end=as_end)
        if parsed is not None:
            return parsed
    return None


def _start_for(segment: dict, kind: str) -> datetime | None:
    if kind == "hotel":
        return _instant(segment.get("checkIn"), as_end=False)
    if kind == "attraction":
        return _date_and_time(segment.get("date"), segment.get("time"), as_end=False)
    return _instant(segment.get("departDate") or segment.get("date"), as_end=False)


def _end_for(segment: dict, kind: str) -> datetime | None:
    if kind == "hotel":
        return _instant(segment.get("checkOut") or segment.get("checkIn"), as_end=True)
    if kind == "attraction":
        if isinstance(segment.get("time"), str) and segment.get("time").strip():
            return _date_and_time(segment.get("date"), segment.get("time"), as_end=False)
        return _instant(segment.get("date"), as_end=True)
    raw = segment.get("returnDate") or segment.get("departDate") or segment.get("date")
    return _instant(raw, as_end=True)


def _date_and_time(date_value, time_value, *, as_end: bool) -> datetime | None:
    if isinstance(date_value, str) and "T" in date_value:
        return _instant(date_value, as_end=as_end)
    day = _parse_date(date_value)
    clock = _parse_clock(time_value)
    if day is None:
        return _instant(date_value, as_end=as_end)
    if clock is None:
        return _end_of_date(day) if as_end else day
    hour, minute, second = clock
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def _instant(value, *, as_end: bool) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    day = _parse_date(text)
    if day is not None:
        return _end_of_date(day) if as_end else day
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


def _end_of_date(day: datetime) -> datetime:
    return day + timedelta(days=1)


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


def _update(segment_id: str, kind: str, issue: str, action: str) -> dict:
    return {"segmentId": segment_id, "kind": kind, "issue": issue, "action": action}


def _result(phase: str, on_track: bool, updates: list) -> dict:
    return {"phase": phase, "onTrack": on_track, "updates": updates}
