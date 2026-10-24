"""Tool names the master calls.

Each function forwards to a capability package. None of them books a supplier,
parses an inbox, or decides whether the trip is on track.
"""

from __future__ import annotations

from typing import Any

from booking.master.capabilities import (
    PROGRESS_NOT_INSTALLED,
    PROVIDER_NOT_INSTALLED,
    VERIFIER_NOT_INSTALLED,
    ProgressNotInstalled,
    load_book,
    load_trip_progress,
    load_verifier,
)

BOOK_TOOL_BY_KIND = {
    "flight": "book_flight",
    "hotel": "book_hotel",
    "attraction": "book_attraction",
}

VERIFY_TOOL_BY_KIND = {
    "flight": "verify_flight_email",
    "hotel": "verify_hotel_email",
    "attraction": "verify_attraction_email",
}


def _message(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _failed(segment: dict[str, Any], kind: str, error: str) -> dict[str, Any]:
    segment_id = segment.get("segmentId") if isinstance(segment, dict) else None
    return {
        "segmentId": segment_id if isinstance(segment_id, str) else None,
        "kind": kind,
        "status": "failed",
        "confirmationCode": None,
        "price": None,
        "error": error,
    }


def call_book(kind: str, segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call book_flight, book_hotel, or book_attraction."""

    book = load_book(kind)
    if book is None:
        return _failed(segment, kind, PROVIDER_NOT_INSTALLED)
    try:
        raw = book(segment, travelers, trip_id)
    except Exception as exc:
        return _failed(segment, kind, _message(exc))
    if not isinstance(raw, dict):
        return _failed(segment, kind, "invalid_provider_result")
    return raw


def book_flight(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call booking.providers.flights."""

    return call_book("flight", segment, travelers, trip_id)


def book_hotel(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call booking.providers.hotels."""

    return call_book("hotel", segment, travelers, trip_id)


def book_attraction(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> dict[str, Any]:
    """Call booking.providers.attractions."""

    return call_book("attraction", segment, travelers, trip_id)


def call_verify(
    kind: str,
    segment: dict[str, Any],
    confirmation_code: str,
    travelers: list[Any],
    trip_id: str,
) -> dict[str, Any]:
    """Sandbox path: sample_email, then verify. A real inbox is never read."""

    segment_id = segment.get("segmentId") if isinstance(segment.get("segmentId"), str) else None
    verifier = load_verifier(kind)
    if verifier is None:
        return {
            "segmentId": segment_id,
            "kind": kind,
            "verified": False,
            "reason": VERIFIER_NOT_INSTALLED,
        }
    sample_email, verify = verifier
    try:
        email = sample_email(segment, confirmation_code, travelers, trip_id)
    except Exception as exc:
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": _message(exc)}
    if not isinstance(email, dict):
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": "invalid_email"}
    try:
        outcome = verify(email, segment, confirmation_code, travelers)
    except Exception as exc:
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": _message(exc)}
    if not isinstance(outcome, dict):
        return {"segmentId": segment_id, "kind": kind, "verified": False, "reason": "invalid_verifier_result"}
    verified = outcome.get("verified") is True
    reason = outcome.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "verified" if verified else "not_verified"
    return {
        "segmentId": outcome.get("segmentId") if isinstance(outcome.get("segmentId"), str) else segment_id,
        "kind": kind,
        "verified": verified,
        "reason": reason.strip(),
    }


def verify_flight_email(
    segment: dict[str, Any], confirmation_code: str, travelers: list[Any], trip_id: str
) -> dict[str, Any]:
    """Call booking.verify.flights. Sandbox uses sample_email, then verify."""

    return call_verify("flight", segment, confirmation_code, travelers, trip_id)


def verify_hotel_email(
    segment: dict[str, Any], confirmation_code: str, travelers: list[Any], trip_id: str
) -> dict[str, Any]:
    """Call booking.verify.hotels. Sandbox uses sample_email, then verify."""

    return call_verify("hotel", segment, confirmation_code, travelers, trip_id)


def verify_attraction_email(
    segment: dict[str, Any], confirmation_code: str, travelers: list[Any], trip_id: str
) -> dict[str, Any]:
    """Call booking.verify.attractions. Sandbox uses sample_email, then verify."""

    return call_verify("attraction", segment, confirmation_code, travelers, trip_id)


def trip_progress(plan: dict[str, Any], results: list[dict[str, Any]], clock: dict[str, Any]) -> Any:
    """Call booking.progress.trip_progress.

    Raises ProgressNotInstalled when that function is not importable.
    """

    progress = load_trip_progress()
    if progress is None:
        raise ProgressNotInstalled(PROGRESS_NOT_INSTALLED)
    return progress(plan, results, clock)


BOOK_TOOLS = {
    "flight": book_flight,
    "hotel": book_hotel,
    "attraction": book_attraction,
}

VERIFY_TOOLS = {
    "flight": verify_flight_email,
    "hotel": verify_hotel_email,
    "attraction": verify_attraction_email,
}

RUNTIME_TOOLS = {
    "book_flight": book_flight,
    "book_hotel": book_hotel,
    "book_attraction": book_attraction,
    "verify_flight_email": verify_flight_email,
    "verify_hotel_email": verify_hotel_email,
    "verify_attraction_email": verify_attraction_email,
    "trip_progress": trip_progress,
}
