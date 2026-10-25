from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from roam_contracts.geo import haversine_km
from roam_contracts.models import (
    Candidate,
    FlightOffer,
    HotelOffer,
    HotelStay,
    ItineraryDay,
    Leg,
    LegSource,
    Proposal,
    Stop,
    StopKind,
    Suggestion,
    SuggestionAction,
    SuggestionActionName,
    SuggestionKind,
    SuggestionStatus,
    TravelMode,
    TravelPackage,
    UserProfile,
)

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
VISITS = {StopKind.ATTRACTION, StopKind.MERCHANT}
BUFFER_MIN = 10
SPEED_KMH = {
    TravelMode.WALK: 4.5,
    TravelMode.BIKE: 12,
    TravelMode.TRANSIT: 18,
    TravelMode.TAXI: 22,
    TravelMode.CAR: 22,
}
WINDOWS = {
    "red_eye": (0, 5),
    "early_morning": (5, 8),
    "morning": (8, 12),
    "afternoon": (12, 17),
    "evening": (17, 22),
}
RELAXED_DAY = re.compile(r"\bmake day (\d+) more relaxed\b", re.I)
LOCKED = {SuggestionStatus.REJECTED, SuggestionStatus.BOOKED}
KEPT = {SuggestionStatus.ACCEPTED, SuggestionStatus.BOOKED}
WORDS: list[tuple[re.Pattern[str], str, object]] = [
    (re.compile(r"cheap|less expensive|lower price", re.I), "cheaper", True),
    (re.compile(r"nonstop|non-stop|direct", re.I), "max_stops", 0),
    (re.compile(r"early morning", re.I), "time_of_day", "early_morning"),
    (re.compile(r"\bmorning\b", re.I), "time_of_day", "morning"),
    (re.compile(r"afternoon", re.I), "time_of_day", "afternoon"),
    (re.compile(r"evening", re.I), "time_of_day", "evening"),
    (re.compile(r"\bgion\b", re.I), "area", "Gion"),
    (re.compile(r"arashiyama", re.I), "area", "Arashiyama"),
    (re.compile(r"downtown|central", re.I), "area", "Downtown"),
    (re.compile(r"food|eat|market", re.I), "category", "food"),
    (re.compile(r"nature|garden|park|walk", re.I), "category", "nature"),
    (re.compile(r"temple|shrine", re.I), "category", "temples"),
    (re.compile(r"museum|castle|history", re.I), "category", "museums"),
]


@dataclass(frozen=True)
class Catalog:
    flights: list[FlightOffer]
    hotels: list[HotelOffer]
    candidates: list[Candidate]


@dataclass(frozen=True)
class Change:
    proposal: Proposal
    rejected_ids: list[str]
    changed: bool
    reflowed: bool
    suggestion: Suggestion | None = None
    removed_title: str | None = None
    reason: str | None = None


def load_catalog() -> Catalog:
    flights = [FlightOffer.model_validate(row) for row in json.loads((FIXTURES / "flight_offers.json").read_text())]
    hotels = [HotelOffer.model_validate(row) for row in json.loads((FIXTURES / "hotel_offers.json").read_text())]
    candidates = [Candidate.model_validate(row) for row in json.loads((FIXTURES / "candidates_kyoto.json").read_text())["candidates"]]
    return Catalog(flights, hotels, candidates)


def relaxed_day_number(text: str) -> int | None:
    found = RELAXED_DAY.search(text)
    return int(found.group(1)) if found else None


def read_constraints(text: str | None, explicit: dict | None) -> dict:
    found: dict = {}
    if text:
        for pattern, key, value in WORDS:
            if pattern.search(text):
                found.setdefault(key, value)
    for key, value in (explicit or {}).items():
        if value is not None:
            found[key] = value
    return found


def remember_reason(profile: UserProfile, reason: str) -> UserProfile:
    if reason in profile.travel.avoid:
        return profile
    travel = profile.travel.model_copy(update={"avoid": [*profile.travel.avoid, reason]})
    return profile.model_copy(update={"travel": travel})


def alternatives(proposal: Proposal, rejected_ids: list[str], sid: str, constraints: dict | None = None) -> list[Suggestion]:
    row = _row(proposal, sid)
    if row is None:
        return []
    wanted = read_constraints((constraints or {}).get("text"), constraints)
    return [option for option in _options(proposal, rejected_ids, row) if _fits(option, row, wanted)][:3]


