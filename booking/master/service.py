"""Control loop for one finished trip plan.

The loop calls capability tools. It does not book a supplier itself, parse
confirmation mail, decide how to shift the day, decide a guard outcome, or
decide an assist outcome. One replan agent is called per disruption event.
Those agents live in booking.replan. Budget, spend, refund, conflict, notice,
and assist tools live in their own packages.
"""

from __future__ import annotations

import copy
import logging
from datetime import date, datetime, timedelta, timezone
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
    SCRIPTED_AUTHORIZED_AMOUNT,
    SCRIPTED_CURRENCY,
    SCRIPTED_EMERGENCY_COUNTRY,
    SCRIPTED_HOURS_CLOSE,
    SCRIPTED_HOURS_CLOSED_WEEKDAYS,
    SCRIPTED_HOURS_OPEN,
    SCRIPTED_PASSPORT_DAYS_AFTER_TRIP_END,
    SCRIPTED_REQUESTED_AMOUNT,
    SCRIPTED_TRAVEL_MINUTES,
    SCRIPTED_VISA_ON_FILE,
    SCRIPTED_WEATHER_CONDITION,
    VERIFY_TOOLS,
    after_dark,
    airport_leave,
    authorize_spend,
    check_budget,
    check_conflicts,
    check_entry,
    check_hours,
    check_transfer,
    check_weather,
    emergency_card,
    hold_table,
    late_checkout,
    luggage_drop,
    phrase_card,
    quote_fx,
    refund_booking,
    request_ride,
    tip_policy,
    trip_notice,
    trip_progress,
    trip_wallet,
    watch_trip,
)

logger = logging.getLogger(__name__)

