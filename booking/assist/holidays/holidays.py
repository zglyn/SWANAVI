"""Decide whether one segment is closed for a sandbox public holiday.

The holiday table lives in this module. The caller supplies the segment.
A ``shift`` is a signal for the master, the same idea as a weather hold.
This function leaves the segment where it is. It does not read the wall
clock, open the network, or call AWS.
"""

from __future__ import annotations

import json
from datetime import date

_FIELDS = ("segmentId", "kind", "name", "city", "country", "date")
_KINDS = frozenset({"attraction", "flight", "hotel", "restaurant"})

# Canonical country keys after case-insensitive alias matching.
_COUNTRIES = {
    "japan": "JP",
    "jp": "JP",
    "france": "FR",
    "fr": "FR",
    "united states": "US",
    "us": "US",
    "usa": "US",
}

# date → holiday name, scoped to the country that observes it.
_HOLIDAYS = {
    ("JP", "2026-11-03"): "Culture Day",
    ("JP", "2026-11-23"): "Labor Thanksgiving Day",
    ("FR", "2026-11-11"): "Armistice Day",
    ("US", "2026-11-26"): "Thanksgiving Day",
}

_ERROR = "invalid_segment"


def holiday_closure(segment=None, **kwargs) -> dict:
    """Return whether ``segment`` is closed for a sandbox holiday.

    ``segment`` is ``{segmentId, kind, name, city, country, date}``, a JSON
    object of those fields, or ``{"segment": {...}}``. The same fields may
    be passed as keywords. Never raises.

    An attraction on a listed holiday is closed and asks for ``shift``.
    Flights, hotels, and restaurants stay open on that same holiday.
    Any other date stays open and ``holiday`` is null. A segment that
    cannot be read returns ``error`` ``invalid_segment`` and ``action``
    ``none``. The input segment is not modified.
    """
    try:
        data = _load(segment, kwargs)
        if not isinstance(data, dict):
            return _invalid("")
        return _decide(data)
    except Exception:
        return _invalid("")


def _load(segment, kwargs) -> dict | None:
    if isinstance(segment, str) and not kwargs:
        segment = _json_object(segment)
    if segment is None and not kwargs:
        return None
    if isinstance(segment, dict):
        data = _unwrap(segment)
        if kwargs:
            data = dict(data)
            for key in _FIELDS:
                if key in kwargs:
                    data[key] = kwargs[key]
        return data
    if segment is None and kwargs:
        return _unwrap(dict(kwargs))
    return None


def _json_object(payload: str) -> dict | None:
    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return loaded
    return None


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, str):
        arguments = _json_object(arguments)
    if isinstance(arguments, dict):
        payload = arguments
    elif isinstance(payload.get("input"), dict) and not _looks_like_segment(payload):
        payload = payload["input"]
    nested = payload.get("segment")
    if isinstance(nested, str):
        nested = _json_object(nested)
    if isinstance(nested, dict) and not _looks_like_segment(payload):
        return nested
    return payload


def _looks_like_segment(value: dict) -> bool:
    return any(key in value for key in _FIELDS)


def _decide(data: dict) -> dict:
    segment_id = _segment_id(data.get("segmentId"))
    if any(key not in data for key in _FIELDS):
        return _invalid(segment_id)
    kind = _kind(data.get("kind"))
    day = _calendar_date(data.get("date"))
    country = _country(data.get("country"))
    if (
        not segment_id
        or kind is None
        or day is None
        or country is None
        or not _present_text(data.get("name"))
        or not _present_text(data.get("city"))
    ):
        return _invalid(segment_id)
    holiday = _HOLIDAYS.get((country, day))
    if kind == "attraction" and holiday is not None:
        return _result(segment_id, True, holiday, "shift")
    return _result(segment_id, False, holiday, "none")


def _result(segment_id: str, closed: bool, holiday: str | None, action: str) -> dict:
    return {
        "segmentId": segment_id,
        "closed": closed,
        "holiday": holiday,
        "action": action,
    }


def _invalid(segment_id: str) -> dict:
    result = _result(segment_id, False, None, "none")
    result["error"] = _ERROR
    return result


def _segment_id(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _present_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _kind(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    if text in _KINDS:
        return text
    return None


def _country(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().casefold().split())
    if not text:
        return None
    return _COUNTRIES.get(text, text)


def _calendar_date(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    parts = text.split("-")
    if len(parts) != 3 or len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        return None
    if not all(part.isdigit() for part in parts):
        return None
    try:
        date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
    return text
