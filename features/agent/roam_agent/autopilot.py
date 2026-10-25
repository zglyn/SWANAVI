from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from roam_contracts.models import (
    AttractionSelection,
    Autonomy,
    CandidateSet,
    Density,
    FlightOffer,
    HotelOffer,
    HotelStay,
    Itinerary,
    ItineraryDay,
    Lodging,
    PackageChoices,
    PackageTotals,
    Pace,
    PlanSelection,
    Stop,
    StopKind,
    SwanPhase,
    TravelPackage,
    TripBrief,
    TripRequest,
    UserProfile,
)
from roam_agent.plan import DEPLANE_MIN, arrival_lodging, build_legs, schedule_stops
from roam_agent.plan import plan as build_plan
from roam_agent.profile_crypto import planning_profile
from roam_tools.demo_city import freshen_package, load as load_demo
from roam_tools.flight_search import search_flights
from roam_tools.hotel_search import search_hotels
from roam_tools.transport import arrival_transfer_minutes, get_transport_profile

log = logging.getLogger("swan.autopilot")
ROOT = Path(__file__).resolve().parents[3]
KYOTO_CANDIDATES = ROOT / "contracts" / "fixtures" / "candidates_kyoto.json"
DEMO_CANDIDATES = ROOT / "contracts" / "fixtures" / "candidates_demo.json"
KYOTO_PACKAGE = ROOT / "contracts" / "fixtures" / "package_kyoto.json"
DEMO_PACKAGE = ROOT / "contracts" / "fixtures" / "package_demo.json"
AMOUNT_WEIGHT = {"none": 0, "a_little": 1, "some": 2, "lots": 4}
DENSITY_CAP = {Density.LIGHT: 2, Density.BALANCED: 3, Density.PACKED: 4}
PACE = {Density.LIGHT: Pace.RELAXED, Density.BALANCED: Pace.BALANCED, Density.PACKED: Pace.PACKED}


@dataclass
class SwanTrip:
    plan_id: str
    user_id: str
    request: TripRequest
    profile: UserProfile
    phase: SwanPhase = SwanPhase.ATTRACTIONS
    selection: AttractionSelection | None = None
    flights: list[FlightOffer] = field(default_factory=list)
    hotels: list[HotelOffer] = field(default_factory=list)
    outbound_id: str | None = None
    return_id: str | None = None
    hotel_ids: list[str] = field(default_factory=list)
    package: TravelPackage | None = None
    chosen_ids: list[str] = field(default_factory=list)


def begin(user_id: str, request: TripRequest, profile: UserProfile, plan_id: str | None = None) -> SwanTrip:
    trip = SwanTrip(
        plan_id=plan_id or uuid.uuid4().hex[:12],
        user_id=user_id,
        request=request,
        profile=profile,
    )
    if request.autonomy.attractions == Autonomy.I_CHOOSE:
        trip.phase = SwanPhase.ATTRACTIONS
        log.info("swan %s waiting_attractions", trip.plan_id)
        return trip
    return advance(trip)


def submit_attractions(trip: SwanTrip, selection: AttractionSelection) -> SwanTrip:
    trip.selection = selection
    return advance(trip)


def apply_choices(trip: SwanTrip, choices: PackageChoices) -> SwanTrip:
    outbound_changed = bool(choices.outbound_id and choices.outbound_id != trip.outbound_id)
    hotel_changed = bool(choices.hotel_ids and choices.hotel_ids != trip.hotel_ids)
    if choices.outbound_id:
        trip.outbound_id = choices.outbound_id
    if choices.return_id:
        trip.return_id = choices.return_id
    if choices.hotel_ids:
        trip.hotel_ids = list(choices.hotel_ids)
    if trip.package and outbound_changed and not hotel_changed:
        outbound = _offer(trip.flights, trip.outbound_id)
        if outbound is not None:
            shifted = _shift_day_one(trip.package.itinerary, outbound.segments[-1].arrive_at)
            trip.package = trip.package.model_copy(update={
                "outbound": outbound,
                "itinerary": shifted,
                "reasons": [*trip.package.reasons, "Day 1 moved to the new arrival. Later days stayed put."],
            })
            if choices.return_id:
                inbound = _offer(trip.flights, trip.return_id)
                trip.package.return_flight = inbound
            trip.phase = SwanPhase.READY
            return trip
    return advance(trip)