MAX_TICKS = 5
_STATUSES = {"booked", "failed", "needs_user"}
_ACTIONS = {"none", "rebook", "verify_email", "replan"}
_REPLAN_EVENTS = {"cancelled", "ended_early", "ended_late"}
_KINDS = ("flight", "hotel", "attraction")
_LISTS = {"flight": "flights", "hotel": "hotels", "attraction": "attractions"}
_JAPAN = {"jp", "jpn", "japan"}
_OUTDOOR_WORDS = ("garden", "park", "outdoor", "walk")
_MEAL_WORDS = ("tea", "lunch", "dinner", "breakfast", "meal", "restaurant")
_RIDE_CODE_KEYS = ("rideCode", "code", "confirmationCode", "id")
_ASSIST_KEYS = (
    "entry",
    "emergency",
    "fx",
    "tip",
    "weather",
    "transfer",
    "luggage",
    "table",
    "checkout",
    "rides",
)


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
    assist = _prepare_assist(plan, trip_id)
    segments = list(_segments(plan))

    results: list[dict[str, Any]] = []
    located: dict[str, list[dict[str, Any]]] = {}
    for kind, segment in segments:
        result, price = _book_and_verify(kind, segment, travelers, trip_id)
        results.append(result)
        located.setdefault(result["segmentId"], []).append(
            {"kind": kind, "segment": segment, "index": len(results) - 1, "price": price}
        )

    ticks, stopped, spend = _control_loop(plan, results, located, travelers, trip_id, assist)
    return _envelope(trip_id, results, ticks, stopped, None, spend, assist)


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
    assist: dict[str, Any],
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    ticks: list[dict[str, Any]] = []
    spend, spend_notice, fx, tip = _scripted_spend(trip_id, assist)
    assist["fx"] = fx
    assist["tip"] = tip
    held: list[Any] = [spend_notice] if spend_notice is not None else []
    _handoff_weather_shift(assist, plan, located, results, trip_id, travelers, held)

    def finish(tick: dict[str, Any], more: list[Any] | None = None) -> dict[str, Any]:
        notices = [*held, *(more or [])]
        held.clear()
        if notices:
            tick["notice"] = notices[0] if len(notices) == 1 else notices
        tick["wallet"] = trip_wallet(trip_id, _known_codes(results, assist))
        return tick

    def open_tick(clock: dict[str, Any]) -> tuple[Any, list[dict[str, Any]], list[Any], list[dict[str, Any]]]:
        """Poll watch_trip and act on severity ``act`` before the rest of this tick."""

        notices: list[Any] = []
        assist["phraseCards"] = []
        started = len(assist["rides"])
        watch_record, warnings = _poll_watch(
            plan, clock, trip_id, assist, located, results, notices
        )
        assist["tickAirport"] = _airport_on_day(plan, clock, trip_id)
        assist["tickAfterDark"] = _after_dark_walks(plan, clock, trip_id, assist)
        _rides_for_ending(plan, clock, trip_id, assist)
        return watch_record, warnings, notices, assist["rides"][started:]

    if load_trip_progress() is None:
        clock = _clock(plan, 1)
        watch_record, warnings, notices, rides = open_tick(clock)
        tick = _tick(1, clock, None, None, [_update(None, None, PROGRESS_NOT_INSTALLED, "none")])
        _stamp_tick(tick, watch_record, warnings, rides, assist)
        ticks.append(finish(tick, notices))
        return ticks, PROGRESS_NOT_INSTALLED, spend

    stopped = "max_ticks"
    for number in range(1, MAX_TICKS + 1):
        clock = _clock(plan, number)
        watch_record, warnings, notices, rides = open_tick(clock)
        try:
            report = trip_progress(copy.deepcopy(plan), copy.deepcopy(results), clock)
        except ProgressNotInstalled:
            tick = _tick(number, clock, None, None, [_update(None, None, PROGRESS_NOT_INSTALLED, "none")])
            _stamp_tick(tick, watch_record, warnings, rides, assist)
            ticks.append(finish(tick, notices))
            return ticks, PROGRESS_NOT_INSTALLED, spend
        except Exception as exc:
            logger.warning("trip_progress failed on tick %s: %s", number, exc)
            message = str(exc).strip() or exc.__class__.__name__
            tick = _tick(number, clock, None, None, [_update(None, None, message, "none")])
            _stamp_tick(tick, watch_record, warnings, rides, assist)
            ticks.append(finish(tick, notices))
            return ticks, "progress_error", spend

        if not isinstance(report, dict):
            tick = _tick(number, clock, None, None, [_update(None, None, "invalid_progress_result", "none")])
            _stamp_tick(tick, watch_record, warnings, rides, assist)
            ticks.append(finish(tick, notices))
            return ticks, "progress_error", spend

        phase = report.get("phase") if isinstance(report.get("phase"), str) else None
        on_track = report.get("onTrack") if isinstance(report.get("onTrack"), bool) else None
        raw_updates = report.get("updates") if isinstance(report.get("updates"), list) else []
        updates = [_normalize_update(item) for item in raw_updates]
        tick = _tick(number, clock, phase, on_track, updates)

        acted = False
        for update in updates:
            if update["action"] == "rebook":
                acted = True
                _rebook(update, located, results, travelers, trip_id)
            elif update["action"] == "verify_email":
                acted = True
                _verify_again(update, located, results, travelers, trip_id)
            elif update["action"] == "replan" and _replan(update, plan, located, results, trip_id, clock):
                notices.append(_replan_notice(trip_id, update))
        _stamp_tick(tick, watch_record, warnings, rides, assist)
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
        return _note_hours(update, plan)
    if not isinstance(raw, dict):
        update["replan"] = "unchanged"
        _refund_if_cancelled(update, located, results, trip_id)
        return _note_hours(update, plan)
    if raw.get("changed") is True and isinstance(raw.get("plan"), dict):
        _replace_plan(plan, raw["plan"], located)
        update["replan"] = "changed"
        update["notes"] = _recorded_notes(raw.get("notes"))
        update["conflicts"] = check_conflicts(trip_id, copy.deepcopy(plan))
        _refund_if_cancelled(update, located, results, trip_id)
        return _note_hours(update, plan)
    if raw.get("error") == REPLAN_NOT_INSTALLED:
        update["replan"] = REPLAN_NOT_INSTALLED
        _refund_if_cancelled(update, located, results, trip_id)
        return _note_hours(update, plan)
    update["replan"] = "unchanged"
    _refund_if_cancelled(update, located, results, trip_id)
    return _note_hours(update, plan)


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


def _scripted_spend(trip_id: str, assist: dict[str, Any]) -> tuple[dict[str, Any], Any | None, Any, Any]:
    """Quote 1000 JPY into USD, ask tip_policy, then authorize the scripted charge.

    tip_policy's authorizedAmount, when it returns one, is the spend ceiling.
    A missing tip package keeps the scripted ceiling.
    """

    fx = quote_fx()
    country = assist.get("countryName") if isinstance(assist.get("countryName"), str) else ""
    tip = tip_policy(trip_id, country, SCRIPTED_CURRENCY, SCRIPTED_REQUESTED_AMOUNT)
    record = authorize_spend(authorizedAmount=_spend_ceiling(tip))
    if record.get("reason") != "over_capture_rejected":
        return record, None, fx, tip
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
    return record, notice, fx, tip


