"""List booking, refund, and ride codes for one trip.

Sandbox only: no network and no AWS. The master agent calls this on the
Amazon Bedrock AgentCore runtime at the end of a tick so the traveler has
one list of those codes. This module does not run that loop.
"""

from __future__ import annotations

import json
import math

_ENVELOPE_KEYS = ("tripId", "trip_id", "items")
_LINE_FIELDS = ("kind", "segmentId", "code", "amount", "currency")


def trip_wallet(tripId=None, items=None) -> dict:
    """Return ``tripId``, ``lines``, and ``count``. Never raises.

    ``tripId`` may be the id, or one object with ``tripId`` and ``items``.
    Each line is kind, segment id, code, amount, and currency, skipping
    nulls. ``count`` is the number of items that have a code. Empty items
    return count 0 and an empty list.
    """
    try:
        trip_id, item_list = _normalize(tripId, items)
        return _result(trip_id, _lines(item_list))
    except Exception:
        return _result("", [])


def _normalize(tripId, items):
    if isinstance(tripId, str) and items is None:
        try:
            loaded = json.loads(tripId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            tripId = loaded
        else:
            return "", []
    if isinstance(tripId, dict) and items is None:
        source = tripId
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        return (
            _trip_id(source.get("tripId", source.get("trip_id"))),
            _item_list(source.get("items")),
        )
    return _trip_id(tripId), _item_list(items)


def _lines(items: list) -> list[str]:
    lines = []
    for item in items:
        try:
            line = _line(item)
        except Exception:
            continue
        if line is not None:
            lines.append(line)
    return lines


def _line(item) -> str | None:
    if not isinstance(item, dict):
        return None
    code = _token(item, "code")
    if code is None:
        return None
    parts = []
    for field in _LINE_FIELDS:
        token = code if field == "code" else _token(item, field)
        if token is not None:
            parts.append(token)
    return " ".join(parts)


def _token(item: dict, field: str) -> str | None:
    if field == "segmentId":
        value = item["segmentId"] if "segmentId" in item else item.get("segment_id")
    else:
        value = item.get(field)
    if field == "amount":
        return _amount(value)
    return _text(value)


def _trip_id(value) -> str:
    return _text(value) or ""


def _text(value) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return None


def _amount(value) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return _text(value)


def _item_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _result(trip_id: str, lines: list[str]) -> dict:
    copied = list(lines)
    return {"tripId": trip_id, "lines": copied, "count": len(copied)}
