"""Decide whether the gap between two stops covers the ride.

Sandbox only. The caller supplies both clocks and the ride length. This
module does not read the wall clock, call a maps API, open the network, or
call AWS. The master agent calls ``check_transfer`` between consecutive stops.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

_CALL_KEYS = ("fromSegmentId", "toSegmentId", "fromEnd", "toStart", "travelMinutes")
_MINUTE_MICROSECONDS = 60 * 1_000_000


def check_transfer(
    fromSegmentId=None,
    toSegmentId=None,
    fromEnd=None,
    toStart=None,
    travelMinutes=None,
) -> dict:
    """Return whether ``toStart - fromEnd`` covers ``travelMinutes``.

    ``ok`` is true when the gap is at least the ride. ``leaveBy`` is
    ``fromEnd`` when that is true, otherwise null. ``shortfallMinutes`` is
    ``max(0, travelMinutes - gap)`` for a whole-minute gap. A negative gap is
    an overlap: ``ok`` is false. Never raises.
    """
    try:
        bare_payload = (
            _is_payload(fromSegmentId)
            and toSegmentId is None
            and fromEnd is None
            and toStart is None
            and travelMinutes is None
        )
        if bare_payload:
            data = _load(fromSegmentId)
        else:
            data = {
                "fromSegmentId": fromSegmentId,
                "toSegmentId": toSegmentId,
                "fromEnd": fromEnd,
                "toStart": toStart,
                "travelMinutes": travelMinutes,
            }
        if not isinstance(data, dict):
            return _invalid()
        return _decide(data)
    except Exception:
        return _invalid()


def _decide(data: dict) -> dict:
    from_raw = data.get("fromEnd")
    to_raw = data.get("toStart")
    travel = _minutes(data.get("travelMinutes"))
    from_at = _instant(from_raw)
    to_at = _instant(to_raw)
    if travel is None or from_at is None or to_at is None:
        return _invalid()

    gap_micro = _span_microseconds(from_at, to_at)
    need_micro = travel * _MINUTE_MICROSECONDS
    shortfall = _shortfall_minutes(need_micro, gap_micro)
    if gap_micro < 0:
        return _result(False, None, shortfall, "overlap")
    if gap_micro >= need_micro:
        return _result(True, _leave_by(from_raw, from_at), 0, "enough_time")
    return _result(False, None, shortfall, "shortfall")


def _result(ok: bool, leave_by: str | None, shortfall: int, reason: str) -> dict:
    return {
        "ok": ok,
        "leaveBy": leave_by,
        "shortfallMinutes": shortfall,
        "reason": reason,
    }


def _invalid() -> dict:
    return _result(False, None, 0, "invalid_input")


def _shortfall_minutes(need_micro: int, gap_micro: int) -> int:
    """Whole minutes still needed. Exact minute gaps match ``max(0, travel - gap)``."""
    deficit = need_micro - gap_micro
    if deficit <= 0:
        return 0
    return (deficit + _MINUTE_MICROSECONDS - 1) // _MINUTE_MICROSECONDS


def _span_microseconds(start: datetime, end: datetime) -> int:
    delta = end - start
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _leave_by(raw, parsed: datetime) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    text = parsed.astimezone(timezone.utc).isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def _minutes(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        if value != int(value):
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 10)
        except ValueError:
            return None
    return None


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
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _CALL_KEYS):
        return nested
    return payload