def _refund_if_cancelled(
    update: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    trip_id: str,
) -> None:
    if update.get("event") != "cancelled":
        return
    segment_id = update.get("segmentId") if isinstance(update.get("segmentId"), str) else None
    amount, currency = _quoted_price(segment_id, located)
    update["refund"] = refund_booking(
        trip_id,
        segment_id,
        _confirmation_code(segment_id, located, results),
        amount,
        currency,
    )


def _quoted_price(
    segment_id: str | None,
    located: dict[str, list[dict[str, Any]]],
) -> tuple[Any, str | None]:
    """Amount and currency from the booking price stored for this segment."""

    if not segment_id:
        return None, None
    for match in located.get(segment_id) or []:
        price = match.get("price")
        if not isinstance(price, dict) or "amount" not in price:
            continue
        currency = price.get("currency")
        return price.get("amount"), currency if isinstance(currency, str) else None
    return None, None


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


def _prepare_assist(plan: dict[str, Any], trip_id: str) -> dict[str, Any]:
    """Call the assist tools that run once, before the control loop."""

    end = _trip_end(plan)
    expiry = ""
    trip_end = ""
    if end is not None:
        trip_end = end.isoformat()
        expiry = (end + timedelta(days=SCRIPTED_PASSPORT_DAYS_AFTER_TRIP_END)).isoformat()
    assist: dict[str, Any] = {
        "entry": check_entry(_destination_country(plan), expiry, trip_end, SCRIPTED_VISA_ON_FILE),
        "rides": [],
        "countryName": SCRIPTED_EMERGENCY_COUNTRY if _is_japan(plan) else _destination_country(plan),
        "walksChecked": [],
    }
    if _is_japan(plan):
        assist["emergency"] = emergency_card(SCRIPTED_EMERGENCY_COUNTRY, _traveler_name(plan))
    outdoor = _first_where(plan, _is_outdoor)
    if outdoor is not None:
        assist["weather"] = check_weather(
            _segment_id(outdoor),
            True,
            SCRIPTED_WEATHER_CONDITION,
        )
        assist["weatherSegmentId"] = _segment_id(outdoor)
    pair = _first_consecutive(plan)
    if pair is not None:
        assist["transfer"] = _transfer_between(trip_id, pair[0], pair[1])
    dropped = _luggage_if_early(plan, trip_id)
    if dropped is not None:
        assist["luggage"] = dropped
    held = _table_if_late(plan, trip_id)
    if held is not None:
        assist["table"] = held
    checkout = _checkout_if_same_day(plan, trip_id)
    if checkout is not None:
        assist["checkout"] = checkout
    return assist


def _handoff_weather_shift(
    assist: dict[str, Any],
    plan: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    trip_id: str,
    travelers: list[Any],
    held: list[Any],
) -> None:
    """Hand a storm shift to the existing replan path. Does not invent the shift."""

    del travelers
    weather = assist.get("weather")
    if not isinstance(weather, dict) or weather.get("action") != "shift":
        return
    segment_id = assist.get("weatherSegmentId")
    if not isinstance(segment_id, str) or not segment_id:
        segment_id = weather.get("segmentId") if isinstance(weather.get("segmentId"), str) else None
    update = _replan_update(segment_id, plan, "storm", "ended_late", None)
    clock = _clock(plan, 1)
    if _replan(update, plan, located, results, trip_id, clock):
        assist["weatherReplan"] = update.get("replan")
        held.append(_replan_notice(trip_id, update))


def _poll_watch(
    plan: dict[str, Any],
    clock: dict[str, Any],
    trip_id: str,
    assist: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    notices: list[Any],
) -> tuple[Any, list[dict[str, Any]]]:
    """Call watch_trip. Severity ``act`` warnings are handled before this returns."""

    raw = watch_trip(
        _now(clock),
        copy.deepcopy(plan),
        copy.deepcopy(assist.get("rides") or []),
        _signals(plan, clock),
        trip_id,
    )
    if not isinstance(raw, dict):
        return raw, []
    warnings_in = raw.get("warnings")
    warnings = [dict(item) for item in warnings_in if isinstance(item, dict)] if isinstance(warnings_in, list) else []
    if raw.get("ok") is False:
        for warning in warnings:
            if warning.get("severity") != "act":
                continue
            notice = _act_warning(warning, plan, located, results, trip_id, clock, assist)
            if notice is not None:
                notices.append(notice)
    return raw, warnings


