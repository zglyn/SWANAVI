"""Decide whether a walk should become a ride after sunset.

Sandbox only: the caller supplies ``now`` and ``sunset``. This module does not
read the wall clock, open the network, or call AWS. It does not request a ride.
When the action is ``request_ride``, the master agent calls the ride agent.
This module does not run that loop.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

_ENVELOPE_KEYS = ("segmentId", "mode", "now", "sunset")
_TIME_FIELDS = ("now", "sunset")

REASON_RIDE = "mode is ride"
REASON_BEFORE = "walk is before sunset"
REASON_AFTER = "walk is at or after sunset"
REASON_MODE = "mode must be walk or ride"
REASON_FAILED = "after_dark failed closed"


def after_dark(source=None) -> dict:
    """Return ``segmentId``, ``ok``, ``action``, and ``reason``. Never raises.

    ``source`` is ``{segmentId, mode, now, sunset}`` or a JSON object with
    those fields. ``mode`` is ``walk`` or ``ride``. ``now`` and ``sunset`` are
    ISO-8601 instants from the caller.

    A ride is already fine: ``ok`` is true and ``action`` is ``none``. A walk
    at or after sunset is not fine: ``ok`` is false and ``action`` is
    ``request_ride``. A walk before sunset is fine. A walk with a missing or
    unreadable time returns ``ok`` false and ``action`` ``none``.
    """
    try:
        return _decide(_mapping(source))
    except Exception:
        return _result("", False, "none", REASON_FAILED)


def _mapping(source) -> dict:
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError:
            return {}
    if not isinstance(source, dict):
        return {}
    arguments = source.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = None
    if isinstance(arguments, dict):
        source = arguments
    elif isinstance(source.get("input"), dict) and not _looks_like_check(source):
        source = source["input"]
    if not isinstance(source, dict):
        return {}
    return source


def _looks_like_check(value: dict) -> bool:
    return any(key in value for key in _ENVELOPE_KEYS)


def _decide(data: dict) -> dict:
    segment_id = _segment_id(data.get("segmentId"))
    mode = _mode(data.get("mode"))
    if mode == "ride":
        return _result(segment_id, True, "none", REASON_RIDE)
    if mode != "walk":
        return _result(segment_id, False, "none", REASON_MODE)

    missing = []
    invalid = []
    instants = {}
    for key in _TIME_FIELDS:
        if key not in data or _blank(data.get(key)):
            missing.append(key)
            continue
        parsed = _parse_instant(data.get(key))
        if parsed is None:
            invalid.append(key)
            continue
        instants[key] = parsed
    if missing or invalid:
        return _result(segment_id, False, "none", _time_problem(missing, invalid))

    if instants["now"] >= instants["sunset"]:
        return _result(segment_id, False, "request_ride", REASON_AFTER)
    return _result(segment_id, True, "none", REASON_BEFORE)


def _segment_id(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _mode(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text in ("walk", "ride"):
        return text
    return None


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _time_problem(missing: list[str], invalid: list[str]) -> str:
    parts = []
    if missing:
        parts.append("missing " + ", ".join(missing))
    if invalid:
        parts.append("invalid " + ", ".join(invalid))
    return "; ".join(parts)


def _parse_instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _result(segment_id: str, ok: bool, action: str, reason: str) -> dict:
    return {
        "segmentId": segment_id,
        "ok": ok,
        "action": action,
        "reason": reason,
    }