def apply_action(proposal: Proposal, rejected_ids: list[str], action: SuggestionAction, catalog: Catalog) -> Change:
    row = _row(proposal, action.suggestion_id)
    if row is None or row.status in LOCKED:
        return Change(proposal, list(rejected_ids), False, False)
    if action.action == SuggestionActionName.ACCEPT:
        updated = row.model_copy(update={"status": SuggestionStatus.ACCEPTED})
        return Change(_set_row(proposal, updated), list(rejected_ids), True, False, updated)
    if action.action == SuggestionActionName.MODIFY and action.alternative_id:
        pick = next((option for option in _options(proposal, rejected_ids, row, catalog) if option.id == action.alternative_id), None)
        if pick is None:
            return Change(proposal, list(rejected_ids), False, False)
        return _swap(proposal, rejected_ids, row, pick, SuggestionStatus.ACCEPTED)
    if action.action == SuggestionActionName.REJECT:
        if row.kind in {SuggestionKind.ATTRACTION, SuggestionKind.TRANSFER}:
            return _drop(proposal, rejected_ids, row, action.reason)
        rejected = [*rejected_ids, _item_id(row)]
        pick = next(iter(_options(proposal, rejected, row, catalog)), None)
        if pick is None:
            updated = row.model_copy(update={"status": SuggestionStatus.REJECTED})
            return Change(_set_row(proposal, updated), rejected, True, False, updated, reason=action.reason)
        change = _swap(proposal, rejected, row, pick, SuggestionStatus.REPLACED)
        return Change(change.proposal, rejected, True, change.reflowed, change.suggestion, reason=action.reason)
    return Change(proposal, list(rejected_ids), False, False)


def accept_all(proposal: Proposal) -> Proposal:
    rows = [
        row.model_copy(update={"status": SuggestionStatus.ACCEPTED})
        if row.status in {SuggestionStatus.PROPOSED, SuggestionStatus.REPLACED}
        else row
        for row in proposal.suggestions
    ]
    return proposal.model_copy(update={"suggestions": rows})


def relax_day(proposal: Proposal, rejected_ids: list[str], day_number: int) -> Change:
    days = proposal.package.itinerary.days
    if day_number < 1 or day_number > len(days):
        return Change(proposal, list(rejected_ids), False, False)
    protected = {row.item.id for row in proposal.suggestions if row.kind == SuggestionKind.ATTRACTION and row.status in KEPT}
    victims = [stop for stop in days[day_number - 1].stops if stop.kind == StopKind.ATTRACTION and stop.id not in protected]
    if not victims:
        return Change(proposal, list(rejected_ids), False, False)
    target = victims[-1]
    row = next((item for item in proposal.suggestions if item.kind == SuggestionKind.ATTRACTION and item.item.id == target.id), None)
    package = _drop_stop(proposal.package, target.id)
    updated = None
    if row is not None:
        updated = row.model_copy(update={"status": SuggestionStatus.REJECTED})
        proposal = _set_row(proposal, updated)
    proposal = _retotal(proposal.model_copy(update={"package": package}))
    return Change(proposal, list(rejected_ids), True, True, updated, target.title)


def _row(proposal: Proposal, sid: str) -> Suggestion | None:
    return next((row for row in proposal.suggestions if row.id == sid), None)


def _item_id(row: Suggestion) -> str:
    if row.kind == SuggestionKind.FLIGHT:
        return row.item.id
    if row.kind == SuggestionKind.HOTEL:
        return row.item.offer.id
    return row.item.id


def _set_row(proposal: Proposal, row: Suggestion) -> Proposal:
    return proposal.model_copy(update={
        "suggestions": [row if item.id == row.id else item for item in proposal.suggestions],
    })