def _act_warning(
    warning: dict[str, Any],
    plan: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    trip_id: str,
    clock: dict[str, Any],
    assist: dict[str, Any],
) -> Any | None:
    action = warning.get("action")
    if action == "replan":
        return _act_replan(warning, plan, located, results, trip_id, clock, ended_late=False)
    if action == "shift":
        segment_id = _warning_segment(warning)
        condition = warning.get("condition")
        if not isinstance(condition, str) or not condition.strip():
            condition = SCRIPTED_WEATHER_CONDITION
        warning["weather"] = check_weather(segment_id or "", True, condition.strip())
        return _act_replan(warning, plan, located, results, trip_id, clock, ended_late=True)
    if action == "request_ride":
        ride = _ride_for_segment(plan, clock, trip_id, _warning_segment(warning), warning)
        if ride is not None:
            _remember_ride(assist, ride, trip_id)
            warning["ride"] = ride
        return None
    if action == "check_transfer":
        warning["transfer"] = _transfer_for_warning(plan, trip_id, warning)
        return None
    return None


def _act_replan(
    warning: dict[str, Any],
    plan: dict[str, Any],
    located: dict[str, list[dict[str, Any]]],
    results: list[dict[str, Any]],
    trip_id: str,
    clock: dict[str, Any],
    ended_late: bool,
) -> Any | None:
    event = warning.get("event") if warning.get("event") in _REPLAN_EVENTS else None
    if event is None and ended_late:
        event = "ended_late"
    delta = _delta_minutes(warning.get("deltaMinutes"))
    update = _replan_update(_warning_segment(warning), plan, _warning_issue(warning), event, delta)
    if not _replan(update, plan, located, results, trip_id, clock):
        warning["replan"] = "unchanged"
        return None
    warning["replan"] = update.get("replan")
    if "hours" in update:
        warning["hours"] = update["hours"]
    if "conflicts" in update:
        warning["conflicts"] = update["conflicts"]
    if "refund" in update:
        warning["refund"] = update["refund"]
    if "notes" in update:
        warning["notes"] = update["notes"]
    return _replan_notice(trip_id, update)


def _replan_update(
    segment_id: str | None,
    plan: dict[str, Any],
    issue: str,
    event: str | None,
    delta: int | None,
) -> dict[str, Any]:
    kind = _kind_of(plan, segment_id)
    update = _update(segment_id, kind, issue, "replan")
    if event in _REPLAN_EVENTS:
        update["event"] = event
        update["deltaMinutes"] = delta
    return update


def _signals(plan: dict[str, Any], clock: dict[str, Any]) -> list[Any]:
    """Signals the caller already has for this tick. The demo may replace this."""

    raw = plan.get("signals") if isinstance(plan, dict) else None
    if not isinstance(raw, list):
        return []
    tick = clock.get("tick") if isinstance(clock, dict) else None
    selected: list[Any] = []
    for item in raw:
        if isinstance(item, dict) and "tick" in item and item.get("tick") not in (None, tick):
            continue
        selected.append(copy.deepcopy(item) if isinstance(item, dict) else item)
    return selected


def _rides_for_ending(plan: dict[str, Any], clock: dict[str, Any], trip_id: str, assist: dict[str, Any]) -> None:
    """Request a ride when an attraction is ending and another stop follows."""

    now = _parse_instant(clock.get("now"))
    if now is None:
        return
    stops = _ordered_stops(plan)
    for index, stop in enumerate(stops):
        if stop["kind"] != "attraction":
            continue
        end = stop["end"]
        if end is None or now < end:
            continue
        if index + 1 >= len(stops):
            continue
        nxt = stops[index + 1]
        ride = _request_one_ride(trip_id, stop, nxt)
        if ride is not None:
            _remember_ride(assist, ride, trip_id)


def _ride_for_segment(
    plan: dict[str, Any],
    clock: dict[str, Any],
    trip_id: str,
    segment_id: str | None,
    warning: dict[str, Any],
) -> dict[str, Any] | None:
    stops = _ordered_stops(plan)
    chosen = None
    follow = None
    for index, stop in enumerate(stops):
        if segment_id and _segment_id(stop["segment"]) == segment_id:
            chosen = stop
            if index + 1 < len(stops):
                follow = stops[index + 1]
            break
    if chosen is None:
        for index, stop in enumerate(stops):
            if stop["kind"] == "attraction" and index + 1 < len(stops):
                chosen = stop
                follow = stops[index + 1]
                break
    if chosen is None or follow is None:
        pickup = warning.get("pickupAt") if isinstance(warning.get("pickupAt"), str) else ""
        dropoff = warning.get("dropoffName") if isinstance(warning.get("dropoffName"), str) else ""
        if not pickup and not dropoff:
            return None
        return _store_ride(
            trip_id,
            segment_id or "",
            "",
            pickup,
            dropoff,
            request_ride(pickup, dropoff, segment_id or "", "", trip_id),
        )
    return _request_one_ride(trip_id, chosen, follow)


