from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from roam_contracts.models import (
    Candidate,
    CandidateKind,
    CandidateSet,
    Itinerary,
    ItineraryDay,
    Leg,
    LegSource,
    PlanRevision,
    PlanSelection,
    RevisionAction,
    SegmentStatus,
    Stop,
    StopKind,
    StopStatus,
    TravelMode,
    TripBrief,
)
from roam_agent.validate import validate_itinerary
from roam_tools.attractions import search_attractions
from roam_tools.routing import optimize_route
from roam_tools.transport import arrival_transfer_minutes, get_transport_profile

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"


def flight_warnings(brief: TripBrief) -> list[str]:
    notes: list[str] = []
    for label, segment in (("Arrival", brief.arrival), ("Departure", brief.departure)):
        if segment is None:
            continue
        if segment.status == SegmentStatus.UNVERIFIED:
            notes.append(f"Unverified flight times for {segment.number or label}.")
        if segment.status == SegmentStatus.DELAYED and label == "Arrival":
            notes.append(f"Arrival {segment.number or ''} is delayed. Day 1 uses the revised time.".strip())
    return notes


def _emit(emit, plan_id: str, tool: str, summary: str) -> None:
    if emit is not None:
        emit({"plan_id": plan_id, "tool": tool, "summary": summary})


def collect_candidates(brief: TripBrief, emit=None, plan_id: str = "plan") -> CandidateSet:
    if os.environ.get("ROAM_SCRIPTED_AGENT") == "1":
        payload = json.loads((FIXTURES / "candidates_kyoto.json").read_text())
        return CandidateSet.model_validate(payload)
    profile = get_transport_profile(brief.destination)
    _emit(emit, plan_id, "get_transport_profile", profile.tips[0] if profile.tips else profile.place)
    near = None
    if brief.lodging and brief.lodging[0].location is not None:
        near = {"lat": brief.lodging[0].location.lat, "lng": brief.lodging[0].location.lng}
    attractions = search_attractions(brief.destination, brief.interests, near, 25, 12)
    _emit(emit, plan_id, "search_attractions", f"{len(attractions)} sights")
    candidates = [
        Candidate(id=item.id, kind=CandidateKind.ATTRACTION, attraction=item) for item in attractions
    ]
    hours = 8.0
    if brief.arrival and brief.departure:
        hours = max(4.0, (brief.departure.depart_at - brief.arrival.arrive_at).total_seconds() / 3600 - 6)
    return CandidateSet(plan_id=plan_id, candidates=candidates, available_hours=round(hours, 1))


def _candidate_map(candidates: CandidateSet) -> dict[str, Candidate]:
    return {item.id: item for item in candidates.candidates}


def _stop_from(candidate: Candidate, start: datetime, required: bool) -> Stop:
    if candidate.attraction is not None:
        attraction = candidate.attraction
        return Stop(
            id=candidate.id, kind=StopKind.ATTRACTION, start=start,
            end=start + timedelta(minutes=attraction.typical_duration_min),
            location=attraction.location, title=attraction.name, attraction=attraction,
            required=required, status=StopStatus.PROPOSED,
        )
    quote = candidate.quote
    location = candidate.merchant.location if candidate.merchant and candidate.merchant.location else quote.location
    title = quote.title if quote is not None else candidate.id
    return Stop(
        id=candidate.id, kind=StopKind.MERCHANT, start=start, end=start + timedelta(minutes=60),
        location=location, title=title, quote=quote, required=required, status=StopStatus.PROPOSED,
    )


