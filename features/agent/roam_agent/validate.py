from __future__ import annotations

from datetime import datetime, timedelta

from roam_contracts.geo import haversine_km
from roam_contracts.models import Itinerary, StopKind, TravelMode
from roam_tools.transport import arrival_transfer_minutes, get_transport_profile

SPEED_KMH = {"walk": 4.5, "bike": 12, "transit": 18, "taxi": 22, "car": 22}


def _buffer_hours(itinerary: Itinerary) -> int:
    segment = itinerary.brief.departure
    if segment is None:
        return 2
    origin = (segment.from_place.code or "").upper()
    dest = (segment.to_place.code or "").upper()
    domestic = origin in {"HND", "NRT", "KIX", "ITM", "NGO"} and dest in {"HND", "NRT", "KIX", "ITM", "NGO"}
    return 2 if domestic else 3


def _clock(moment: datetime, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _estimate_minutes(lat1, lng1, lat2, lng2, mode: TravelMode) -> int:
    distance = haversine_km(lat1, lng1, lat2, lng2) * 1.3
    speed = SPEED_KMH[mode.value]
    minutes = distance / speed * 60
    if mode == TravelMode.TRANSIT:
        minutes += 8
    return max(1, round(minutes)) if distance > 0 else 0


def validate_itinerary(itinerary: Itinerary) -> list[str]:
    errors: list[str] = []
    warnings = " ".join(itinerary.warnings)
    present = set()
    for day in itinerary.days:
        for stop in day.stops:
            present.add(stop.id)
            if stop.attraction is not None:
                present.add(stop.attraction.id)
            if stop.quote is not None:
                present.add(stop.quote.merchant_id)
    for must in itinerary.selection.must_visit:
        if must not in present and must not in warnings:
            errors.append(f"Must-visit {must} is missing and no warning explains it")

    profile = get_transport_profile(itinerary.brief.destination)
    code = None
    if itinerary.brief.arrival is not None and itinerary.brief.arrival.to_place.code:
        code = itinerary.brief.arrival.to_place.code
    transfer = arrival_transfer_minutes(profile, code)
    if itinerary.brief.arrival is not None:
        earliest = itinerary.brief.arrival.arrive_at + timedelta(minutes=transfer)
        for day in itinerary.days:
            for stop in day.stops:
                if stop.kind in {StopKind.ARRIVAL, StopKind.DEPARTURE}:
                    continue
                if stop.start < earliest and stop.kind != StopKind.LODGING:
                    errors.append(f"{stop.title} starts before arrival plus the {transfer} min transfer")
                if stop.kind == StopKind.LODGING and "check-out" in stop.id:
                    continue
    if itinerary.brief.departure is not None:
        latest = itinerary.brief.departure.depart_at - timedelta(hours=_buffer_hours(itinerary)) - timedelta(minutes=transfer)
        for day in itinerary.days:
            for stop in day.stops:
                if stop.kind in {StopKind.DEPARTURE, StopKind.LODGING, StopKind.ARRIVAL}:
                    continue
                if stop.end > latest and stop.start.date() == itinerary.brief.departure.depart_at.date():
                    errors.append(f"{stop.title} runs past departure minus buffer")

    for day in itinerary.days:
        ordered = sorted(day.stops, key=lambda stop: stop.start)
        for earlier, later in zip(ordered, ordered[1:]):
            if later.start < earlier.end:
                errors.append(f"{later.title} overlaps {earlier.title}")
        for stop in day.stops:
            if stop.kind in {StopKind.ARRIVAL, StopKind.DEPARTURE}:
                continue
            opening = _clock(stop.start, itinerary.brief.daily_start)
            closing = _clock(stop.start, itinerary.brief.daily_end)
            if stop.start < opening or stop.end > closing:
                errors.append(f"{stop.title} sits outside {itinerary.brief.daily_start}-{itinerary.brief.daily_end}")
        for leg in day.legs:
            if leg.source.value == "estimate":
                continue
            origin = next((stop for stop in day.stops if stop.id == leg.from_stop_id), None)
            dest = next((stop for stop in day.stops if stop.id == leg.to_stop_id), None)
            if origin is None or dest is None:
                errors.append(f"Leg {leg.from_stop_id} to {leg.to_stop_id} does not match a stop")
                continue
            expected = _estimate_minutes(origin.location.lat, origin.location.lng, dest.location.lat, dest.location.lng, leg.mode)
            if abs(leg.minutes - expected) > max(5, expected // 2):
                errors.append(f"Leg {leg.from_stop_id} to {leg.to_stop_id} claims {leg.minutes} min, estimate is {expected}")

    bookable = 0
    for day in itinerary.days:
        for stop in day.stops:
            if stop.quote is None or stop.status.value == "removed":
                continue
            bookable += int(stop.quote.amount * 100)
            if stop.quote.expires_at <= stop.start:
                errors.append(f"Quote for {stop.title} is already expired")
    if bookable > int(itinerary.brief.budget * 100):
        errors.append("Bookable total is over the trip budget")
    return errors