def _request_one_ride(trip_id: str, stop: dict[str, Any], nxt: dict[str, Any]) -> dict[str, Any]:
    pickup = _iso(stop["end"]) if isinstance(stop.get("end"), datetime) else ""
    dropoff = _stop_label(nxt)
    return _store_ride(
        trip_id,
        _segment_id(stop["segment"]),
        _segment_id(nxt["segment"]),
        pickup,
        dropoff,
        request_ride(pickup, dropoff, _segment_id(stop["segment"]), _segment_id(nxt["segment"]), trip_id),
    )


def _store_ride(
    trip_id: str,
    segment_id: str,
    to_segment_id: str,
    pickup_at: str,
    dropoff_name: str,
    result: Any,
) -> dict[str, Any]:
    del trip_id
    return {
        "segmentId": segment_id,
        "toSegmentId": to_segment_id,
        "pickupAt": pickup_at,
        "dropoffName": dropoff_name,
        "rideCode": _ride_code(result),
        "result": result,
    }


def _remember_ride(assist: dict[str, Any], ride: dict[str, Any], trip_id: str) -> None:
    rides = assist.setdefault("rides", [])
    segment_id = ride.get("segmentId")
    if segment_id and any(isinstance(item, dict) and item.get("segmentId") == segment_id for item in rides):
        return
    rides.append(ride)
    country = assist.get("countryName") if isinstance(assist.get("countryName"), str) else ""
    assist.setdefault("phraseCards", []).append(
        phrase_card(
            trip_id,
            country,
            ride.get("dropoffName") if isinstance(ride.get("dropoffName"), str) else "",
            ride.get("pickupAt") if isinstance(ride.get("pickupAt"), str) else "",
            segment_id if isinstance(segment_id, str) else "",
        )
    )


def _ride_code(result: Any) -> str | None:
    if isinstance(result, str) and result.startswith("SANDBOX-RIDE-"):
        return result
    if not isinstance(result, dict):
        return None
    for key in _RIDE_CODE_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.startswith("SANDBOX-RIDE-"):
            return value
    for value in result.values():
        if isinstance(value, str) and value.startswith("SANDBOX-RIDE-"):
            return value
    return None


def _transfer_for_warning(plan: dict[str, Any], trip_id: str, warning: dict[str, Any]) -> Any:
    stops = _ordered_stops(plan)
    origin_id = warning.get("fromSegmentId") if isinstance(warning.get("fromSegmentId"), str) else _warning_segment(warning)
    dest_id = warning.get("toSegmentId") if isinstance(warning.get("toSegmentId"), str) else None
    origin = _stop_by_id(stops, origin_id)
    dest = _stop_by_id(stops, dest_id) if dest_id else None
    if origin is not None and dest is None:
        for index, stop in enumerate(stops):
            if stop is origin and index + 1 < len(stops):
                dest = stops[index + 1]
                break
    if origin is None or dest is None:
        pair = _first_consecutive(plan)
        if pair is None:
            return check_transfer("", "", "", "", SCRIPTED_TRAVEL_MINUTES)
        origin, dest = pair
    return _transfer_between(trip_id, origin, dest)


def _transfer_between(trip_id: str, origin: dict[str, Any], dest: dict[str, Any]) -> Any:
    del trip_id
    travel = dest["segment"].get("travelMinutes")
    if isinstance(travel, bool) or not isinstance(travel, int):
        travel = SCRIPTED_TRAVEL_MINUTES
    return check_transfer(
        _segment_id(origin["segment"]),
        _segment_id(dest["segment"]),
        _iso(origin["end"]) if isinstance(origin.get("end"), datetime) else "",
        _iso(dest["start"]) if isinstance(dest.get("start"), datetime) else "",
        travel,
    )


