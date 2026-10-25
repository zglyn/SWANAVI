"""Sandbox attraction confirmation email.

``sample_email`` builds the message a traveler would receive after a ticket
books. ``verify`` checks that message. Neither function uses a network, an
inbox, or AWS. ``verify`` returns ``verified: false`` for a bad email and
does not raise.
"""

from __future__ import annotations

import re
from datetime import date

_FROM = "tickets@sandbox.roam402.invalid"
_TO_FALLBACK = "traveler@sandbox.roam402.invalid"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KIND = "attraction"

# Checked in this order so a failure reason stays stable.
_CHECKS = ("confirmation code", "attraction name", "date", "party size")


def sample_email(segment: object, confirmation_code: object, travelers: object, trip_id: object) -> dict:
    """Build the sandbox confirmation a traveler would get after the ticket books.

    The body includes the confirmation code, attraction name, city, date, and
    party size. ``receivedAt`` is the visit date at 18:00:00Z when that date
    is a real calendar day, otherwise a fixed sandbox timestamp.
    """

    try:
        name = _text_field(segment, "name")
        city = _text_field(segment, "city")
        visit = _text_field(segment, "date")
        party = _party_size(segment)
        code = _code(confirmation_code)
        trip = trip_id.strip() if isinstance(trip_id, str) else ""
        party_text = "" if party is None else str(party)
        subject_name = name or "Attraction"
        subject_code = code or "confirmation pending"
        body = "\n".join(
            [
                "Your attraction tickets are confirmed.",
                "",
                f"Confirmation code: {code or ''}",
                f"Attraction: {name or ''}",
                f"City: {city or ''}",
                f"Date: {visit or ''}",
                f"Party size: {party_text}",
                f"Trip: {trip}",
                "",
                "Sandbox message. No inbox was used.",
            ]
        )
        return {
            "from": _FROM,
            "to": _recipients(travelers),
            "subject": f"Attraction tickets confirmed — {subject_name} — {subject_code}",
            "body": body,
            "receivedAt": _received_at(visit),
        }
    except Exception:
        return {
            "from": _FROM,
            "to": _TO_FALLBACK,
            "subject": "Attraction tickets confirmed",
            "body": "Sandbox message. No inbox was used.",
            "receivedAt": "1970-01-01T00:00:00Z",
        }


def verify(email: object, segment: object, confirmation_code: object, travelers: object) -> dict:
    """Return whether the confirmation email matches this attraction ticket.

    ``verified`` is true only when the confirmation code, attraction name,
    date, and party size each appear in the subject or the body. ``travelers``
    is the party the master agent booked. Those names are not a checked field.
    A wrong code, a wrong date, or a malformed email yields ``verified: false``.
    """

    try:
        segment_id = _segment_id(segment)
        if not isinstance(email, dict):
            return _result(segment_id, False, "confirmation email is missing")

        text = _email_text(email)
        if text is None:
            return _result(segment_id, False, "confirmation email has no subject or body")

        code = _code(confirmation_code)
        name = _text_field(segment, "name")
        visit = _text_field(segment, "date")
        party = _party_size(segment)
        found = {
            "confirmation code": code is not None and code in text,
            "attraction name": name is not None and name in text,
            "date": visit is not None and visit in text,
            "party size": party is not None and _party_size_appears(text, party, code=code, visit=visit),
        }
        missing = [label for label in _CHECKS if not found[label]]
        if missing:
            return _result(segment_id, False, "missing " + ", ".join(missing))
        return _result(
            segment_id,
            True,
            "confirmation code, attraction name, date, and party size match",
        )
    except Exception:
        return _result(_segment_id(segment), False, "confirmation email could not be read")


def _result(segment_id: str, verified: bool, reason: str) -> dict:
    return {
        "segmentId": segment_id,
        "kind": _KIND,
        "verified": verified,
        "reason": reason,
    }


def _segment_id(segment: object) -> str:
    if isinstance(segment, dict):
        value = segment.get("segmentId")
        if isinstance(value, str):
            return value
    return ""


def _text_field(segment: object, key: str) -> str | None:
    if not isinstance(segment, dict):
        return None
    value = segment.get(key)
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None


def _code(confirmation_code: object) -> str | None:
    if isinstance(confirmation_code, str):
        text = confirmation_code.strip()
        if text:
            return text
    return None


def _party_size(segment: object) -> int | None:
    if not isinstance(segment, dict):
        return None
    value = segment.get("partySize")
    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _email_text(email: dict) -> str | None:
    chunks: list[str] = []
    saw_text = False
    for key in ("subject", "body"):
        value = email.get(key)
        if isinstance(value, str):
            saw_text = True
            chunks.append(value)
    if not saw_text:
        return None
    return "\n".join(chunks)


def _party_size_appears(text: str, party_size: int, *, code: str | None, visit: str | None) -> bool:
    """True when ``party_size`` appears as its own number.

    The confirmation code and the visit date are removed first, so a digit
    inside either one does not count as the party size.
    """

    scrubbed = text
    if code:
        scrubbed = scrubbed.replace(code, " ")
    if visit:
        scrubbed = scrubbed.replace(visit, " ")
    return re.search(rf"(?<!\d){party_size}(?!\d)", scrubbed) is not None


def _received_at(visit: str | None) -> str:
    if visit and _DATE.fullmatch(visit):
        try:
            date.fromisoformat(visit)
        except ValueError:
            return "1970-01-01T00:00:00Z"
        return f"{visit}T18:00:00Z"
    return "1970-01-01T00:00:00Z"


def _recipients(travelers: object) -> str:
    if not isinstance(travelers, list):
        return _TO_FALLBACK
    parts: list[str] = []
    for traveler in travelers:
        if isinstance(traveler, dict):
            name = traveler.get("name")
            email = traveler.get("email")
            name_text = name.strip() if isinstance(name, str) else ""
            email_text = email.strip() if isinstance(email, str) else ""
            if email_text and name_text:
                parts.append(f"{name_text} <{email_text}>")
            elif email_text:
                parts.append(email_text)
            elif name_text:
                parts.append(f"{name_text} <{_TO_FALLBACK}>")
        elif isinstance(traveler, str) and traveler.strip():
            parts.append(f"{traveler.strip()} <{_TO_FALLBACK}>")
    return ", ".join(parts) or _TO_FALLBACK