def _options(proposal: Proposal, rejected_ids: list[str], row: Suggestion, catalog: Catalog | None = None) -> list[Suggestion]:
    catalog = catalog or load_catalog()
    skip = set(rejected_ids)
    package = proposal.package
    if row.kind == SuggestionKind.FLIGHT:
        current = row.item
        skip.update(offer.id for offer in (package.outbound, package.return_flight) if offer is not None)
        offers = [offer for offer in catalog.flights if offer.direction == current.direction and offer.id not in skip]
        offers.sort(key=lambda offer: offer.score, reverse=True)
        return [
            Suggestion(id=offer.id, kind=SuggestionKind.FLIGHT, item=offer, why=list(offer.why), alternatives_available=True, required=True)
            for offer in offers
        ]
    if row.kind == SuggestionKind.HOTEL:
        current = row.item
        skip.update(stay.offer.id for stay in package.hotels)
        offers = [offer for offer in catalog.hotels if offer.id not in skip]
        offers.sort(key=lambda offer: offer.score, reverse=True)
        rows = []
        for offer in offers:
            stay = HotelStay(offer=offer, check_in=offer.check_in or current.check_in, check_out=offer.check_out or current.check_out)
            rows.append(Suggestion(
                id=offer.id, kind=SuggestionKind.HOTEL, item=stay, why=list(offer.why), alternatives_available=True, required=True,
            ))
        return rows
    skip.update(stop.id for day in package.itinerary.days for stop in day.stops)
    skip.update(_item_id(item) for item in proposal.suggestions)
    current = row.item
    places = [candidate for candidate in catalog.candidates if candidate.attraction is not None and candidate.id not in skip]
    places.sort(key=lambda candidate: candidate.attraction.popularity, reverse=True)
    rows = []
    for candidate in places:
        place = candidate.attraction
        assert place is not None
        stop = Stop(
            id=candidate.id, kind=StopKind.ATTRACTION, start=current.start,
            end=current.start + timedelta(minutes=place.typical_duration_min),
            location=place.location, title=place.name, attraction=place,
        )
        why = [part for part in (place.category, place.area, f"{place.typical_duration_min} min") if part]
        rows.append(Suggestion(id=candidate.id, kind=SuggestionKind.ATTRACTION, item=stop, why=why, alternatives_available=True))
    return rows


def _fits(option: Suggestion, row: Suggestion, wanted: dict) -> bool:
    if option.kind == SuggestionKind.FLIGHT and row.kind == SuggestionKind.FLIGHT:
        offer = option.item
        hour = offer.segments[0].depart_at.hour
        window = wanted.get("time_of_day")
        bounds = WINDOWS.get(window) if window and window != "any" else None
        if bounds is not None and (hour < bounds[0] or hour >= bounds[1]):
            return False
        if wanted.get("max_stops") is not None and offer.stops > wanted["max_stops"]:
            return False
        if wanted.get("airline") and offer.carrier != wanted["airline"]:
            return False
        if wanted.get("max_price") is not None and offer.price > Decimal(str(wanted["max_price"])):
            return False
        if wanted.get("cheaper") and offer.price >= row.item.price:
            return False
        return True
    if option.kind == SuggestionKind.HOTEL and row.kind == SuggestionKind.HOTEL:
        offer = option.item.offer
        if wanted.get("max_price") is not None and offer.price_per_night > Decimal(str(wanted["max_price"])):
            return False
        if wanted.get("cheaper") and offer.price_per_night >= row.item.offer.price_per_night:
            return False
        if wanted.get("min_stars") is not None and (offer.stars or 0) < wanted["min_stars"]:
            return False
        if wanted.get("area") and offer.area != wanted["area"]:
            return False
        return True
    if option.kind == SuggestionKind.ATTRACTION:
        place = option.item.attraction
        if wanted.get("category") and (place is None or place.category != wanted["category"]):
            return False
        if wanted.get("area") and (place is None or place.area != wanted["area"]):
            return False
        return True
    return False


def _swap(proposal: Proposal, rejected_ids: list[str], row: Suggestion, pick: Suggestion, status: SuggestionStatus) -> Change:
    package = proposal.package
    reflowed = False
    if row.kind == SuggestionKind.HOTEL and pick.kind == SuggestionKind.HOTEL:
        package = _swap_hotel(package, row.item, pick.item)
        reflowed = True
    elif row.kind == SuggestionKind.FLIGHT and pick.kind == SuggestionKind.FLIGHT:
        package = _swap_flight(package, pick.item)
        reflowed = True
    elif row.kind in {SuggestionKind.ATTRACTION, SuggestionKind.TRANSFER} and pick.kind == SuggestionKind.ATTRACTION:
        package = _swap_stop(package, row.item, pick.item)
        reflowed = True
    else:
        return Change(proposal, list(rejected_ids), False, False)
    updated = row.model_copy(update={"item": pick.item, "why": list(pick.why), "status": status})
    proposal = _retotal(_set_row(proposal.model_copy(update={"package": package}), updated))
    return Change(proposal, list(rejected_ids), True, reflowed, updated)