def _luggage_if_early(plan: dict[str, Any], trip_id: str) -> Any | None:
    arrival = None
    flight_id = ""
    check_in = None
    hotel_id = ""
    for stop in _ordered_stops(plan):
        if stop["kind"] == "flight" and arrival is None and isinstance(stop.get("end"), datetime):
            arrival = stop["end"]
            flight_id = _segment_id(stop["segment"])
        if stop["kind"] == "hotel" and check_in is None and isinstance(stop.get("start"), datetime):
            check_in = stop["start"]
            hotel_id = _segment_id(stop["segment"])
    if arrival is None or check_in is None or not (arrival < check_in):
        return None
    return luggage_drop(_iso(arrival), _iso(check_in), hotel_id, flight_id, trip_id)


def _table_if_late(plan: dict[str, Any], trip_id: str) -> Any | None:
    stops = _ordered_stops(plan)
    for index, stop in enumerate(stops):
        if index == 0 or not _is_meal(stop["segment"]):
            continue
        reservation = _parse_instant(stop["segment"].get("reservationAt")) or stop.get("start")
        arrive = _parse_instant(stop["segment"].get("arriveAt")) or stops[index - 1].get("end")
        if not isinstance(arrive, datetime) or not isinstance(reservation, datetime) or not (arrive > reservation):
            continue
        party = stop["segment"].get("partySize")
        party_size = party if isinstance(party, int) and not isinstance(party, bool) else None
        name = stop["segment"].get("name")
        return hold_table(
            _segment_id(stop["segment"]),
            _iso(arrive),
            _iso(reservation),
            trip_id,
            name if isinstance(name, str) else "",
            party_size,
        )
    return None


def _note_hours(update: dict[str, Any], plan: dict[str, Any]) -> bool:
    attraction = _hours_attraction(plan, update)
    if attraction is None:
        return True
    start, end = _window("attraction", attraction)
    closed = attraction.get("closedWeekdays")
    update["hours"] = check_hours(
        _segment_id(attraction),
        _iso(start) if isinstance(start, datetime) else "",
        _iso(end) if isinstance(end, datetime) else "",
        attraction.get("open") if isinstance(attraction.get("open"), str) else SCRIPTED_HOURS_OPEN,
        attraction.get("close") if isinstance(attraction.get("close"), str) else SCRIPTED_HOURS_CLOSE,
        closed if isinstance(closed, list) else list(SCRIPTED_HOURS_CLOSED_WEEKDAYS),
    )
    return True


def _hours_attraction(plan: dict[str, Any], update: dict[str, Any]) -> dict[str, Any] | None:
    segment_id = update.get("segmentId") if isinstance(update.get("segmentId"), str) else None
    if update.get("kind") == "attraction" and segment_id:
        for kind, segment in _segments(plan):
            if kind == "attraction" and segment.get("segmentId") == segment_id and segment.get("removed") is not True:
                return segment
    for kind, segment in _segments(plan):
        if kind == "attraction" and segment.get("removed") is not True:
            return segment
    return None


def _first_where(plan: dict[str, Any], predicate: Any) -> dict[str, Any] | None:
    for kind, segment in _segments(plan):
        if segment.get("removed") is True:
            continue
        if kind == "attraction" and predicate(segment):
            return segment
    return None


def _stamp_tick(
    tick: dict[str, Any],
    watch_record: Any,
    warnings: list[dict[str, Any]],
    rides: list[dict[str, Any]],
    assist: dict[str, Any],
) -> None:
    tick["watch"] = watch_record
    tick["warnings"] = warnings
    if rides:
        tick["rides"] = rides
    if assist.get("tickAirport") is not None:
        tick["airport"] = assist["tickAirport"]
    if assist.get("tickAfterDark") is not None:
        tick["afterDark"] = assist["tickAfterDark"]
    cards = assist.get("phraseCards") or []
    if cards:
        tick["phrase"] = cards[0] if len(cards) == 1 else list(cards)


def _spend_ceiling(tip: Any) -> int:
    """Use tip_policy.authorizedAmount as the spend ceiling when it is a number."""

    if not isinstance(tip, dict):
        return SCRIPTED_AUTHORIZED_AMOUNT
    amount = tip.get("authorizedAmount")
    if isinstance(amount, bool) or amount is None:
        return SCRIPTED_AUTHORIZED_AMOUNT
    if isinstance(amount, int):
        return amount
    if isinstance(amount, float) and amount.is_integer():
        return int(amount)
    if isinstance(amount, str):
        text = amount.strip()
        digits = text[1:] if text.startswith("-") else text
        if digits.isdigit():
            return int(text)
    return SCRIPTED_AUTHORIZED_AMOUNT


