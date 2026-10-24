"""Sandbox hotel confirmation email. No network, no inbox, and no AWS."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, TypedDict

SANDBOX_FROM = "hotel-confirmations@sandbox.swanavi.invalid"
SANDBOX_TO = "guest@sandbox.swanavi.invalid"
SANDBOX_RECEIVED_AT = "2026-01-01T12:00:00Z"
VERIFIED_REASON = (
    "confirmation code, city, check-in, check-out, and guest names are in the email"
)

ConfirmationEmail = TypedDict(
    "ConfirmationEmail",
    {
        "from": str,
        "to": str,
        "subject": str,
        "body": str,
        "receivedAt": str,
    },
)


class VerifyResult(TypedDict):
    segmentId: str
    kind: Literal["hotel"]
    verified: bool
    reason: str


def sample_email(
    segment: object,
    confirmation_code: object,
    travelers: object,
    trip_id: object,
) -> ConfirmationEmail:
    """Build the confirmation email a traveler would get after a hotel books.

    The message stays in memory. Nothing is sent.
    """
    stay = segment if isinstance(segment, dict) else {}
    code = _code(confirmation_code)
    city = _city(stay) or ""
    check_in = _iso_date(stay.get("checkIn")) or ""
    check_out = _iso_date(stay.get("checkOut")) or ""
    names = _readable_names(travelers)
    trip = trip_id.strip() if isinstance(trip_id, str) else ""
    guest_lines = "\n".join(f"- {name}" for name in names) or "- (none)"
    subject_code = code or "pending"
    subject_city = city or "your city"
    body = (
        "Your hotel stay is confirmed.\n"
        "\n"
        f"Confirmation code: {code}\n"
        f"City: {city}\n"
        f"Check-in: {check_in}\n"
        f"Check-out: {check_out}\n"
        "Guests:\n"
        f"{guest_lines}\n"
        f"Trip: {trip}\n"
        f"Segment: {_segment_id(stay)}\n"
        "\n"
        "This message is a Swanavi sandbox confirmation. "
        "It was not delivered to an inbox.\n"
    )
    return {
        "from": SANDBOX_FROM,
        "to": _recipients(travelers),
        "subject": f"Hotel confirmation {subject_code} for {subject_city}",
        "body": body,
        "receivedAt": SANDBOX_RECEIVED_AT,
    }


def verify(
    email: object,
    segment: object,
    confirmation_code: object,
    travelers: object,
) -> VerifyResult:
    """Return whether the email matches the hotel segment.

    ``verified`` is true only when the confirmation code, city, check-in,
    check-out, and every guest name appear in the subject or body. A wrong
    code or wrong dates make ``verified`` false. A bad email does not raise.
    """
    segment_id = _segment_id(segment)
    try:
        return _verify(email, segment, confirmation_code, travelers, segment_id)
    except Exception:
        return _unverified(segment_id, "confirmation email could not be checked")


def _verify(
    email: object,
    segment: object,
    confirmation_code: object,
    travelers: object,
    segment_id: str,
) -> VerifyResult:
    if not isinstance(email, dict):
        return _unverified(segment_id, "email must be an object")

    text = f"{_string(email.get('subject'))}\n{_string(email.get('body'))}"
    problems: list[str] = []

    code = _code(confirmation_code)
    if not code:
        problems.append("confirmation code is missing")
    elif not _appears(text, code, casefold=False):
        problems.append("confirmation code is not in the email")

    if not isinstance(segment, dict):
        problems.append("segment must be an object")
    else:
        city = _city(segment)
        if not city:
            problems.append("city is missing from the segment")
        elif not _appears(text, city, casefold=True):
            problems.append("city is not in the email")

        check_in = _iso_date(segment.get("checkIn"))
        if check_in is None:
            problems.append("check-in is missing from the segment")
        elif not _appears(text, check_in, casefold=False):
            problems.append("check-in is not in the email")

        check_out = _iso_date(segment.get("checkOut"))
        if check_out is None:
            problems.append("check-out is missing from the segment")
        elif not _appears(text, check_out, casefold=False):
            problems.append("check-out is not in the email")

    names, name_problem = _guest_names(travelers)
    if name_problem is not None:
        problems.append(name_problem)
    else:
        for name in names:
            if not _appears(text, name, casefold=True):
                problems.append(f"guest name {name} is not in the email")

    if problems:
        return _unverified(segment_id, "; ".join(problems))
    return {
        "segmentId": segment_id,
        "kind": "hotel",
        "verified": True,
        "reason": VERIFIED_REASON,
    }


def _unverified(segment_id: str, reason: str) -> VerifyResult:
    return {
        "segmentId": segment_id,
        "kind": "hotel",
        "verified": False,
        "reason": reason,
    }


def _appears(text: str, phrase: str, *, casefold: bool) -> bool:
    """True when ``phrase`` appears as its own token in ``text``."""
    haystack = " ".join(text.split())
    needle = " ".join(phrase.split())
    if not needle:
        return False
    if casefold:
        haystack = haystack.casefold()
        needle = needle.casefold()
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index else " "
        end = index + len(needle)
        after = haystack[end] if end < len(haystack) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = index + 1


def _segment_id(segment: object) -> str:
    if not isinstance(segment, dict):
        return ""
    segment_id = segment.get("segmentId")
    if isinstance(segment_id, str) and segment_id.strip():
        return segment_id.strip()
    return ""


def _city(segment: dict) -> str | None:
    city = segment.get("city")
    if not isinstance(city, str):
        return None
    text = " ".join(city.strip().split())
    return text or None


def _code(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _iso_date(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    candidate = value.strip().split("T", 1)[0].split(" ", 1)[0]
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def _guest_names(travelers: object) -> tuple[list[str], str | None]:
    if not isinstance(travelers, list) or not travelers:
        return [], "guest names are missing"
    names: list[str] = []
    for index, traveler in enumerate(travelers):
        name = _person_name(traveler)
        if name is None:
            return [], f"travelers[{index}] is missing a name"
        names.append(name)
    return names, None


def _readable_names(travelers: object) -> list[str]:
    names, problem = _guest_names(travelers)
    if problem is not None:
        return []
    return names


def _person_name(traveler: object) -> str | None:
    if isinstance(traveler, str):
        raw = traveler
    elif isinstance(traveler, dict):
        value = traveler.get("name", traveler.get("fullName"))
        if not isinstance(value, str):
            return None
        raw = value
    else:
        return None
    name = " ".join(raw.strip().split())
    return name or None


def _recipients(travelers: object) -> str:
    if not isinstance(travelers, list):
        return SANDBOX_TO
    emails: list[str] = []
    for traveler in travelers:
        if not isinstance(traveler, dict):
            continue
        email = traveler.get("email")
        if isinstance(email, str) and email.strip():
            emails.append(email.strip())
    if not emails:
        return SANDBOX_TO
    return ", ".join(emails)
