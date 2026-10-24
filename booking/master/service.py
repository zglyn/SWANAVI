"""Control loop for one finished trip plan.

The loop calls capability tools. It does not book a supplier itself, parse
confirmation mail, decide how to shift the day, or decide a guard outcome.
One replan agent is called per disruption event. Those agents live in
booking.replan. Budget, spend, refund, conflict, and notice tools live in
their own packages.
"""

from __future__ import annotations

import copy
import logging
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError

from booking.contract import TripPlan
from booking.master.capabilities import (
    PROGRESS_NOT_INSTALLED,
    REPLAN_NOT_INSTALLED,
    ProgressNotInstalled,
    load_trip_progress,
)
from booking.master.tools import (
    BOOK_TOOLS,
    REPLAN_TOOLS,
    VERIFY_TOOLS,
    authorize_spend,
    check_budget,
    check_conflicts,
    refund_booking,
    trip_notice,
    trip_progress,
)

logger = logging.getLogger(__name__)

MAX_TICKS = 5
_STATUSES = {"booked", "failed", "needs_user"}
_ACTIONS = {"none", "rebook", "verify_email", "replan"}
_REPLAN_EVENTS = {"cancelled", "ended_early", "ended_late"}
_KINDS = ("flight", "hotel", "attraction")
_LISTS = {"flight": "flights", "hotel": "hotels", "attraction": "attractions"}


def segment_accepted(result: dict[str, Any]) -> bool:
    """True only when the booking status is booked and email verification passed."""

    return result.get("status") == "booked" and result.get("emailVerified") is True


def handle_payload(payload: object) -> dict[str, Any]:
    """Run the master loop for a trip plan. Invalid input does not raise."""

    if not isinstance(payload, dict):
        return _envelope(None, [], [], "invalid_plan", "invalid_plan")
    try:
        TripPlan.model_validate(payload)
    except ValidationError:
        logger.info("Rejected trip plan that does not match the booking contract")
        trip_id = payload.get("tripId")
        return _envelope(
            trip_id if isinstance(trip_id, str) else None,
            [],
            [],
            "invalid_plan",
            "invalid_plan",
        )
    return run_plan(payload)