def _airport_on_day(plan: dict[str, Any], clock: dict[str, Any], trip_id: str) -> Any | None:
    """Call airport_leave when this tick falls on a flight day."""

    now = _parse_instant(clock.get("now"))
    if now is None:
        return None
    day = now.date()
    for kind, segment in _segments(plan):
        if kind != "flight" or segment.get("removed") is True:
            continue
        days = [_parse_day(segment.get("departDate")), _parse_day(segment.get("returnDate"))]
        start, end = _window("flight", segment)
        if start is not None:
            days.append(start.date())
        if end is not None:
            days.append(end.date())
        if day not in days:
            continue
        origin = segment.get("from") if isinstance(segment.get("from"), str) else ""
        destination = segment.get("to") if isinstance(segment.get("to"), str) else ""
        return airport_leave(trip_id, _segment_id(segment), day.isoformat(), _now(clock), origin, destination)
    return None


def _after_dark_walks(
    plan: dict[str, Any],
    clock: dict[str, Any],
    trip_id: str,
    assist: dict[str, Any],
) -> Any | None:
    """Call after_dark for each walk leg once. action request_ride asks for a ride."""

    checked = assist.setdefault("walksChecked", [])
    outcomes: list[Any] = []
    stops = _ordered_stops(plan)
    now = _now(clock)
    for index, stop in enumerate(stops):
        segment = stop["segment"]
        if not _is_walk(segment):
            continue
        segment_id = _segment_id(segment)
        if segment_id in checked:
            continue
        checked.append(segment_id)
        name = segment.get("name") if isinstance(segment.get("name"), str) else ""
        outcome = after_dark(
            segment_id,
            name,
            _iso(stop["start"]) if isinstance(stop.get("start"), datetime) else "",
            _iso(stop["end"]) if isinstance(stop.get("end"), datetime) else "",
            now,
            trip_id,
        )
        outcomes.append(outcome)
        if isinstance(outcome, dict) and outcome.get("action") == "request_ride" and index + 1 < len(stops):
            _remember_ride(assist, _request_one_ride(trip_id, stop, stops[index + 1]), trip_id)
    if not outcomes:
        return None
    return outcomes[0] if len(outcomes) == 1 else outcomes


def _is_walk(segment: dict[str, Any]) -> bool:
    if segment.get("walk") is True:
        return True
    name = segment.get("name")
    return isinstance(name, str) and "walk" in name.lower()


def _checkout_if_same_day(plan: dict[str, Any], trip_id: str) -> Any | None:
    flights: list[dict[str, Any]] = []
    hotels: list[dict[str, Any]] = []
    for kind, segment in _segments(plan):
        if segment.get("removed") is True:
            continue
        if kind == "flight":
            flights.append(segment)
        elif kind == "hotel":
            hotels.append(segment)
    for hotel in hotels:
        checkout = _parse_day(hotel.get("checkOut"))
        if checkout is None:
            continue
        for flight in flights:
            flight_days = [_parse_day(flight.get("departDate")), _parse_day(flight.get("returnDate"))]
            if checkout not in flight_days:
                continue
            return late_checkout(
                trip_id,
                _segment_id(flight),
                _segment_id(hotel),
                checkout.isoformat(),
                checkout.isoformat(),
            )
    return None


