"""Sandbox flight check-in for one segment.

The caller supplies ``now``. This module does not read the wall clock, open
the network, call an airline, or call AWS. It does not run the master loop.
A partial input returns ``error`` ``invalid_segment`` and does not raise.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

STATUS_WAITING = "waiting"
STATUS_CHECKED_IN = "checked_in"
STATUS_MISSED = "missed"
STATUS_NEEDS_USER = "needs_user"
STATUS_NOT_A_FLIGHT = "not_a_flight"
ERROR_INVALID = "invalid_segment"

_WINDOW = timedelta(hours=24)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ENVELOPE_KEYS = ("now", "segment", "travelers")
_DEPART_AT_KEYS = ("departAt", "depart_at")
_DEPART_DATE_KEYS = ("departDate", "depart_date")
_CONFIRMATION_KEYS = ("confirmationCode", "confirmation_code")


def check_in_flight(now=None, segment=None, travelers=None) -> dict:
    """Return a sandbox check-in for one segment. Never raises.

    ``now`` may be an ISO-8601 timestamp, or one object with ``now``,
    ``segment``, and ``travelers``. The check-in window opens 24 hours
    before departure. A date-only ``departDate`` is that date at 09:00 UTC.
    ``boardingPass`` is a sandbox code, not a barcode.
    """
    try:
        data = _payload(now, segment, travelers)
        if not isinstance(data, dict):
            return _invalid("")
        return _decide(data)
    except Exception:
        return _invalid("")


def _payload(now, segment, travelers):
    bare = isinstance(now, (dict, str)) and segment is None and travelers is None
    if bare:
        if isinstance(now, str):
            loaded = _json_object(now)
            if not isinstance(loaded, dict):
                return None
            return _unwrap(loaded)
        return _unwrap(now)
    if now is None and segment is None and travelers is None:
        return None
    return {"now": now, "segment": segment, "travelers": travelers}


def _json_object(text: str):
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, str):
        arguments = _json_object(arguments)
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _ENVELOPE_KEYS):
        return nested
    return payload


def _decide(data: dict) -> dict:
    segment = data.get("segment")
    if not isinstance(segment, dict):
        return _invalid("")
    segment_id = _segment_id(segment)
    if segment_id is None:
        return _invalid("")
    if not isinstance(data.get("travelers"), list):
        return _invalid(segment_id)

    kind = _kind(segment)
    if kind is None:
        return _invalid(segment_id)
    if kind != "flight":
        return _result(segment_id, STATUS_NOT_A_FLIGHT, None, None)

    now_at = _instant(data.get("now"))
    if now_at is None:
        return _invalid(segment_id)
    depart = _departure(segment)
    if depart is None:
        return _invalid(segment_id)

    opens_at = _format(depart - _WINDOW)
    confirmation = _confirmation(segment)
    if confirmation is None:
        return _result(segment_id, STATUS_NEEDS_USER, None, opens_at)
    if now_at >= depart:
        return _result(segment_id, STATUS_MISSED, None, opens_at)
    if now_at < depart - _WINDOW:
        return _result(segment_id, STATUS_WAITING, None, opens_at)
    return _result(
        segment_id,
        STATUS_CHECKED_IN,
        _boarding_pass(segment_id, confirmation, data.get("travelers")),
        opens_at,
    )


def _result(segment_id: str, status: str | None, boarding_pass: str | None, opens_at: str | None) -> dict:
    return {
        "segmentId": segment_id,
        "status": status,
        "boardingPass": boarding_pass,
        "opensAt": opens_at,
        "error": None,
    }


def _invalid(segment_id: str) -> dict:
    return {
        "segmentId": segment_id,
        "status": None,
        "boardingPass": None,
        "opensAt": None,
        "error": ERROR_INVALID,
    }


def _segment_id(segment: dict) -> str | None:
    value = segment.get("segmentId", segment.get("segment_id"))
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _kind(segment: dict) -> str | None:
    value = segment.get("kind")
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text or None


def _confirmation(segment: dict) -> str | None:
    value = _first(segment, _CONFIRMATION_KEYS)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _departure(segment: dict) -> datetime | None:
    if _present(segment, _DEPART_AT_KEYS):
        return _instant(_first(segment, _DEPART_AT_KEYS))
    if not _present(segment, _DEPART_DATE_KEYS):
        return None
    raw = _first(segment, _DEPART_DATE_KEYS)
    if isinstance(raw, str) and _DATE.fullmatch(raw.strip()):
        try:
            day = datetime.strptime(raw.strip(), "%Y-%m-%d")
        except ValueError:
            return None
        return day.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return _instant(raw)


def _present(segment: dict, keys: tuple[str, ...]) -> bool:
    for key in keys:
        if key in segment and not _blank(segment.get(key)):
            return True
    return False


def _first(segment: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in segment:
            return segment.get(key)
    return None


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


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


def _format(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _boarding_pass(segment_id: str, confirmation: str, travelers: list) -> str:
    party = []
    for traveler in travelers:
        if not isinstance(traveler, dict):
            continue
        traveler_id = traveler.get("id")
        name = traveler.get("name")
        traveler_id = traveler_id.strip() if isinstance(traveler_id, str) else ""
        name = " ".join(name.split()) if isinstance(name, str) else ""
        if traveler_id or name:
            party.append(f"{traveler_id}:{name}")
    party.sort()
    raw = "|".join((segment_id, confirmation, ",".join(party)))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-BP-{digest}"
