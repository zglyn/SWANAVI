"""Tool names the master calls.

Each function forwards to a capability package. None of them books a supplier,
parses an inbox, decides whether the trip is on track, shifts the day, or
decides a guard outcome.
"""

from __future__ import annotations

import inspect
from typing import Any

from booking.master.capabilities import (
    AUTHORIZE_SPEND_NOT_INSTALLED,
    CHECK_BUDGET_NOT_INSTALLED,
    CHECK_CONFLICTS_NOT_INSTALLED,
    PROGRESS_NOT_INSTALLED,
    PROVIDER_NOT_INSTALLED,
    REFUND_BOOKING_NOT_INSTALLED,
    REPLAN_NOT_INSTALLED,
    TRIP_NOTICE_NOT_INSTALLED,
    VERIFIER_NOT_INSTALLED,
    ProgressNotInstalled,
    load_authorize_spend,
    load_book,
    load_check_budget,
    load_check_conflicts,
    load_refund_booking,
    load_replan,
    load_trip_notice,
    load_trip_progress,
    load_verifier,
)

# One scripted demo charge. The spend guard decides payAmount and reason.
SCRIPTED_AUTHORIZED_AMOUNT = 10
SCRIPTED_REQUESTED_AMOUNT = 12
SCRIPTED_CURRENCY = "USD"

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


def _call_replan(
    event: str,
    trip_id: str,
    now: str,
    plan: dict[str, Any],
    disruption: dict[str, Any],
) -> Any:
    """Forward one disruption to that event's replan agent."""

    replan = load_replan(event)
    if replan is None:
        return {
            "changed": False,
            "plan": None,
            "notes": [],
            "error": REPLAN_NOT_INSTALLED,
        }
    return replan(trip_id, now, plan, disruption)


