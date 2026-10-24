"""Book every segment on a finished trip plan.

The planner has already chosen flights, hotels, and attractions. This service
calls one tool per segment, records booking state, and always returns one
result per segment.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from booking.contract import SegmentResult, TripBookingResponse, TripPlan
from booking.orchestrator.memory import BookingMemory
from booking.orchestrator.tools import TOOLS_BY_KIND, Tool, normalize_provider_result

logger = logging.getLogger(__name__)


def _result(
    segment_id: str,
    kind: str,
    status: str,
    *,
    error: str | None = None,
    confirmation_code: str | None = None,
    price: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return SegmentResult(
        segmentId=segment_id,
        kind=kind,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        confirmationCode=confirmation_code,
        price=price,
        error=error,
    ).model_dump()


def _segments(plan: TripPlan) -> list[tuple[str, dict[str, Any]]]:
    ordered: list[tuple[str, dict[str, Any]]] = []
    for flight in plan.flights:
        ordered.append(("flight", flight.model_dump(by_alias=True, mode="json")))
    for hotel in plan.hotels:
        ordered.append(("hotel", hotel.model_dump(mode="json")))
    for attraction in plan.attractions:
        ordered.append(("attraction", attraction.model_dump(mode="json")))
    return ordered


def book_plan(
    plan: TripPlan,
    memory: BookingMemory,
    tools: dict[str, Tool] | None = None,
) -> dict[str, Any]:
    """Book each segment through a registered runtime tool.

    A provider failure is one result; later segments still run.
    """

    registry = tools if tools is not None else {tool.name: tool for tool in TOOLS_BY_KIND.values()}

    known_travelers = {traveler.id for traveler in plan.travelers}
    travelers = [traveler.model_dump(mode="json") for traveler in plan.travelers]
    prior = {
        item["segmentId"]: item
        for item in memory.load(plan.tripId)
        if isinstance(item, dict) and item.get("status") == "booked" and item.get("segmentId")
    }

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kind, segment in _segments(plan):
        segment_id = segment["segmentId"]
        if segment_id in seen:
            results.append(_result(segment_id, kind, "needs_user", error="duplicate_segment_id"))
            continue
        seen.add(segment_id)

        if segment_id in prior:
            # Re-check the stored code. A non-sandbox confirmation is not replayed.
            results.append(normalize_provider_result(prior[segment_id], segment_id, kind))
            continue

        if kind == "flight":
            requested = segment.get("travelerIds") or []
            if not requested:
                results.append(_result(segment_id, kind, "needs_user", error="missing_travelers"))
                continue
            unknown = [traveler_id for traveler_id in requested if traveler_id not in known_travelers]
            if unknown:
                results.append(_result(segment_id, kind, "needs_user", error="unknown_traveler"))
                continue

        try:
            outcome = registry[TOOLS_BY_KIND[kind].name].fn(segment, travelers, plan.tripId)
        except Exception as exc:
            logger.exception("Booking tool crashed for %s", segment_id)
            message = str(exc).strip() or exc.__class__.__name__
            outcome = _result(segment_id, kind, "failed", error=message)
        results.append(outcome)
        if outcome.get("status") == "booked":
            memory.save(plan.tripId, results)

    memory.save(plan.tripId, results)
    return TripBookingResponse(tripId=plan.tripId, results=results, error=None).model_dump()


def handle_payload(
    payload: object,
    memory: BookingMemory,
    tools: dict[str, Tool] | None = None,
) -> dict[str, Any]:
    """Validate a trip plan and book it. Invalid JSON shape does not raise."""

    if not isinstance(payload, dict):
        return TripBookingResponse(tripId=None, results=[], error="invalid_plan").model_dump()
    try:
        plan = TripPlan.model_validate(payload)
    except ValidationError:
        logger.info("Rejected trip plan that does not match the booking contract")
        trip_id = payload.get("tripId")
        return TripBookingResponse(
            tripId=trip_id if isinstance(trip_id, str) else None,
            results=[],
            error="invalid_plan",
        ).model_dump()
    return book_plan(plan, memory, tools=tools)