def plan(brief: TripBrief, selection: PlanSelection, candidates: CandidateSet, emit=None, plan_id: str = "plan") -> Itinerary:
    if os.environ.get("ROAM_SCRIPTED_AGENT") == "1":
        payload = json.loads((FIXTURES / "itinerary_kyoto.json").read_text())
        built = Itinerary.model_validate(payload)
        built.selection = selection
        built.warnings = [*built.warnings, *flight_warnings(brief)]
        return built
    by_id = _candidate_map(candidates)
    profile = get_transport_profile(brief.destination)
    code = brief.arrival.to_place.code if brief.arrival and brief.arrival.to_place else None
    transfer = arrival_transfer_minutes(profile, code)
    _emit(emit, plan_id, "get_transport_profile", f"Arrival transfer {transfer} min")
    chosen_ids = [item for item in selection.must_visit if item in by_id]
    for item in selection.maybe:
        if item in by_id and item not in chosen_ids:
            chosen_ids.append(item)
    warnings: list[str] = []
    warnings.extend(flight_warnings(brief))
    if profile.source == "llm":
        warnings.append(f"Getting around {brief.destination} is unverified.")
    missing = [item for item in selection.must_visit if item not in by_id]
    for item in missing:
        warnings.append(f"{item} doesn't fit; it was not in the candidate list")
    hotel = brief.lodging[0].location if brief.lodging and brief.lodging[0].location else None
    mode = brief.preferred_modes[0] if brief.preferred_modes else TravelMode.WALK
    start_day = brief.arrival.arrive_at if brief.arrival else brief.start_date
    end_day = brief.departure.depart_at if brief.departure else brief.end_date
    if start_day is None or end_day is None:
        raise ValueError("Trip brief needs arrival and departure, or start and end dates")
    days: list[ItineraryDay] = []
    cursor_date = start_day.date()
    pool = list(chosen_ids)
    while cursor_date <= end_day.date():
        if cursor_date == start_day.date() and brief.arrival is not None:
            window_start = brief.arrival.arrive_at + timedelta(minutes=transfer + 30)
        else:
            window_start = datetime.fromisoformat(f"{cursor_date.isoformat()}T{brief.daily_start}:00").replace(tzinfo=start_day.tzinfo)
        if cursor_date == end_day.date() and brief.departure is not None:
            window_end = brief.departure.depart_at - timedelta(minutes=transfer) - timedelta(hours=2)
        else:
            window_end = datetime.fromisoformat(f"{cursor_date.isoformat()}T{brief.daily_end}:00").replace(tzinfo=start_day.tzinfo)
        day_ids = []
        while pool and len(day_ids) < (2 if brief.pace.value == "relaxed" else 3):
            day_ids.append(pool.pop(0))
        routed = []
        for cid in day_ids:
            candidate = by_id[cid]
            duration = candidate.attraction.typical_duration_min if candidate.attraction else 60
            location = candidate.attraction.location if candidate.attraction else candidate.merchant.location
            routed.append({
                "id": cid, "lat": location.lat, "lng": location.lng, "duration_min": duration,
                "required": cid in selection.must_visit,
            })
        origin = {"lat": hotel.lat, "lng": hotel.lng} if hotel is not None else {"lat": routed[0]["lat"], "lng": routed[0]["lng"]} if routed else {"lat": 35.01, "lng": 135.77}
        order = [item["id"] for item in routed]
        if routed:
            result = optimize_route(routed, origin, mode.value, window_start, window_end, origin)
            order = result["order"] or order
            warnings.extend(result["warnings"])
            _emit(emit, plan_id, "optimize_route", f"Ordered {len(order)} stops")
        stops: list[Stop] = []
        if cursor_date == start_day.date() and brief.arrival is not None:
            hub = brief.arrival.to_place.location
            stops.append(Stop(
                id="arrival", kind=StopKind.ARRIVAL, start=brief.arrival.arrive_at,
                end=brief.arrival.arrive_at + timedelta(minutes=20),
                location=hub or hotel, title=f"Arrive {brief.arrival.number or ''} at {brief.arrival.to_place.name}".strip(),
            ))
        if hotel is not None and cursor_date == start_day.date():
            check = brief.lodging[0].check_in
            stops.append(Stop(
                id="check-in", kind=StopKind.LODGING, start=check, end=check + timedelta(minutes=20),
                location=hotel, title=f"Check in at {brief.lodging[0].name}",
            ))
        clock = window_start
        for cid in order:
            stop = _stop_from(by_id[cid], clock, cid in selection.must_visit)
            if stop.end > window_end and cid in selection.must_visit:
                warnings.append(f"{cid} doesn't fit; add a day")
            stops.append(stop)
            clock = stop.end + timedelta(minutes=15)
        if cursor_date == end_day.date() and brief.departure is not None and hotel is not None:
            checkout = brief.lodging[0].check_out
            hub = brief.departure.from_place.location or hotel
            stops.append(Stop(
                id="check-out", kind=StopKind.LODGING, start=checkout, end=checkout + timedelta(minutes=20),
                location=hotel, title=f"Check out of {brief.lodging[0].name}",
            ))
            stops.append(Stop(
                id="departure", kind=StopKind.DEPARTURE, start=brief.departure.depart_at,
                end=brief.departure.depart_at + timedelta(minutes=20),
                location=hub, title=f"Depart {brief.departure.number or ''} from {brief.departure.from_place.name}".strip(),
            ))
        legs = []
        for left, right in zip(stops, stops[1:]):
            legs.append(Leg(
                from_stop_id=left.id, to_stop_id=right.id, mode=mode,
                minutes=max(1, int((right.start - left.end).total_seconds() // 60) or 10),
                distance_km=1.0, source=LegSource.ESTIMATE,
            ))
        days.append(ItineraryDay(date=cursor_date.isoformat(), stops=stops, legs=legs))
        cursor_date = cursor_date + timedelta(days=1)
    bookable = Decimal("0")
    for day in days:
        for stop in day.stops:
            if stop.quote is not None:
                bookable += stop.quote.amount
    built = Itinerary(
        plan_id=plan_id, brief=brief, selection=selection, days=days,
        transport_summary=profile.tips[0] if profile.tips else profile.place,
        estimated_total=bookable, bookable_total=bookable, warnings=warnings,
    )
    errors = validate_itinerary(built)
    if errors:
        built.warnings.extend(errors)
    return built


def revise(itinerary: Itinerary, revision: PlanRevision, emit=None) -> Itinerary:
    removed = {item.stop_id for item in revision.actions if item.action == RevisionAction.REMOVE}
    accepted = {item.stop_id for item in revision.actions if item.action == RevisionAction.ACCEPT}
    days = []
    for day in itinerary.days:
        stops = []
        for stop in day.stops:
            if stop.id in removed and not stop.required:
                continue
            if stop.id in accepted:
                stop = stop.model_copy(update={"status": StopStatus.ACCEPTED})
            stops.append(stop)
        keep = {stop.id for stop in stops}
        legs = [leg for leg in day.legs if leg.from_stop_id in keep and leg.to_stop_id in keep]
        days.append(ItineraryDay(date=day.date, stops=stops, legs=legs))
    warnings = list(itinerary.warnings)
    titles = {stop.id: stop.title for day in days for stop in day.stops}
    for item in revision.actions:
        if item.action == RevisionAction.SWAP:
            warnings.append(f"Asked to swap {titles.get(item.stop_id, item.stop_id)}")
    if revision.feedback:
        warnings.append(revision.feedback)
        _emit(emit, itinerary.plan_id, "revise", revision.feedback)
    updated = itinerary.model_copy(update={"days": days, "warnings": warnings})
    return updated