def run_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Book, verify booked segments, then tick trip_progress at most five times."""

    plan = copy.deepcopy(payload)
    travelers = plan.get("travelers") if isinstance(plan.get("travelers"), list) else []
    trip_id = plan.get("tripId") if isinstance(plan.get("tripId"), str) else ""
    segments = list(_segments(plan))

    results: list[dict[str, Any]] = []
    located: dict[str, list[dict[str, Any]]] = {}
    for kind, segment in segments:
        result, price = _book_and_verify(kind, segment, travelers, trip_id)
        results.append(result)
        located.setdefault(result["segmentId"], []).append(
            {"kind": kind, "segment": segment, "index": len(results) - 1, "price": price}
        )

    ticks, stopped, spend = _control_loop(plan, results, located, travelers, trip_id)
    return _envelope(trip_id, results, ticks, stopped, None, spend)


def _book_and_verify(
    kind: str,
    segment: dict[str, Any],
    travelers: list[Any],
    trip_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    raw = BOOK_TOOLS[kind](segment, travelers, trip_id)
    price = raw.get("price") if isinstance(raw, dict) and isinstance(raw.get("price"), dict) else None
    result = _normalize_booking(raw, segment["segmentId"], kind)
    if result["status"] == "booked" and isinstance(result["confirmationCode"], str):
        checked = VERIFY_TOOLS[kind](segment, result["confirmationCode"], travelers, trip_id)
        result["emailVerified"] = checked["verified"] is True
        result["reason"] = checked["reason"]
    _apply_budget(result, segment, price, trip_id)
    return result, price


def _control_loop(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    located: dict[str, list[dict[str, Any]]],
    travelers: list[Any],
    trip_id: str,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    ticks: list[dict[str, Any]] = []
    spend, spend_notice = _scripted_spend(trip_id)
    held: list[Any] = [spend_notice] if spend_notice is not None else []

    def finish(tick: dict[str, Any], more: list[Any] | None = None) -> dict[str, Any]:
        notices = [*held, *(more or [])]
        held.clear()
        if notices:
            tick["notice"] = notices[0] if len(notices) == 1 else notices
        return tick

    if load_trip_progress() is None:
        clock = _clock(plan, 1)
        ticks.append(finish(_tick(1, clock, None, None, [_update(None, None, PROGRESS_NOT_INSTALLED, "none")])))
        return ticks, PROGRESS_NOT_INSTALLED, spend

    stopped = "max_ticks"
    for number in range(1, MAX_TICKS + 1):
        clock = _clock(plan, number)
        try:
            report = trip_progress(copy.deepcopy(plan), copy.deepcopy(results), clock)
        except ProgressNotInstalled:
            ticks.append(finish(_tick(number, clock, None, None, [_update(None, None, PROGRESS_NOT_INSTALLED, "none")])))
            return ticks, PROGRESS_NOT_INSTALLED, spend
        except Exception as exc:
            logger.warning("trip_progress failed on tick %s: %s", number, exc)
            message = str(exc).strip() or exc.__class__.__name__
            ticks.append(finish(_tick(number, clock, None, None, [_update(None, None, message, "none")])))
            return ticks, "progress_error", spend

        if not isinstance(report, dict):
            ticks.append(finish(_tick(number, clock, None, None, [_update(None, None, "invalid_progress_result", "none")])))
            return ticks, "progress_error", spend

        phase = report.get("phase") if isinstance(report.get("phase"), str) else None
        on_track = report.get("onTrack") if isinstance(report.get("onTrack"), bool) else None
        raw_updates = report.get("updates") if isinstance(report.get("updates"), list) else []
        updates = [_normalize_update(item) for item in raw_updates]
        tick = _tick(number, clock, phase, on_track, updates)

        acted = False
        notices: list[Any] = []
        for update in updates:
            if update["action"] == "rebook":
                acted = True
                _rebook(update, located, results, travelers, trip_id)
            elif update["action"] == "verify_email":
                acted = True
                _verify_again(update, located, results, travelers, trip_id)
            elif update["action"] == "replan" and _replan(update, plan, located, results, trip_id, clock):
                notices.append(_replan_notice(trip_id, update))
        ticks.append(finish(tick, notices))
        if on_track is True and not acted:
            stopped = "on_track"
            break
    return ticks, stopped, spend


def _replan(
    update: dict[str, Any],
    plan: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    trip_id: str,
    clock: dict[str, Any],
) -> bool:
    """Call one replan agent for this event. A missing package does not end the loop.

    Returns True when this update was a replan the master handled, so the loop
    can notify the traveler. Refunds a cancelled segment. Checks conflicts
    only after a replan that changed the plan.
    """

    event = update.get("event")
    tool = REPLAN_TOOLS.get(event) if isinstance(event, str) else None
    if tool is None:
        return False
    disruption = {
        "segmentId": update.get("segmentId"),
        "kind": update.get("kind"),
        "event": event,
        "deltaMinutes": update.get("deltaMinutes"),
    }
    try:
        raw = tool(trip_id, _now(clock), copy.deepcopy(plan), disruption)
    except Exception as exc:
        logger.warning("replan %s failed on %s: %s", event, update.get("segmentId"), exc)
        update["replan"] = "unchanged"
        _refund_if_cancelled(update, located, results, trip_id)
        return True
    if not isinstance(raw, dict):
        update["replan"] = "unchanged"
        _refund_if_cancelled(update, located, results, trip_id)
        return True
    if raw.get("changed") is True and isinstance(raw.get("plan"), dict):
        _replace_plan(plan, raw["plan"], located)
        update["replan"] = "changed"
        update["notes"] = _recorded_notes(raw.get("notes"))
        update["conflicts"] = check_conflicts(trip_id, copy.deepcopy(plan))
        _refund_if_cancelled(update, located, results, trip_id)
        return True
    if raw.get("error") == REPLAN_NOT_INSTALLED:
        update["replan"] = REPLAN_NOT_INSTALLED
        _refund_if_cancelled(update, located, results, trip_id)
        return True
    update["replan"] = "unchanged"
    _refund_if_cancelled(update, located, results, trip_id)
    return True


def _replace_plan(
    plan: dict[str, Any],
    replacement: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
) -> None:
    """Swap in the plan a replan agent returned, and point later rebooks at it."""

    incoming = copy.deepcopy(replacement)
    plan.clear()
    plan.update(incoming)
    current: dict[str, dict[str, Any]] = {}
    for _kind, segment in _segments(plan):
        segment_id = segment.get("segmentId")
        if isinstance(segment_id, str):
            current[segment_id] = segment
    for segment_id, matches in located.items():
        segment = current.get(segment_id)
        if segment is None:
            continue
        for match in matches:
            match["segment"] = copy.deepcopy(segment)


def _recorded_notes(notes: object) -> str | list[str]:
    if isinstance(notes, str):
        return notes
    if isinstance(notes, list):
        return [item for item in notes if isinstance(item, str)]
    return []


def _now(clock: dict[str, Any]) -> str:
    now = clock.get("now") if isinstance(clock, dict) else None
    return now if isinstance(now, str) else ""


def _rebook(
    update: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    travelers: list[Any],
    trip_id: str,
) -> None:
    """Call that segment's book_* tool again. Rebook does not edit the plan."""

    matches = located.get(update["segmentId"] or "")
    if not matches:
        return
    for match in matches:
        kind = match["kind"]
        segment = match["segment"]
        raw = BOOK_TOOLS[kind](segment, travelers, trip_id)
        price = raw.get("price") if isinstance(raw, dict) and isinstance(raw.get("price"), dict) else None
        booked = _normalize_booking(raw, segment["segmentId"], kind)
        if booked["status"] == "booked":
            booked["emailVerified"] = False
            booked["reason"] = "rebooked"
        match["price"] = price
        results[match["index"]] = booked