def _known_codes(results: list[dict[str, Any]], assist: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        code = item.get("confirmationCode")
        if isinstance(code, str) and code.strip():
            codes.append(code.strip())
    for ride in assist.get("rides") or []:
        if not isinstance(ride, dict):
            continue
        code = ride.get("rideCode")
        if isinstance(code, str) and code.strip():
            codes.append(code.strip())
    return codes


def _ordered_stops(plan: dict[str, Any]) -> list[dict[str, Any]]:
    stops: list[dict[str, Any]] = []
    for kind, segment in _segments(plan):
        if segment.get("removed") is True:
            continue
        start, end = _window(kind, segment)
        stops.append({"kind": kind, "segment": segment, "start": start, "end": end})
    missing = datetime.max.replace(tzinfo=timezone.utc)
    stops.sort(key=lambda item: (item["start"] or missing, _segment_id(item["segment"])))
    return stops


def _first_consecutive(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    stops = _ordered_stops(plan)
    if len(stops) < 2:
        return None
    return stops[0], stops[1]


def _stop_by_id(stops: list[dict[str, Any]], segment_id: str | None) -> dict[str, Any] | None:
    if not segment_id:
        return None
    for stop in stops:
        if _segment_id(stop["segment"]) == segment_id:
            return stop
    return None


def _window(kind: str, segment: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    start = _parse_instant(segment.get("start"))
    end = _parse_instant(segment.get("end"))
    if kind == "flight":
        if start is None:
            day = _parse_day(segment.get("departDate"))
            start = _at(day, 9, 0) if day else None
        if end is None and start is not None:
            end = start + timedelta(hours=3)
    elif kind == "hotel":
        if start is None:
            day = _parse_day(segment.get("checkIn"))
            start = _at(day, 15, 0) if day else None
        if end is None:
            day = _parse_day(segment.get("checkOut"))
            end = _at(day, 11, 0) if day else None
    elif kind == "attraction":
        if start is None:
            start = _attraction_start(segment)
        if end is None and start is not None:
            end = start + timedelta(hours=2)
    return start, end


def _attraction_start(segment: dict[str, Any]) -> datetime | None:
    raw = segment.get("date")
    if isinstance(raw, str) and "T" in raw:
        return _parse_instant(raw)
    day = _parse_day(raw if isinstance(raw, str) else None)
    if day is None:
        return None
    clock = _parse_hhmm(segment.get("time"))
    if clock is None:
        return _at(day, 10, 0)
    return _at(day, clock[0], clock[1])


def _is_outdoor(segment: dict[str, Any]) -> bool:
    if segment.get("outdoor") is True:
        return True
    if segment.get("outdoor") is False:
        return False
    name = segment.get("name")
    if not isinstance(name, str):
        return False
    lowered = name.lower()
    return any(word in lowered for word in _OUTDOOR_WORDS)


def _is_meal(segment: dict[str, Any]) -> bool:
    if segment.get("meal") is True:
        return True
    if segment.get("meal") is False:
        return False
    name = segment.get("name")
    if not isinstance(name, str):
        return False
    lowered = name.lower()
    return any(word in lowered for word in _MEAL_WORDS)


def _is_japan(plan: dict[str, Any]) -> bool:
    return _destination_country(plan).strip().lower() in _JAPAN


def _destination_country(plan: dict[str, Any]) -> str:
    destination = plan.get("destination")
    if not isinstance(destination, dict):
        return ""
    country = destination.get("country")
    return country.strip() if isinstance(country, str) else ""


def _traveler_name(plan: dict[str, Any]) -> str:
    travelers = plan.get("travelers")
    if not isinstance(travelers, list):
        return ""
    for traveler in travelers:
        if isinstance(traveler, dict) and isinstance(traveler.get("name"), str) and traveler["name"].strip():
            return traveler["name"].strip()
    return ""


def _trip_end(plan: dict[str, Any]) -> date | None:
    dates = plan.get("dates")
    if not isinstance(dates, dict):
        return None
    return _parse_day(dates.get("end"))


def _kind_of(plan: dict[str, Any], segment_id: str | None) -> str | None:
    if not segment_id:
        return None
    for kind, segment in _segments(plan):
        if segment.get("segmentId") == segment_id:
            return kind
    return None


def _warning_segment(warning: dict[str, Any]) -> str | None:
    segment_id = warning.get("segmentId")
    return segment_id if isinstance(segment_id, str) and segment_id else None


def _warning_issue(warning: dict[str, Any]) -> str:
    issue = warning.get("issue")
    return issue if isinstance(issue, str) else ""


def _segment_id(segment: dict[str, Any]) -> str:
    segment_id = segment.get("segmentId")
    return segment_id if isinstance(segment_id, str) else ""


def _stop_label(stop: dict[str, Any]) -> str:
    segment = stop["segment"]
    name = segment.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    city = segment.get("city")
    if isinstance(city, str) and city.strip():
        return city.strip()
    destination = segment.get("to")
    if isinstance(destination, str) and destination.strip():
        return destination.strip()
    return _segment_id(segment) or stop["kind"]


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_instant(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if "T" not in text:
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


def _parse_day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if "T" in text:
        instant = _parse_instant(text)
        return None if instant is None else instant.date()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_hhmm(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if hour > 23 or minute > 59 or hour < 0 or minute < 0:
        return None
    return hour, minute


def _at(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def _envelope(
    trip_id: str | None,
    results: list[dict[str, Any]],
    ticks: list[dict[str, Any]],
    loop_stopped: str,
    error: str | None,
    spend: dict[str, Any] | None = None,
    assist: dict[str, Any] | None = None,
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
    if assist:
        for key in _ASSIST_KEYS:
            value = assist.get(key)
            if value is None or value == []:
                continue
            body[key] = value
    return body
