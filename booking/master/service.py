"""Control loop for one finished trip plan.

The loop calls capability tools. It does not book a supplier itself, parse
confirmation mail, or decide how to shift the day. One replan agent is called
per disruption event. Those agents live in booking.replan.
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
from booking.master.tools import BOOK_TOOLS, REPLAN_TOOLS, VERIFY_TOOLS, trip_progress

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
        result = _book_and_verify(kind, segment, travelers, trip_id)
        results.append(result)
        located.setdefault(result["segmentId"], []).append(
            {"kind": kind, "segment": segment, "index": len(results) - 1}
        )

    ticks, stopped = _control_loop(plan, results, located, travelers, trip_id)
    return _envelope(trip_id, results, ticks, stopped, None)


def _book_and_verify(
    kind: str,
    segment: dict[str, Any],
    travelers: list[Any],
    trip_id: str,
) -> dict[str, Any]:
    result = _normalize_booking(BOOK_TOOLS[kind](segment, travelers, trip_id), segment["segmentId"], kind)
    if result["status"] == "booked" and isinstance(result["confirmationCode"], str):
        checked = VERIFY_TOOLS[kind](segment, result["confirmationCode"], travelers, trip_id)
        result["emailVerified"] = checked["verified"] is True
        result["reason"] = checked["reason"]
    return result


def _control_loop(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    located: dict[str, list[dict[str, Any]]],
    travelers: list[Any],
    trip_id: str,
) -> tuple[list[dict[str, Any]], str]:
    ticks: list[dict[str, Any]] = []
    if load_trip_progress() is None:
        clock = _clock(plan, 1)
        ticks.append(_tick(1, clock, None, None, [_update(None, None, PROGRESS_NOT_INSTALLED, "none")]))
        return ticks, PROGRESS_NOT_INSTALLED

    stopped = "max_ticks"
    for number in range(1, MAX_TICKS + 1):
        clock = _clock(plan, number)
        try:
            report = trip_progress(copy.deepcopy(plan), copy.deepcopy(results), clock)
        except ProgressNotInstalled:
            ticks.append(_tick(number, clock, None, None, [_update(None, None, PROGRESS_NOT_INSTALLED, "none")]))
            return ticks, PROGRESS_NOT_INSTALLED
        except Exception as exc:
            logger.warning("trip_progress failed on tick %s: %s", number, exc)
            message = str(exc).strip() or exc.__class__.__name__
            ticks.append(_tick(number, clock, None, None, [_update(None, None, message, "none")]))
            return ticks, "progress_error"

        if not isinstance(report, dict):
            ticks.append(_tick(number, clock, None, None, [_update(None, None, "invalid_progress_result", "none")]))
            return ticks, "progress_error"

        phase = report.get("phase") if isinstance(report.get("phase"), str) else None
        on_track = report.get("onTrack") if isinstance(report.get("onTrack"), bool) else None
        raw_updates = report.get("updates") if isinstance(report.get("updates"), list) else []
        updates = [_normalize_update(item) for item in raw_updates]
        ticks.append(_tick(number, clock, phase, on_track, updates))

        acted = False
        for update in updates:
            if update["action"] == "rebook":
                acted = True
                _rebook(update, located, results, travelers, trip_id)
            elif update["action"] == "verify_email":
                acted = True
                _verify_again(update, located, results, travelers, trip_id)
            elif update["action"] == "replan":
                _replan(update, plan, located, trip_id, clock)
        if on_track is True and not acted:
            stopped = "on_track"
            break
    return ticks, stopped


def _replan(
    update: dict[str, Any],
    plan: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    trip_id: str,
    clock: dict[str, Any],
) -> None:
    """Call one replan agent for this event. A missing package does not end the loop."""

    event = update.get("event")
    tool = REPLAN_TOOLS.get(event) if isinstance(event, str) else None
    if tool is None:
        return
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
        return
    if not isinstance(raw, dict):
        update["replan"] = "unchanged"
        return
    if raw.get("changed") is True and isinstance(raw.get("plan"), dict):
        _replace_plan(plan, raw["plan"], located)
        update["replan"] = "changed"
        update["notes"] = _recorded_notes(raw.get("notes"))
        return
    if raw.get("error") == REPLAN_NOT_INSTALLED:
        update["replan"] = REPLAN_NOT_INSTALLED
        return
    update["replan"] = "unchanged"


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
        booked = _normalize_booking(BOOK_TOOLS[kind](segment, travelers, trip_id), segment["segmentId"], kind)
        if booked["status"] == "booked":
            booked["emailVerified"] = False
            booked["reason"] = "rebooked"
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


def _envelope(
    trip_id: str | None,
    results: list[dict[str, Any]],
    ticks: list[dict[str, Any]],
    loop_stopped: str,
    error: str | None,
) -> dict[str, Any]:
    return {
        "tripId": trip_id,
        "results": results,
        "ticks": ticks,
        "maxTicks": MAX_TICKS,
        "loopStopped": loop_stopped,
        "error": error,
    }
