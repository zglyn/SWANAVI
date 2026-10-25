"""Replace one cancelled segment with the same kind on the same day.

Sandbox only: no network, no airline or hotel API, and no wall-clock read.
The caller passes ``now``. This module does not build a new itinerary, change
city, or add stops, and it does not call the planner. A later integrator
wires the master.

A flight start is ``departDate`` at 00:00 UTC. A hotel start is ``checkIn``
at 00:00 UTC. An attraction start is ``date`` plus ``time`` when ``time`` is
present, otherwise ``date`` at 00:00 UTC. Those are the instants the existing
fields can name. A start before ``now`` is rewritten as ``now`` plus 30
minutes. A date-only field changes only when that instant falls on another
UTC date.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

REASON_NOT_CANCELLED = "not_cancelled"
REASON_REBOOKED = "rebooked"
REASON_UNREADABLE = "unreadable"

NOTE_NOT_CANCELLED = "segment is not cancelled"
NOTE_KEPT = "kept the original start"
NOTE_UNREADABLE = "rebook_segment could not read the input"

_SHIFT = timedelta(minutes=30)
_KINDS = frozenset({"flight", "hotel", "attraction"})
_ENVELOPE_KEYS = ("tripId", "trip_id", "now", "segment", "travelers", "cancelled")


def rebook_segment(
    tripId=None,
    now=None,
    segment=None,
    travelers=None,
    cancelled=None,
) -> dict:
    """Rebook one cancelled segment, or leave it alone when it is not cancelled.

    ``tripId`` may be the id, or one object with ``tripId``, ``now``,
    ``segment``, ``travelers``, and ``cancelled``. Never raises.
    """
    try:
        trip_id, now, segment, travelers, cancelled = _normalize(
            tripId, now, segment, travelers, cancelled
        )
        return _rebook(trip_id, now, segment, travelers, cancelled)
    except Exception:
        return _unreadable(_segment_id(segment))


def _normalize(tripId, now, segment, travelers, cancelled):
    if (
        isinstance(tripId, str)
        and now is None
        and segment is None
        and travelers is None
        and cancelled is None
    ):
        try:
            loaded = json.loads(tripId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            tripId = loaded
    if (
        isinstance(tripId, dict)
        and now is None
        and segment is None
        and travelers is None
        and cancelled is None
    ):
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
                source.get("segment"),
                source.get("travelers"),
                source.get("cancelled"),
            )
    return tripId, now, segment, travelers, cancelled


def _rebook(trip_id, now, segment, travelers, cancelled) -> dict:
    segment_id = _segment_id(segment)
    if cancelled is False:
        return _result(segment_id, False, REASON_NOT_CANCELLED, None, [NOTE_NOT_CANCELLED])
    if cancelled is not True:
        return _unreadable(segment_id, "cancelled must be a boolean")

    parsed_now = _instant(now)
    if parsed_now is None:
        return _unreadable(segment_id, "now is not an ISO-8601 timestamp")
    if not isinstance(trip_id, str) or not trip_id.strip():
        return _unreadable(segment_id, "tripId is required")
    party = _party(travelers)
    if party is None:
        return _unreadable(segment_id, "travelers must be a list")
    if not isinstance(segment, dict):
        return _unreadable(segment_id, "segment must be an object")

    kind = segment.get("kind")
    if kind not in _KINDS or not segment_id:
        return _unreadable(segment_id, "segment needs a segmentId and a flight, hotel, or attraction kind")

    built = _schedule(segment, kind, parsed_now)
    if built is None:
        return _unreadable(segment_id, "segment fields could not be kept")

    fields, shifted, when = built
    price = _price(segment.get("price"))
    replacement = {
        "segmentId": segment_id,
        "kind": kind,
        **fields,
        "status": "booked",
        "confirmationCode": _confirmation(trip_id.strip(), segment_id, kind, fields, party),
        "price": price,
        "error": None,
    }
    note = NOTE_KEPT if not shifted else f"moved the start to {when} UTC"
    return _result(segment_id, True, REASON_REBOOKED, replacement, [note])


def _schedule(segment: dict, kind: str, now_at: datetime):
    if kind == "flight":
        return _flight_schedule(segment, now_at)
    if kind == "hotel":
        return _hotel_schedule(segment, now_at)
    return _attraction_schedule(segment, now_at)


def _flight_schedule(segment: dict, now_at: datetime):
    origin = _text(segment.get("from"))
    destination = _text(segment.get("to"))
    depart = _parse_date(segment.get("departDate"))
    if origin is None or destination is None or depart is None:
        return None
    start = depart
    shifted, new_start = _next_start(start, now_at)
    new_day = _utc_date(new_start)
    old_day = depart.date()
    fields = {
        "from": origin,
        "to": destination,
        "departDate": _kept_or_date(segment.get("departDate"), old_day, new_day),
    }
    if not _optional_date(segment, "returnDate", fields, old_day, new_day):
        return None
    if not _optional_text_field(segment, "cabin", fields):
        return None
    if not _optional_ids(segment, fields):
        return None
    return fields, shifted, _when(new_start)


def _hotel_schedule(segment: dict, now_at: datetime):
    city = _text(segment.get("city"))
    check_in = _parse_date(segment.get("checkIn"))
    check_out = _parse_date(segment.get("checkOut"))
    if city is None or check_in is None or check_out is None:
        return None
    if check_out.date() <= check_in.date():
        return None
    shifted, new_start = _next_start(check_in, now_at)
    new_day = _utc_date(new_start)
    old_day = check_in.date()
    fields = {
        "city": city,
        "checkIn": _kept_or_date(segment.get("checkIn"), old_day, new_day),
        "checkOut": _shift_date(segment.get("checkOut"), check_out.date(), old_day, new_day),
    }
    if not _optional_int_field(segment, "rooms", fields):
        return None
    if not _optional_int_field(segment, "guests", fields):
        return None
    return fields, shifted, _when(new_start)


def _attraction_schedule(segment: dict, now_at: datetime):
    name = _text(segment.get("name"))
    city = _text(segment.get("city"))
    day = _parse_date(segment.get("date"))
    if name is None or city is None or day is None:
        return None
    clock_state, clock = _clock(segment.get("time"), "time" in segment and segment.get("time") is not None)
    if clock_state == "bad":
        return None
    if clock is None:
        start = day
    else:
        hour, minute, second = clock
        start = day.replace(hour=hour, minute=minute, second=second)
    shifted, new_start = _next_start(start, now_at)
    new_day = _utc_date(new_start)
    fields = {
        "name": name,
        "city": city,
        "date": _kept_or_date(segment.get("date"), day.date(), new_day),
    }
    if shifted:
        fields["time"] = _utc(new_start).strftime("%H:%M")
    elif clock is not None:
        fields["time"] = _text(segment.get("time"))
    if not _optional_int_field(segment, "partySize", fields):
        return None
    return fields, shifted, _when(new_start)


def _next_start(start: datetime, now_at: datetime) -> tuple[bool, datetime]:
    if start < now_at:
        return True, now_at + _SHIFT
    return False, start


def _optional_date(segment: dict, key: str, fields: dict, old_day, new_day) -> bool:
    if key not in segment or segment.get(key) is None:
        return True
    parsed = _parse_date(segment.get(key))
    if parsed is None:
        return False
    fields[key] = _shift_date(segment.get(key), parsed.date(), old_day, new_day)
    return True


def _optional_text_field(segment: dict, key: str, fields: dict) -> bool:
    if key not in segment or segment.get(key) is None:
        return True
    text = _text(segment.get(key))
    if text is None:
        return False
    fields[key] = text
    return True


def _optional_ids(segment: dict, fields: dict) -> bool:
    if "travelerIds" not in segment or segment.get("travelerIds") is None:
        return True
    raw = segment.get("travelerIds")
    if not isinstance(raw, list):
        return False
    ids: list[str] = []
    for item in raw:
        text = _text(item)
        if text is None:
            return False
        ids.append(text)
    fields["travelerIds"] = ids
    return True


def _optional_int_field(segment: dict, key: str, fields: dict) -> bool:
    if key not in segment or segment.get(key) is None:
        return True
    value = segment.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return False
    fields[key] = value
    return True


def _kept_or_date(raw, old_day, new_day) -> str:
    if old_day == new_day:
        return _text(raw) or new_day.isoformat()
    return new_day.isoformat()


def _shift_date(raw, original, old_anchor, new_anchor) -> str:
    if old_anchor == new_anchor:
        return _text(raw) or original.isoformat()
    return (original + timedelta(days=(new_anchor - old_anchor).days)).isoformat()


def _clock(value, present: bool):
    if not present:
        return "omit", None
    parsed = _parse_clock(value)
    if parsed is None:
        return "bad", None
    return "set", parsed


def _party(travelers):
    if not isinstance(travelers, list):
        return None
    names: list[str] = []
    for traveler in travelers:
        if isinstance(traveler, str):
            text = _text(traveler)
            if text is None:
                return None
            names.append(text)
            continue
        if not isinstance(traveler, dict):
            return None
        ident = traveler.get("id", traveler.get("travelerId"))
        if isinstance(ident, str) and ident.strip():
            names.append(ident.strip())
            continue
        name = traveler.get("name")
        if isinstance(name, str) and name.strip():
            names.append(" ".join(name.split()))
            continue
        given = traveler.get("givenName") if isinstance(traveler.get("givenName"), str) else ""
        family = traveler.get("familyName") if isinstance(traveler.get("familyName"), str) else ""
        joined = " ".join(f"{given} {family}".split())
        if not joined:
            return None
        names.append(joined)
    return names


def _price(price):
    if not isinstance(price, dict):
        return None
    amount = price.get("amount")
    currency = price.get("currency")
    if isinstance(amount, bool) or isinstance(amount, float):
        return None
    if isinstance(amount, int):
        copied = amount
    elif isinstance(amount, str) and amount.strip():
        copied = amount.strip()
    else:
        return None
    if not isinstance(currency, str) or not currency.strip():
        return None
    return {"amount": copied, "currency": currency.strip()}


def _confirmation(trip_id: str, segment_id: str, kind: str, fields: dict, party: list[str]) -> str:
    payload = json.dumps(
        {
            "tripId": trip_id,
            "segmentId": segment_id,
            "kind": kind,
            "fields": fields,
            "party": party,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-RB-{digest}"


def _segment_id(segment) -> str:
    if not isinstance(segment, dict):
        return ""
    return _text(segment.get("segmentId")) or ""


def _text(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


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


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return _utc(parsed)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _parse_date(text) is not None:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _utc_date(value: datetime):
    return _utc(value).date()


def _when(value: datetime) -> str:
    return _utc(value).strftime("%Y-%m-%d %H:%M")


def _result(segment_id: str, changed: bool, reason: str, replacement, notes: list[str]) -> dict:
    return {
        "segmentId": segment_id,
        "changed": changed,
        "reason": reason,
        "replacement": replacement,
        "notes": notes,
    }


def _unreadable(segment_id: str, note: str = NOTE_UNREADABLE) -> dict:
    return _result(segment_id, False, REASON_UNREADABLE, None, [note])