def replan_cancel(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> Any:
    """Call booking.replan.cancel.replan_cancel. One agent for a cancellation."""

    return _call_replan("cancelled", trip_id, now, plan, disruption)


def replan_early(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> Any:
    """Call booking.replan.early.replan_early. One agent for an early finish."""

    return _call_replan("ended_early", trip_id, now, plan, disruption)


def replan_late(trip_id: str, now: str, plan: dict[str, Any], disruption: dict[str, Any]) -> Any:
    """Call booking.replan.late.replan_late. One agent for a late finish."""

    return _call_replan("ended_late", trip_id, now, plan, disruption)


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

REPLAN_TOOLS = {
    "cancelled": replan_cancel,
    "ended_early": replan_early,
    "ended_late": replan_late,
}


def check_budget(trip_id: str, segment: dict[str, Any], price: dict[str, Any] | None) -> Any:
    """Call booking.guard.budget.check_budget before a booked segment is accepted.

    Returns the tool result, or ``check_budget_not_installed`` when that
    function cannot be imported.
    """

    budget = load_check_budget()
    if budget is None:
        return CHECK_BUDGET_NOT_INSTALLED
    try:
        return _call_budget(budget, trip_id, segment, price)
    except Exception as exc:
        return {"allowed": None, "error": _message(exc)}


def authorize_spend(
    authorizedAmount: int = SCRIPTED_AUTHORIZED_AMOUNT,
    requestedAmount: int = SCRIPTED_REQUESTED_AMOUNT,
    currency: str = SCRIPTED_CURRENCY,
) -> dict[str, Any]:
    """Call booking.guard.spend.authorize_spend for the scripted demo charge.

    The master passes authorizedAmount 10, requestedAmount 12, and currency USD.
    payAmount and reason are whatever that tool returns.
    """

    record: dict[str, Any] = {
        "authorizedAmount": authorizedAmount,
        "requestedAmount": requestedAmount,
        "currency": currency,
    }
    spend = load_authorize_spend()
    if spend is None:
        record["payAmount"] = None
        record["reason"] = AUTHORIZE_SPEND_NOT_INSTALLED
        return record
    try:
        # The spend package names these fields. Positional order is segmentId, currency, then the amounts.
        raw = spend(authorizedAmount=authorizedAmount, requestedAmount=requestedAmount, currency=currency)
    except Exception as exc:
        record["payAmount"] = None
        record["reason"] = _message(exc)
        return record
    if not isinstance(raw, dict):
        record["payAmount"] = None
        record["reason"] = "invalid_spend_result"
        return record
    record.update(raw)
    record.setdefault("payAmount", None)
    record.setdefault("reason", None)
    return record


def refund_booking(
    trip_id: str,
    segment_id: str | None,
    confirmation_code: str | None,
    amount: Any = None,
    currency: str | None = None,
) -> Any:
    """Call booking.refund.refund_booking when a segment is cancelled."""

    refund = load_refund_booking()
    if refund is None:
        return REFUND_BOOKING_NOT_INSTALLED
    try:
        raw = _call_refund(refund, trip_id, segment_id, confirmation_code, amount, currency)
    except Exception as exc:
        return {"error": _message(exc)}
    if not isinstance(raw, dict):
        return {"error": "invalid_refund_result"}
    return raw


def check_conflicts(trip_id: str, plan: dict[str, Any]) -> Any:
    """Call booking.guard.conflicts.check_conflicts after a replan changes the plan."""

    conflicts = load_check_conflicts()
    if conflicts is None:
        return CHECK_CONFLICTS_NOT_INSTALLED
    try:
        raw = conflicts(trip_id, plan)
    except Exception as exc:
        return {"error": _message(exc)}
    if not isinstance(raw, dict):
        return {"error": "invalid_conflicts_result"}
    return raw


def trip_notice(trip_id: str, event: dict[str, Any]) -> Any:
    """Call booking.notify.trip_notice after a replan or an over-capture rejection."""

    notice = load_trip_notice()
    if notice is None:
        return TRIP_NOTICE_NOT_INSTALLED
    try:
        return _call_notice(notice, trip_id, event)
    except Exception as exc:
        return {"error": _message(exc)}


_NOTICE_EVENTS = frozenset({"cancelled", "ended_early", "ended_late", "booked", "over_capture_rejected"})


def _param_names(fn: Any) -> list[str]:
    try:
        return list(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return []


def _call_budget(
    budget: Any,
    trip_id: str,
    segment: dict[str, Any],
    price: dict[str, Any] | None,
) -> Any:
    """booking.guard.budget.check_budget takes one source object, not three positional args."""

    if _param_names(budget)[:1] == ["source"]:
        return budget(_budget_source(trip_id, segment, price))
    return budget(trip_id, segment, price)


def _budget_source(trip_id: str, segment: dict[str, Any], price: dict[str, Any] | None) -> dict[str, Any]:
    """Quoted price is the proposed charge. The plan has no separate budget, so that quote is the cap."""

    currency = ""
    proposed = None
    if isinstance(price, dict):
        raw_currency = price.get("currency")
        if isinstance(raw_currency, str):
            currency = raw_currency
        if "amount" in price:
            proposed = price.get("amount")
    segment_currency = segment.get("currency")
    if isinstance(segment_currency, str) and segment_currency.strip():
        currency = segment_currency
    return {
        "tripId": trip_id,
        "currency": currency,
        "budgetAmount": segment.get("budgetAmount", proposed),
        "spentAmount": segment.get("spentAmount", "0"),
        "proposedAmount": segment.get("proposedAmount", proposed),
    }


def _call_refund(
    refund: Any,
    trip_id: str,
    segment_id: str | None,
    confirmation_code: str | None,
    amount: Any,
    currency: str | None,
) -> Any:
    """booking.refund.refund_booking is (segmentId, confirmationCode, amount, currency, event)."""

    if "confirmationCode" in _param_names(refund):
        return refund(segment_id, confirmation_code, amount, currency, "cancelled")
    return refund(trip_id, segment_id, confirmation_code)


def _call_notice(notice: Any, trip_id: str, event: dict[str, Any]) -> Any:
    """booking.notify.trip_notice reads tripId, event, notes, and segmentId."""

    names = _param_names(notice)
    if "tripId" in names and "trip_id" not in names:
        name, notes, segment_id = _notice_fields(event)
        return notice(tripId=trip_id, event=name, notes=notes, segmentId=segment_id)
    return notice(trip_id, event)


def _notice_fields(event: dict[str, Any]) -> tuple[str, Any, str]:
    raw_event = event.get("event")
    raw_type = event.get("type")
    if isinstance(raw_event, str) and raw_event in _NOTICE_EVENTS:
        name = raw_event
    elif isinstance(raw_type, str) and raw_type in _NOTICE_EVENTS:
        name = raw_type
    else:
        name = "update"
    segment_id = event.get("segmentId")
    if not isinstance(segment_id, str):
        segment_id = ""
    return name, event.get("notes"), segment_id


RUNTIME_TOOLS = {
    "book_flight": book_flight,
    "book_hotel": book_hotel,
    "book_attraction": book_attraction,
    "verify_flight_email": verify_flight_email,
    "verify_hotel_email": verify_hotel_email,
    "verify_attraction_email": verify_attraction_email,
    "trip_progress": trip_progress,
    "replan_cancel": replan_cancel,
    "replan_early": replan_early,
    "replan_late": replan_late,
    "check_budget": check_budget,
    "authorize_spend": authorize_spend,
    "refund_booking": refund_booking,
    "check_conflicts": check_conflicts,
    "trip_notice": trip_notice,
}