def advance(trip: SwanTrip) -> SwanTrip:
    if _scripted(trip):
        trip.package = TravelPackage.model_validate(json.loads(_package_file(trip.request.destination).read_text()))
        if not _kyoto(trip.request.destination):
            trip.package = freshen_package(trip.package)
        trip.package.plan_id = trip.plan_id
        trip.phase = SwanPhase.READY
        log.info("swan %s package_ready scripted", trip.plan_id)
        return trip
    _ensure_flights(trip)
    if trip.request.autonomy.flights == Autonomy.I_CHOOSE and not trip.outbound_id:
        trip.phase = SwanPhase.FLIGHTS
        log.info("swan %s waiting_flights", trip.plan_id)
        return trip
    if not trip.outbound_id:
        outbound = [item for item in trip.flights if item.direction == "outbound"]
        inbound = [item for item in trip.flights if item.direction == "return"]
        if outbound:
            trip.outbound_id = outbound[0].id
        if inbound:
            trip.return_id = inbound[0].id
    pool = _pool(trip.request.destination)
    trip.chosen_ids = pick_attractions(trip.profile, trip.selection, pool, _nights(trip.request))
    _ensure_hotels(trip)
    if trip.request.autonomy.hotels == Autonomy.I_CHOOSE and not trip.hotel_ids:
        trip.phase = SwanPhase.HOTELS
        log.info("swan %s waiting_hotels", trip.plan_id)
        return trip
    if not trip.hotel_ids and trip.hotels:
        splits = [item for item in trip.hotels if any("Split stay" in line for line in item.why)]
        trip.hotel_ids = [item.id for item in splits[:2]] or [trip.hotels[0].id]
    trip.package = _compose(trip, pool)
    trip.phase = SwanPhase.READY
    log.info("swan %s package_ready", trip.plan_id)
    return trip


def pick_attractions(profile: UserProfile, selection: AttractionSelection | None, pool: CandidateSet, nights: int) -> list[str]:
    selection = selection or AttractionSelection()
    weights = {item.category.lower(): AMOUNT_WEIGHT[item.level.value] for item in selection.amounts}
    density = selection.daily_density if selection.mode == Autonomy.I_CHOOSE or selection.amounts else PACE_FROM_PROFILE(profile)
    cap = max(1, nights) * DENSITY_CAP[density]
    blocked = {tag.lower() for tag in profile.travel.avoid}
    dietary = {tag.lower() for tag in profile.travel.dietary}
    access = {tag.lower() for tag in profile.travel.accessibility}

    def text(candidate) -> str:
        attraction = candidate.attraction
        if attraction:
            return f"{attraction.name} {attraction.description} {attraction.category}".lower()
        merchant = candidate.merchant
        return f"{merchant.name} {merchant.category.value}".lower() if merchant else candidate.id.lower()

    def blocked_row(candidate) -> bool:
        body = text(candidate)
        if any(tag in body for tag in blocked):
            return True
        if dietary and "food" in body and any(tag in body for tag in ("ramen", "sake", "meat")):
            return True
        if "step-free" in access and "stairs" in body:
            return True
        return False

    rows = [item for item in pool.candidates if not blocked_row(item)]
    by_id = {item.id: item for item in rows}
    chosen: list[str] = []
    if selection.mode == Autonomy.I_CHOOSE:
        for pick in selection.picks:
            if pick.priority.value == "must" and pick.candidate_id in by_id:
                chosen.append(pick.candidate_id)
        for pick in selection.picks:
            if pick.priority.value == "nice" and pick.candidate_id in by_id and pick.candidate_id not in chosen:
                chosen.append(pick.candidate_id)
    else:
        interests = {item.lower() for item in profile.travel.interests}

        def interesting(candidate) -> bool:
            if not interests:
                return True
            body = text(candidate)
            return any(item in body for item in interests)

        rows = [item for item in rows if interesting(item)]
    rest = [item for item in rows if item.id not in chosen]

    def category_of(candidate) -> str:
        if candidate.attraction:
            return candidate.attraction.category.lower()
        if candidate.merchant:
            return candidate.merchant.category.value.lower()
        return ""

    def sort_key(candidate) -> tuple:
        category = category_of(candidate)
        weight = weights.get(category, 1 if not weights else 0)
        popular = candidate.attraction.popularity if candidate.attraction else 0
        return (weight, popular)

    rest.sort(key=sort_key, reverse=True)
    for item in rest:
        if len(chosen) >= cap:
            break
        if weights.get(category_of(item)) == 0:
            continue
        chosen.append(item.id)
    return chosen


def PACE_FROM_PROFILE(profile: UserProfile) -> Density:
    return {Pace.RELAXED: Density.LIGHT, Pace.BALANCED: Density.BALANCED, Pace.PACKED: Density.PACKED}[profile.travel.pace]


