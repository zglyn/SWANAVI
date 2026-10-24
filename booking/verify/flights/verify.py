"""Build and check a sandbox flight confirmation email.

No inbox, no network, and no AWS. A bad email returns verified false.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_SENDER = "SWANAVI Sandbox <flights@sandbox.swanavi.invalid>"
_DEFAULT_RECIPIENT = "passenger@sandbox.swanavi.invalid"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")
_SUCCESS = "confirmation code, route, depart date, and traveler names are in the email"


def sample_email(segment, confirmation_code, travelers, trip_id) -> dict:
    """Return the confirmation email a traveler would get after a flight books.

    The body includes the confirmation code, origin, destination, depart date,
    and traveler names. `from` and `to` are the sandbox sender and recipient,
    not the airports. This does not send mail.
    """
    try:
        return _sample_email(segment, confirmation_code, travelers, trip_id)
    except Exception:
        return {
            "from": _SENDER,
            "to": _DEFAULT_RECIPIENT,
            "subject": "Flight confirmation",
            "body": "Sandbox flight confirmation could not be rendered.",
            "receivedAt": _received_at(),
        }


def verify(email, segment, confirmation_code, travelers) -> dict:
    """Return whether the email matches the booked flight.

    `verified` is true only when the confirmation code, both airports, the
    depart date, and every traveler name each appear in the subject or the
    body. A wrong code or a missing depart date is not verified. Never raises.
    """
    try:
        return _verify(email, segment, confirmation_code, travelers)
    except Exception:
        return _result(_segment_id(segment), False, "email could not be read")


def _sample_email(segment, confirmation_code, travelers, trip_id) -> dict:
    segment = segment if isinstance(segment, dict) else {}
    origin = _text(segment.get("from"))
    destination = _text(segment.get("to"))
    depart = _text(segment.get("departDate"))
    code = _text(confirmation_code)
    trip = _text(trip_id)
    names = _collect_names(segment, travelers)

    subject_parts = ["Flight confirmation"]
    if code:
        subject_parts.append(code)
    if origin and destination:
        subject_parts.append(f"{origin} to {destination}")
    if depart:
        subject_parts.append(depart)

    lines = [
        "Your flight is confirmed.",
        "",
        f"Confirmation code: {code}" if code else "Confirmation code:",
        f"From: {origin}" if origin else "From:",
        f"To: {destination}" if destination else "To:",
        f"Depart date: {depart}" if depart else "Depart date:",
        "Travelers: " + ", ".join(names) if names else "Travelers:",
    ]
    if trip:
        lines.append(f"Trip: {trip}")
    lines.extend(["", "This sandbox message was not delivered."])
    return {
        "from": _SENDER,
        "to": _recipients(travelers),
        "subject": " ".join(subject_parts),
        "body": "\n".join(lines),
        "receivedAt": _received_at(),
    }


def _verify(email, segment, confirmation_code, travelers) -> dict:
    segment_id = _segment_id(segment)
    parts = _subject_and_body(email)
    if parts is None:
        return _result(segment_id, False, "email could not be read")
    subject, body = parts

    reasons: list[str] = []
    code = _text(confirmation_code)
    if not code:
        reasons.append("confirmation code is missing")
    elif not _appears(code, subject, body):
        reasons.append("confirmation code was not in the email")

    origin, destination = _route(segment)
    if not origin or not destination:
        reasons.append("route is missing")
    else:
        if not _appears(origin, subject, body):
            reasons.append("origin was not in the email")
        if not _appears(destination, subject, body):
            reasons.append("destination was not in the email")

    depart = _text(segment.get("departDate")) if isinstance(segment, dict) else ""
    if not depart:
        reasons.append("depart date is missing")
    elif not _appears(depart, subject, body):
        reasons.append("depart date was not in the email")

    reasons.extend(_name_reasons(segment, travelers, subject, body))
    if reasons:
        return _result(segment_id, False, "; ".join(reasons))
    return _result(segment_id, True, _SUCCESS)


def _name_reasons(segment, travelers, subject: str, body: str) -> list[str]:
    if not isinstance(travelers, list):
        return ["travelers must be a list"]
    chosen, missing_ids = _select_travelers(segment, travelers)
    if missing_ids:
        return [f"traveler {missing_ids[0]} was not provided"]
    if not chosen:
        return ["traveler names are missing"]
    names: list[str] = []
    for traveler in chosen:
        name = _display_name(traveler)
        if not name:
            return ["traveler names are missing"]
        names.append(name)
    missing = [name for name in names if not _appears(name, subject, body)]
    if missing:
        return ["traveler names were not in the email: " + ", ".join(missing)]
    return []


def _select_travelers(segment, travelers: list) -> tuple[list, list[str]]:
    """Travelers on the segment, plus any requested ids that were not provided."""
    if not isinstance(segment, dict) or not isinstance(segment.get("travelerIds"), list):
        return list(travelers), []
    ids = [item.strip() for item in segment["travelerIds"] if isinstance(item, str) and item.strip()]
    if not ids:
        return list(travelers), []
    index: dict[str, dict] = {}
    for traveler in travelers:
        if not isinstance(traveler, dict):
            continue
        traveler_id = traveler.get("id", traveler.get("travelerId"))
        if isinstance(traveler_id, str) and traveler_id.strip():
            index.setdefault(traveler_id.strip(), traveler)
    missing = [traveler_id for traveler_id in ids if traveler_id not in index]
    chosen = [index[traveler_id] for traveler_id in ids if traveler_id in index]
    return chosen, missing


def _collect_names(segment, travelers) -> list[str]:
    if not isinstance(travelers, list):
        return []
    chosen, _missing = _select_travelers(segment, travelers)
    names = []
    for traveler in chosen:
        name = _display_name(traveler)
        if name:
            names.append(name)
    return names


def _display_name(traveler: object) -> str | None:
    if isinstance(traveler, str) and traveler.strip():
        return " ".join(traveler.split())
    if not isinstance(traveler, dict):
        return None
    name = traveler.get("name")
    if isinstance(name, str) and name.strip():
        return " ".join(name.split())
    given = traveler.get("givenName")
    family = traveler.get("familyName")
    if (
        isinstance(given, str)
        and given.strip()
        and isinstance(family, str)
        and family.strip()
    ):
        return f"{given.strip()} {family.strip()}"
    return None


def _recipients(travelers) -> str:
    found: list[str] = []
    if isinstance(travelers, list):
        for traveler in travelers:
            if not isinstance(traveler, dict):
                continue
            address = traveler.get("email")
            if isinstance(address, str) and _EMAIL.fullmatch(address.strip()):
                found.append(address.strip())
    if not found:
        return _DEFAULT_RECIPIENT
    return ", ".join(found)


def _route(segment) -> tuple[str, str]:
    if not isinstance(segment, dict):
        return "", ""
    return _text(segment.get("from")), _text(segment.get("to"))


def _subject_and_body(email) -> tuple[str, str] | None:
    if not isinstance(email, dict):
        return None
    subject = email.get("subject")
    body = email.get("body")
    subject_ok = isinstance(subject, str)
    body_ok = isinstance(body, str)
    if not subject_ok and not body_ok:
        return None
    return (subject if subject_ok else "", body if body_ok else "")


def _appears(needle: str, subject: str, body: str) -> bool:
    return _in_text(needle, subject) or _in_text(needle, body)


def _in_text(needle: str, text: str) -> bool:
    """True when needle is present and not only a prefix of a longer token.

    Letters, digits, and hyphens stay inside a token, so ``SANDBOX-FLIGHT``
    does not match ``SANDBOX-FLIGHT-001``.
    """
    if not needle or not isinstance(text, str):
        return False
    pattern = re.compile(
        rf"(?:^|(?<=[^A-Za-z0-9-])){re.escape(needle)}(?:$|(?=[^A-Za-z0-9-]))"
    )
    return pattern.search(text) is not None


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _segment_id(segment) -> str:
    if isinstance(segment, dict) and isinstance(segment.get("segmentId"), str):
        return segment["segmentId"]
    return ""


def _received_at() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(segment_id: str, verified: bool, reason: str) -> dict:
    return {
        "segmentId": segment_id,
        "kind": "flight",
        "verified": verified,
        "reason": reason,
    }
