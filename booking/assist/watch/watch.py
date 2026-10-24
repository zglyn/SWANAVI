"""Early warnings for a trip the master has not changed yet.

Sandbox only: no network, no AWS, and no wall-clock read. The caller passes
``now``. This module does not run the master loop, move the plan, or request
a ride. The master calls ``watch_trip`` first on every tick and acts on the
warnings itself.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

REPLAN_EVENTS = frozenset({"cancelled", "ended_early", "ended_late"})
WEATHER = frozenset({"rain", "storm", "snow"})
RIDE_WITHIN = timedelta(minutes=20)
TRANSFER_UNDER = timedelta(minutes=30)
RIDE_REQUESTED = "requested"

ISSUE_REPLAN = "signal event {event} needs a replan"
ISSUE_SHIFT = "outdoor segment has {condition} before the traveler arrives"
ISSUE_RIDE = "attraction ends within 20 minutes and a later same-day stop has no requested ride"
ISSUE_TRANSFER = "gap to {next_id} is under 30 minutes"

_LISTS = (("flights", "flight"), ("hotels", "hotel"), ("attractions", "attraction"))
_START_KEYS = ("start", "startsAt", "startAt")
_END_KEYS = ("end", "endsAt", "endAt")


def watch_trip(*args, **kwargs) -> dict:
    """Return ``ok`` and ``warnings``. Never raises.

    Call with ``now``, ``plan``, ``rides``, and ``signals``, or with one
    object that carries those fields. ``now`` is an ISO-8601 timestamp from
    the caller. This function does not change ``plan`` and does not add a ride.
    """
    try:
        now, plan, rides, signals = _bind(args, kwargs)
        return _watch(now, plan, rides, signals)
    except Exception:
        return _clear()


def _watch(now, plan, rides, signals) -> dict:
    now_at = _parse_instant(now)
    segments = _segments(plan if isinstance(plan, dict) else {})
    warnings: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    _from_signals(warnings, seen, signals, segments, now_at)
    _from_rides(warnings, seen, segments, now_at, _requested(rides))
    _from_transfers(warnings, seen, segments)
    act = any(item["severity"] == "act" for item in warnings)
    return {"ok": not act, "warnings": warnings}


def _from_signals(warnings, seen, signals, segments, now_at) -> None:
    for signal in _dicts(signals):
        segment_id = _text_id(signal.get("segmentId"))
        event = _token(signal.get("event"))
        if event in REPLAN_EVENTS:
            _add(warnings, seen, segment_id, ISSUE_REPLAN.format(event=event), "replan")
        condition = _token(signal.get("condition"))
        if condition not in WEATHER or now_at is None:
            continue
        segment = _find(segments, segment_id)
        if segment is None or segment["removed"] or not segment["outdoor"]:
            continue
        start = segment["start"]
        # Still in the future: the traveler is not there yet.
        if start is None or start <= now_at:
            continue
        _add(warnings, seen, segment_id, ISSUE_SHIFT.format(condition=condition), "shift")


def _from_rides(warnings, seen, segments, now_at, requested: set[str]) -> None:
    if now_at is None:
        return
    for segment in segments:
        if segment["kind"] != "attraction" or segment["removed"]:
            continue
        end = segment["end"]
        if end is None or not _ends_soon(end, now_at):
            continue
        if not _later_same_day(segment, segments):
            continue
        if segment["segmentId"] in requested:
            continue
        _add(warnings, seen, segment["segmentId"], ISSUE_RIDE, "request_ride")


def _from_transfers(warnings, seen, segments) -> None:
    ordered = [
        segment
        for segment in segments
        if not segment["removed"]
        and segment["start"] is not None
        and segment["end"] is not None
        and segment["end"] >= segment["start"]
    ]
    ordered.sort(key=lambda segment: (segment["start"], segment["end"], segment["segmentId"], segment["index"]))
    for left, right in zip(ordered, ordered[1:]):
        gap = right["start"] - left["end"]
        if timedelta(0) <= gap < TRANSFER_UNDER:
            next_id = right["segmentId"] or "the next stop"
            _add(warnings, seen, left["segmentId"], ISSUE_TRANSFER.format(next_id=next_id), "check_transfer")


def _ends_soon(end: datetime, now_at: datetime) -> bool:
    """True when ``end`` is now or up to 20 minutes after now."""
    delta = end - now_at
    return timedelta(0) <= delta <= RIDE_WITHIN


def _later_same_day(segment: dict, segments: list[dict]) -> bool:
    end = segment["end"]
    if end is None:
        return False
    day = end.astimezone(timezone.utc).date()
    for other in segments:
        if other["index"] == segment["index"] or other["removed"] or other["start"] is None:
            continue
        if other["start"] < end:
            continue
        if other["start"].astimezone(timezone.utc).date() == day:
            return True
    return False


def _add(warnings: list, seen: set, segment_id: str, issue: str, action: str) -> None:
    key = (segment_id, action, issue)
    if key in seen:
        return
    seen.add(key)
    warnings.append(
        {
            "segmentId": segment_id,
            "issue": issue,
            "severity": "act",
            "action": action,
        }
    )


def _clear() -> dict:
    return {"ok": True, "warnings": []}


def _bind(args, kwargs):
    if len(args) == 1 and not kwargs:
        return _from_value(args[0])
    return (
        _pick(kwargs, args, "now", 0),
        _pick(kwargs, args, "plan", 1),
        _pick(kwargs, args, "rides", 2),
        _pick(kwargs, args, "signals", 3),
    )


def _pick(kwargs, args, name: str, index: int):
    if name in kwargs:
        return kwargs[name]
    if len(args) > index:
        return args[index]
    return None


def _from_value(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None, None, None, None
    if not isinstance(value, dict):
        return None, None, None, None
    source = _unwrap(value)
    now = source.get("now")
    rides = source.get("rides")
    signals = source.get("signals")
    if "plan" in source and isinstance(source.get("plan"), dict):
        return now, source.get("plan"), rides, signals
    if _looks_like_plan(source):
        return now, source, rides, signals
    return now, None, rides, signals


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    keys = ("plan", "now", "rides", "signals")
    if isinstance(nested, dict) and not any(key in payload for key in keys) and not _looks_like_plan(payload):
        return nested
    return payload


def _looks_like_plan(value: dict) -> bool:
    return any(key in value for key in ("flights", "hotels", "attractions"))


def _segments(plan: dict) -> list[dict]:
    records = []
    index = 0
    for bucket, fallback in _LISTS:
        items = plan.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            records.append(
                {
                    "segmentId": _text_id(item.get("segmentId")),
                    "kind": _kind(item, fallback),
                    "start": _explicit(item, _START_KEYS),
                    "end": _explicit(item, _END_KEYS),
                    "outdoor": _outdoor(item),
                    "removed": item.get("removed") is True,
                    "index": index,
                }
            )
            index += 1
    return records


def _kind(segment: dict, fallback: str) -> str:
    kind = segment.get("kind")
    if isinstance(kind, str) and kind.strip():
        return kind.strip().lower()
    return fallback


def _outdoor(segment: dict) -> bool:
    if "outdoor" in segment:
        return _yes(segment.get("outdoor"))
    indoor = segment.get("indoor")
    if indoor is False:
        return True
    if isinstance(indoor, str) and indoor.strip().lower() in {"false", "no"}:
        return True
    return False


def _yes(value) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in {"true", "yes", "outdoor"}:
        return True
    return False


def _explicit(segment: dict, keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        if key not in segment:
            continue
        parsed = _parse_instant(segment.get(key))
        if parsed is not None:
            return parsed
    return None


def _find(segments: list[dict], segment_id: str) -> dict | None:
    if not segment_id:
        return None
    for segment in segments:
        if segment["segmentId"] == segment_id:
            return segment
    return None


def _requested(rides) -> set[str]:
    found = set()
    for ride in _dicts(rides):
        if _token(ride.get("status")) != RIDE_REQUESTED:
            continue
        segment_id = _text_id(ride.get("fromSegmentId"))
        if segment_id:
            found.add(segment_id)
    return found


def _dicts(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text_id(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _token(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _parse_instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _date_only(text):
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


def _date_only(value: str) -> bool:
    text = value.strip()
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True