def _drop(proposal: Proposal, rejected_ids: list[str], row: Suggestion, reason: str | None) -> Change:
    package = _drop_stop(proposal.package, row.item.id)
    updated = row.model_copy(update={"status": SuggestionStatus.REJECTED})
    proposal = _retotal(_set_row(proposal.model_copy(update={"package": package}), updated))
    return Change(proposal, list(rejected_ids), True, True, updated, row.item.title, reason)


def _swap_hotel(package: TravelPackage, current: HotelStay, stay: HotelStay) -> TravelPackage:
    old_name = current.offer.name
    offer = stay.offer
    index = next(at for at, item in enumerate(package.hotels) if item.offer.id == current.offer.id)
    hotels = [stay if at == index else item for at, item in enumerate(package.hotels)]
    lodging = [
        item.model_copy(update={"name": offer.name, "location": offer.location}) if at == index else item
        for at, item in enumerate(package.itinerary.brief.lodging)
    ]
    days = []
    for day in package.itinerary.days:
        stops = []
        for stop in day.stops:
            if stop.kind == StopKind.LODGING and old_name in stop.title:
                stops.append(stop.model_copy(update={"title": stop.title.replace(old_name, offer.name), "location": offer.location}))
            else:
                stops.append(stop)
        days.append(day.model_copy(update={"stops": stops}))
    brief = package.itinerary.brief.model_copy(update={"lodging": lodging})
    itinerary = package.itinerary.model_copy(update={"brief": brief, "days": days})
    return package.model_copy(update={"hotels": hotels, "itinerary": itinerary})


def _swap_flight(package: TravelPackage, offer: FlightOffer) -> TravelPackage:
    if offer.direction == "outbound":
        arrived = offer.segments[-1]
        days = []
        for index, day in enumerate(package.itinerary.days):
            arrival = next((stop for stop in day.stops if stop.kind == StopKind.ARRIVAL), None)
            if index != 0 or arrival is None:
                days.append(day)
                continue
            late = max(0, round((arrived.arrive_at - arrival.start).total_seconds() / 60))
            stops = []
            for stop in day.stops:
                if stop.kind == StopKind.ARRIVAL:
                    stops.append(stop.model_copy(update={
                        "start": arrived.arrive_at,
                        "end": arrived.arrive_at + timedelta(minutes=20),
                        "title": f"Arrive {arrived.number or offer.carrier} at {arrived.to_place.name}",
                    }))
                elif stop.start > arrival.start:
                    stops.append(_move(stop, late))
                else:
                    stops.append(stop)
            days.append(day.model_copy(update={"stops": stops}))
        itinerary = package.itinerary.model_copy(update={"days": days})
        return package.model_copy(update={"outbound": offer, "itinerary": itinerary})
    departs = offer.segments[0]
    days = []
    for day in package.itinerary.days:
        stops = [
            stop.model_copy(update={
                "start": departs.depart_at,
                "end": departs.depart_at + timedelta(minutes=20),
                "title": f"Depart {departs.number or offer.carrier} from {departs.from_place.name}",
            }) if stop.kind == StopKind.DEPARTURE else stop
            for stop in day.stops
        ]
        days.append(day.model_copy(update={"stops": stops}))
    itinerary = package.itinerary.model_copy(update={"days": days})
    return package.model_copy(update={"return_flight": offer, "itinerary": itinerary})


def _swap_stop(package: TravelPackage, current: Stop, nxt: Stop) -> TravelPackage:
    def change(day: ItineraryDay) -> ItineraryDay:
        index = next(at for at, stop in enumerate(day.stops) if stop.id == current.id)
        placed = nxt.model_copy(update={"start": current.start, "end": current.start + (nxt.end - nxt.start)})
        stops = [placed if at == index else stop for at, stop in enumerate(day.stops)]
        legs = _relink(day, stops)
        before = _leg_after(day.legs, current.id)
        after = _leg_after(legs, placed.id)
        late = round((placed.end - current.end).total_seconds() / 60)
        late += (after.minutes if after else 0) - (before.minutes if before else 0)
        moved = [_move(stop, late) if at > index and stop.kind in VISITS else stop for at, stop in enumerate(stops)]
        return day.model_copy(update={"stops": moved, "legs": legs})

    return _map_day(package, current.id, change)