def _kyoto(destination: str) -> bool:
    return "kyoto" in destination.lower()


def _package_file(destination: str) -> Path:
    return KYOTO_PACKAGE if _kyoto(destination) else DEMO_PACKAGE


def _pool(destination: str) -> CandidateSet:
    path = KYOTO_CANDIDATES if _kyoto(destination) else DEMO_CANDIDATES
    return CandidateSet.model_validate(json.loads(path.read_text()))


def _nights(request: TripRequest) -> int:
    start = date.fromisoformat(request.start_date)
    end = date.fromisoformat(request.end_date)
    return max(1, (end - start).days)


def _airports(request: TripRequest, profile: UserProfile) -> tuple[list[str], list[str]]:
    if request.origin.from_home:
        origins = list(profile.home.airport_codes)
    else:
        origins = list(request.origin.airport_codes)
    destinations = list(request.place.airports) if request.place is not None else []
    return origins, destinations


def _prev(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def _ensure_flights(trip: SwanTrip) -> None:
    if trip.flights:
        return
    origins, destinations = _airports(trip.request, trip.profile)
    seen = trip.profile.flights
    primary = search_flights(
        origins, destinations, _prev(trip.request.start_date), trip.request.end_date,
        trip.request.outbound_window.value, trip.request.return_window.value,
        seen.cabin.value, seen.max_stops, trip.request.travellers,
        seen.favourite_airlines, seen.avoid_red_eye, trip.profile.sleep.sleep_time, trip.profile.sleep.wake_time,
    )
    same_day = search_flights(
        origins, destinations, trip.request.start_date, trip.request.end_date,
        trip.request.outbound_window.value, trip.request.return_window.value,
        seen.cabin.value, seen.max_stops, trip.request.travellers,
        seen.favourite_airlines, seen.avoid_red_eye, trip.profile.sleep.sleep_time, trip.profile.sleep.wake_time,
    )
    merged = {item.id: item for item in primary}
    for item in same_day:
        merged.setdefault(item.id, item)
    trip.flights = sorted(merged.values(), key=lambda item: item.score, reverse=True)


def _ensure_hotels(trip: SwanTrip) -> None:
    if trip.hotels:
        return
    pool = _pool(trip.request.destination)
    by_id = {item.id: item for item in pool.candidates}
    points = []
    nights = _nights(trip.request)
    start = date.fromisoformat(trip.request.start_date)
    for index, chosen in enumerate(trip.chosen_ids):
        candidate = by_id.get(chosen)
        if candidate is None:
            continue
        location = candidate.attraction.location if candidate.attraction else candidate.merchant.location
        day = (start + timedelta(days=min(index, nights - 1))).isoformat()
        weight = 2 if trip.selection and chosen in trip.selection.must_visit else 1
        points.append({"id": chosen, "lat": location.lat, "lng": location.lng, "day": day, "weight": weight})
    if not points and trip.request.place is not None:
        place = trip.request.place
        points = [{
            "id": "destination",
            "lat": place.lat,
            "lng": place.lng,
            "day": trip.request.start_date,
            "weight": 1,
        }]
    elif not points and not _kyoto(trip.request.destination):
        center = load_demo()["center"]
        points = [{
            "id": "destination",
            "lat": center["lat"],
            "lng": center["lng"],
            "day": trip.request.start_date,
            "weight": 1,
        }]
    prefs = trip.profile.hotels
    members = [item.program for item in prefs.loyalty if item.number]
    trip.hotels = search_hotels(
        points, trip.request.start_date, trip.request.end_date,
        trip.profile.travel.budget_level.value, prefs.favourite_brands, prefs.min_stars, prefs.must_have,
        trip.request.travellers, [mode.value for mode in trip.profile.travel.preferred_modes], members,
    )


def _offer(offers: list[FlightOffer], offer_id: str | None) -> FlightOffer | None:
    return next((item for item in offers if item.id == offer_id), None)


def _hotel(trip: SwanTrip, offer_id: str) -> HotelOffer | None:
    return next((item for item in trip.hotels if item.id == offer_id), None)


def _clock(day: date, hhmm: str, tz) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def _shift_minutes(hhmm: str, minutes: int) -> str:
    hour, minute = (int(part) for part in hhmm.split(":"))
    total = (hour * 60 + minute + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _compose(trip: SwanTrip, pool: CandidateSet) -> TravelPackage:
    outbound = _offer(trip.flights, trip.outbound_id)
    inbound = _offer(trip.flights, trip.return_id)
    stays = [item for item in trip.hotels if item.id in trip.hotel_ids]
    brief = _brief(trip, outbound, inbound, stays)
    must = [item for item in trip.chosen_ids if trip.selection and item in (trip.selection.must_visit or [pick.candidate_id for pick in trip.selection.picks if pick.priority.value == "must"])]
    selection = PlanSelection(must_visit=must, maybe=[item for item in trip.chosen_ids if item not in must])
    visible = planning_profile(trip.profile)
    log.info("swan %s planning keys %s", trip.plan_id, sorted(visible.home.model_dump()))
    itinerary = build_plan(brief, selection, pool, plan_id=trip.plan_id, place=trip.request.place)
    itinerary = _lighten_first_day(itinerary, outbound, trip.profile)
    itinerary = _fit_budget(itinerary, trip, outbound, inbound, stays)
    reasons = _reasons(outbound, inbound, stays, trip)
    totals = _totals(outbound, inbound, stays, itinerary)
    return TravelPackage(
        plan_id=trip.plan_id,
        outbound=outbound,
        return_flight=inbound,
        hotels=[HotelStay(offer=stay, check_in=stay.check_in or trip.request.start_date, check_out=stay.check_out or trip.request.end_date) for stay in stays],
        itinerary=itinerary,
        totals=totals,
        reasons=reasons,
    )


def _clock_zone(trip: SwanTrip, outbound: FlightOffer | None):
    if trip.request.place is not None:
        return ZoneInfo(trip.request.place.timezone)
    if outbound is not None and outbound.segments[-1].arrive_at.tzinfo is not None:
        return outbound.segments[-1].arrive_at.tzinfo
    return timezone.utc


def _timezone_name(zone) -> str:
    key = getattr(zone, "key", None)
    if isinstance(key, str) and key:
        return key
    return "UTC"


def _brief(trip: SwanTrip, outbound: FlightOffer | None, inbound: FlightOffer | None, stays: list[HotelOffer]) -> TripBrief:
    start = date.fromisoformat(trip.request.start_date)
    end = date.fromisoformat(trip.request.end_date)
    tz = _clock_zone(trip, outbound)
    wake = _shift_minutes(trip.profile.sleep.wake_time, 45)
    sleep = _shift_minutes(trip.profile.sleep.sleep_time, -60)
    lodging = []
    for stay in stays:
        check_in = datetime.fromisoformat(f"{stay.check_in or trip.request.start_date}T15:00:00")
        check_out = datetime.fromisoformat(f"{stay.check_out or trip.request.end_date}T11:00:00")
        lodging.append(Lodging(
            name=stay.name, location=stay.location,
            check_in=check_in.replace(tzinfo=tz), check_out=check_out.replace(tzinfo=tz),
        ))
    density = trip.selection.daily_density if trip.selection else PACE_FROM_PROFILE(trip.profile)
    pace = PACE[density]
    return TripBrief(
        destination=trip.request.destination,
        timezone=_timezone_name(tz),
        arrival=outbound.segments[-1] if outbound else None,
        departure=inbound.segments[0] if inbound else None,
        lodging=lodging,
        start_date=_clock(start, "00:00", tz),
        end_date=_clock(end, "00:00", tz),
        budget=trip.request.budget or Decimal("2500"),
        interests=trip.profile.travel.interests,
        pace=pace,
        preferred_modes=trip.profile.travel.preferred_modes,
        daily_start=wake,
        daily_end=sleep,
    )


def _lighten_first_day(itinerary: Itinerary, outbound: FlightOffer | None, profile: UserProfile) -> Itinerary:
    if not profile.sleep.jet_lag_buffer or outbound is None or outbound.duration_min < 480:
        return itinerary
    if not itinerary.days:
        return itinerary
    first = itinerary.days[0]
    kept = []
    seen = 0
    for stop in first.stops:
        if stop.kind in {StopKind.ATTRACTION, StopKind.MERCHANT}:
            seen += 1
            if seen > 1:
                continue
        kept.append(stop)
    if len(kept) == len(first.stops):
        return itinerary
    days = [_reflow_day(first, kept, itinerary.brief), *itinerary.days[1:]]
    warnings = [*itinerary.warnings, "Lighter first day after a long flight."]
    return itinerary.model_copy(update={"days": days, "warnings": warnings})


def _reflow_day(day: ItineraryDay, stops: list[Stop], brief: TripBrief) -> ItineraryDay:
    fixed = [stop for stop in stops if stop.kind not in {StopKind.ATTRACTION, StopKind.MERCHANT}]
    visits = [stop for stop in stops if stop.kind in {StopKind.ATTRACTION, StopKind.MERCHANT}]
    anchor = next((stop for stop in fixed if stop.kind == StopKind.LODGING and stop.id == "check-in"), None)
    if anchor is None:
        anchor = next((stop for stop in fixed if stop.kind == StopKind.ARRIVAL), None)
    if anchor is not None and visits:
        visits = schedule_stops(visits, anchor.location, anchor.end + timedelta(minutes=15), brief.preferred_modes)
    ordered = sorted([*fixed, *visits], key=lambda stop: stop.start)
    code = brief.arrival.to_place.code if brief.arrival and brief.arrival.to_place else None
    transfer = arrival_transfer_minutes(get_transport_profile(brief.destination), code)
    return day.model_copy(update={"stops": ordered, "legs": build_legs(ordered, brief.preferred_modes, transfer)})


def _fit_budget(itinerary: Itinerary, trip: SwanTrip, outbound, inbound, stays: list[HotelOffer]) -> Itinerary:
    limit = trip.request.budget or Decimal("2500")
    spent = _money(outbound) + _money(inbound) + sum((stay.total for stay in stays), Decimal("0"))
    warnings = list(itinerary.warnings)
    if spent > limit:
        warnings.append("Flights and hotels already use the trip budget, so activities were left out.")
        days = []
        for day in itinerary.days:
            days.append(day.model_copy(update={"stops": [stop for stop in day.stops if stop.quote is None]}))
        return itinerary.model_copy(update={"days": days, "bookable_total": Decimal("0"), "warnings": warnings})
    return itinerary.model_copy(update={"warnings": warnings}) if warnings != list(itinerary.warnings) else itinerary


def _money(offer: FlightOffer | None) -> Decimal:
    return offer.price if offer else Decimal("0")


def _totals(outbound, inbound, stays: list[HotelOffer], itinerary: Itinerary) -> PackageTotals:
    flights = _money(outbound) + _money(inbound)
    hotels = sum((stay.total for stay in stays), Decimal("0"))
    activities = itinerary.bookable_total
    savings = Decimal("0")
    for stay in stays:
        if stay.quote and stay.quote.viator_price:
            savings += stay.quote.viator_price - stay.quote.amount
    return PackageTotals(
        flights=flights, hotels=hotels, activities=activities,
        total=flights + hotels + activities, currency="USD", savings=savings,
    )


def _reasons(outbound, inbound, stays, trip: SwanTrip) -> list[str]:
    lines = []
    if outbound:
        lines.append(f"{outbound.carrier} outbound: " + "; ".join(outbound.why[:2]))
    if inbound:
        lines.append(f"{inbound.carrier} return: " + "; ".join(inbound.why[:2]))
    for stay in stays:
        lines.append(f"{stay.name}: " + "; ".join(stay.why[:2]))
    lines.append(f"Days run from {trip.profile.sleep.wake_time} wake, with 45 minutes to start.")
    return lines


def _shift_day_one(itinerary: Itinerary, arrival: datetime) -> Itinerary:
    if not itinerary.days:
        return itinerary
    first = itinerary.days[0]
    brief = itinerary.brief.model_copy(deep=True)
    if brief.arrival is not None:
        brief.arrival = brief.arrival.model_copy(update={"arrive_at": arrival})
    code = brief.arrival.to_place.code if brief.arrival and brief.arrival.to_place else None
    transfer = arrival_transfer_minutes(get_transport_profile(brief.destination), code)
    stops = []
    for stop in first.stops:
        if stop.kind == StopKind.ARRIVAL:
            stops.append(stop.model_copy(update={"start": arrival, "end": arrival + timedelta(minutes=DEPLANE_MIN)}))
        elif stop.kind == StopKind.LODGING and stop.id == "check-in" and brief.lodging:
            stops.append(arrival_lodging(brief, arrival + timedelta(minutes=DEPLANE_MIN + transfer)))
        else:
            stops.append(stop)
    days = [_reflow_day(first, stops, brief), *itinerary.days[1:]]
    return itinerary.model_copy(update={"brief": brief, "days": days})


def _scripted(trip: SwanTrip) -> bool:
    if os.environ.get("ROAM_SCRIPTED_AGENT") != "1":
        return False
    auto = trip.request.autonomy
    if auto.attractions != Autonomy.SWAN_DECIDES or auto.flights != Autonomy.SWAN_DECIDES or auto.hotels != Autonomy.SWAN_DECIDES:
        return False
    if trip.selection and trip.selection.mode == Autonomy.I_CHOOSE:
        return False
    return _package_file(trip.request.destination).exists()