def _verify_again(
    update: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    travelers: list[Any],
    trip_id: str,
) -> None:
    matches = located.get(update["segmentId"] or "")
    if not matches:
        return
    for match in matches:
        result = results[match["index"]]
        code = result.get("confirmationCode")
        if result.get("status") != "booked" or not isinstance(code, str):
            result["emailVerified"] = False
            continue
        checked = VERIFY_TOOLS[match["kind"]](match["segment"], code, travelers, trip_id)
        result["emailVerified"] = checked["verified"] is True
        result["reason"] = checked["reason"]
        _apply_budget(result, match["segment"], match.get("price") if isinstance(match.get("price"), dict) else None, trip_id)


def _segments(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    ordered: list[tuple[str, dict[str, Any]]] = []
    for kind in _KINDS:
        items = plan.get(_LISTS[kind])
        if not isinstance(items, list):
            continue
        for segment in items:
            if isinstance(segment, dict):
                ordered.append((kind, dict(segment)))
    return ordered


def _normalize_booking(raw: object, segment_id: str, kind: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _segment(segment_id, kind, "failed", None, False, "invalid_provider_result")
    status = raw.get("status")
    if status not in _STATUSES:
        return _segment(segment_id, kind, "failed", None, False, "invalid_provider_result")
    error = raw.get("error")
    if isinstance(error, str) and error.strip():
        reason = error.strip()
    elif status == "booked":
        reason = "booked"
    else:
        reason = "not_booked"
    code = raw.get("confirmationCode")
    if status == "booked":
        if not isinstance(code, str) or not code.strip():
            return _segment(segment_id, kind, "failed", None, False, "missing_confirmation")
        code = code.strip()
    else:
        code = None
    return _segment(segment_id, kind, status, code, False, reason)


def _segment(
    segment_id: str,
    kind: str,
    status: str,
    confirmation_code: str | None,
    email_verified: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "segmentId": segment_id,
        "kind": kind,
        "status": status,
        "confirmationCode": confirmation_code,
        "emailVerified": email_verified,
        "reason": reason,
    }


def _normalize_update(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _update(None, None, "invalid_update", "none")
    action = raw.get("action")
    if action not in _ACTIONS:
        action = "none"
    segment_id = raw.get("segmentId") if isinstance(raw.get("segmentId"), str) and raw.get("segmentId") else None
    kind = raw.get("kind") if raw.get("kind") in _KINDS else None
    issue = raw.get("issue") if isinstance(raw.get("issue"), str) else ""
    update = _update(segment_id, kind, issue, action)
    event = raw.get("event")
    if action == "replan" and event in _REPLAN_EVENTS:
        update["event"] = event
        update["deltaMinutes"] = _delta_minutes(raw.get("deltaMinutes"))
    return update


def _delta_minutes(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _update(segment_id: str | None, kind: str | None, issue: str, action: str) -> dict[str, Any]:
    return {"segmentId": segment_id, "kind": kind, "issue": issue, "action": action}


def _tick(
    number: int,
    clock: dict[str, Any],
    phase: str | None,
    on_track: bool | None,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "tick": number,
        "clock": clock,
        "phase": phase,
        "onTrack": on_track,
        "updates": updates,
    }


def _clock(plan: dict[str, Any], tick: int) -> dict[str, Any]:
    """Simulated clock. Tick 1 is 08:00Z on the trip start date. Each tick adds three hours."""

    start = date(2026, 1, 1)
    dates = plan.get("dates")
    if isinstance(dates, dict) and isinstance(dates.get("start"), str):
        try:
            start = date.fromisoformat(dates["start"])
        except ValueError:
            start = date(2026, 1, 1)
    hour = 8 + (tick - 1) * 3
    moment = start + timedelta(days=hour // 24)
    clock_hour = hour % 24
    return {"tick": tick, "now": f"{moment.isoformat()}T{clock_hour:02d}:00:00Z"}


def _apply_budget(
    result: dict[str, Any],
    segment: dict[str, Any],
    price: dict[str, Any] | None,
    trip_id: str,
) -> None:
    """Ask check_budget before accepting a booked, email-verified segment.

    A missing package is recorded and the segment stays accepted. allowed false
    sets status to needs_user, so segment_accepted is false.
    """

    if result.get("status") != "booked" or result.get("emailVerified") is not True:
        return
    outcome = check_budget(trip_id, copy.deepcopy(segment), copy.deepcopy(price) if isinstance(price, dict) else None)
    result["budget"] = outcome
    if isinstance(outcome, dict) and outcome.get("allowed") is False:
        result["status"] = "needs_user"


def _scripted_spend(trip_id: str) -> tuple[dict[str, Any], Any | None]:
    """Authorize the scripted demo charge and notice an over-capture rejection."""

    record = authorize_spend()
    if record.get("reason") != "over_capture_rejected":
        return record, None
    notice = trip_notice(
        trip_id,
        {
            "type": "over_capture_rejected",
            "authorizedAmount": record.get("authorizedAmount"),
            "requestedAmount": record.get("requestedAmount"),
            "currency": record.get("currency"),
            "payAmount": record.get("payAmount"),
        },
    )
    return record, notice


def _refund_if_cancelled(
    update: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    trip_id: str,
) -> None:
    if update.get("event") != "cancelled":
        return
    segment_id = update.get("segmentId") if isinstance(update.get("segmentId"), str) else None
    update["refund"] = refund_booking(trip_id, segment_id, _confirmation_code(segment_id, located, results))


def _confirmation_code(
    segment_id: str | None,
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
) -> str | None:
    if not segment_id:
        return None
    for match in located.get(segment_id) or []:
        result = results[match["index"]]
        code = result.get("confirmationCode")
        if isinstance(code, str):
            return code
    return None


def _replan_notice(trip_id: str, update: dict[str, Any]) -> Any:
    return trip_notice(
        trip_id,
        {
            "type": "replan",
            "segmentId": update.get("segmentId"),
            "kind": update.get("kind"),
            "event": update.get("event"),
            "replan": update.get("replan"),
            "notes": update.get("notes", []),
        },
    )


def _envelope(
    trip_id: str | None,
    results: list[dict[str, Any]],
    ticks: list[dict[str, Any]],
    loop_stopped: str,
    error: str | None,
    spend: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "tripId": trip_id,
        "results": results,
        "ticks": ticks,
        "maxTicks": MAX_TICKS,
        "loopStopped": loop_stopped,
        "error": error,
    }
    if spend is not None:
        body["spend"] = spend
    return body