def _drop_stop(package: TravelPackage, stop_id: str) -> TravelPackage:
    def change(day: ItineraryDay) -> ItineraryDay:
        index = next(at for at, stop in enumerate(day.stops) if stop.id == stop_id)
        removed = day.stops[index]
        stops = [stop for stop in day.stops if stop.id != stop_id]
        if not stops:
            return day.model_copy(update={"stops": [], "legs": []})
        legs = _relink(day, stops)
        following = stops[index] if index < len(stops) else None
        if following is None or following.kind not in VISITS:
            return day.model_copy(update={"stops": stops, "legs": legs})
        previous = stops[index - 1] if index else None
        bridge = _leg_after(legs, previous.id) if previous is not None else None
        start = previous.end + timedelta(minutes=bridge.minutes + BUFFER_MIN) if previous is not None and bridge is not None else removed.start
        early = max(0, round((following.start - start).total_seconds() / 60))
        moved = [_move(stop, -early) if at >= index and stop.kind in VISITS else stop for at, stop in enumerate(stops)]
        return day.model_copy(update={"stops": moved, "legs": legs})

    return _map_day(package, stop_id, change)


def _map_day(package: TravelPackage, stop_id: str, change) -> TravelPackage:
    days = [change(day) if any(stop.id == stop_id for stop in day.stops) else day for day in package.itinerary.days]
    return package.model_copy(update={"itinerary": package.itinerary.model_copy(update={"days": days})})


def _relink(day: ItineraryDay, stops: list[Stop]) -> list[Leg]:
    legs = []
    for index, stop in enumerate(stops[1:], start=1):
        origin = stops[index - 1]
        kept = next((leg for leg in day.legs if leg.from_stop_id == origin.id and leg.to_stop_id == stop.id), None)
        if kept is not None:
            legs.append(kept)
            continue
        mode = next((leg.mode for leg in day.legs if leg.from_stop_id == origin.id), TravelMode.WALK)
        legs.append(_estimate(origin, stop, mode))
    return legs


def _leg_after(legs: list[Leg], stop_id: str) -> Leg | None:
    return next((leg for leg in legs if leg.from_stop_id == stop_id), None)


def _estimate(origin: Stop, dest: Stop, mode: TravelMode) -> Leg:
    km = haversine_km(origin.location.lat, origin.location.lng, dest.location.lat, dest.location.lng)
    minutes = (km * 1.3) / SPEED_KMH[mode] * 60
    if mode == TravelMode.TRANSIT:
        minutes += 8
    return Leg(
        from_stop_id=origin.id, to_stop_id=dest.id, mode=mode,
        minutes=max(1, round(minutes)), distance_km=round(km * 10) / 10, source=LegSource.ESTIMATE,
    )


def _move(stop: Stop, minutes: int) -> Stop:
    if not minutes:
        return stop
    delta = timedelta(minutes=minutes)
    return stop.model_copy(update={"start": stop.start + delta, "end": stop.end + delta})


def _money(rows) -> Decimal:
    return sum((row for row in rows), Decimal("0"))


def _retotal(proposal: Proposal) -> Proposal:
    package = proposal.package
    flights = _money(offer.price for offer in (package.outbound, package.return_flight) if offer is not None)
    hotels = _money(stay.offer.total for stay in package.hotels)
    activities = _money(stop.quote.amount for day in package.itinerary.days for stop in day.stops if stop.quote is not None)
    savings = _money(
        stay.offer.quote.viator_price - stay.offer.quote.amount
        for stay in package.hotels
        if stay.offer.quote is not None and stay.offer.quote.viator_price is not None
    )
    totals = package.totals.model_copy(update={
        "flights": flights, "hotels": hotels, "activities": activities,
        "total": flights + hotels + activities, "savings": savings,
    })
    package = package.model_copy(update={"totals": totals})
    return proposal.model_copy(update={"package": package, "totals": totals})
