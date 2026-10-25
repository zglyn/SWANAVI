from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from roam_agent.validate import validate_itinerary
from roam_contracts.models import (
    Attraction,
    Candidate,
    CandidateKind,
    CandidateSet,
    Category,
    ChatMessage,
    ChatRole,
    ConversationFixture,
    ConversationPhase,
    EventLevel,
    EventSource,
    FareConditions,
    FlightOffer,
    GeoPoint,
    HotelOffer,
    HotelSource,
    HotelStay,
    InspectorEvent,
    Itinerary,
    ItineraryDay,
    Leg,
    LegSource,
    Lodging,
    MerchantProfile,
    PackageTotals,
    Pace,
    PlaceRef,
    PlanSelection,
    Proposal,
    Quote,
    ScriptedChange,
    SegmentMode,
    Stop,
    StopKind,
    Suggestion,
    SuggestionAction,
    SuggestionActionName,
    SuggestionKind,
    SuggestionStatus,
    TravelMode,
    TravelPackage,
    TravelSegment,
    TripBrief,
    TripConversation,
    TripFacts,
    TripOrigin,
    TripRequest,
)
from roam_tools.demo_city import load, local_dt

WHEN = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)


def _h(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest().upper()


def _point(lat: float, lng: float) -> GeoPoint:
    return GeoPoint(lat=lat, lng=lng)


def _merchant_row(city: dict, merchant_id: str) -> dict:
    return next(row for row in city["merchants"] if row["id"] == merchant_id)


def _attraction_row(city: dict, attraction_id: str) -> dict:
    return next(row for row in city["attractions"] if row["id"] == attraction_id)


def _hotel_row(city: dict, primary: bool) -> dict:
    return next(row for row in city["hotels"] if row["primary"] is primary)


def _place(city: dict, token: str) -> GeoPoint:
    if token == "jfk":
        airport = city["destination_airport"]
        return _point(airport["lat"], airport["lng"])
    if token == "hotel":
        hotel = _hotel_row(city, True)
        return _point(hotel["lat"], hotel["lng"])
    merchant = next((row for row in city["merchants"] if row["id"] == token), None)
    if merchant is not None:
        return _point(merchant["lat"], merchant["lng"])
    attraction = _attraction_row(city, token)
    return _point(attraction["lat"], attraction["lng"])


def merchants(city: dict | None = None) -> list[MerchantProfile]:
    city = city or load()
    found = []
    for row in city["merchants"]:
        found.append(MerchantProfile(
            merchant_id=row["id"],
            name=row["name"],
            category=Category(row["category"]),
            location=_point(row["lat"], row["lng"]),
            city=city["destination"],
            country=city["country_code"],
            xrpl_address=f"r{row['id'].replace('-', '')}PLACEHOLDER",
            mcp_url=f"http://localhost:8001/m/{row['id']}/mcp",
            pubkey_ed25519="00" * 32,
        ))
    return found


def quotes(city: dict | None = None) -> list[Quote]:
    city = city or load()
    zone = city["timezone"]
    valid = timedelta(hours=city["quote_valid_hours"])
    escrow = timedelta(hours=city["escrow_cancel_after_hours"])
    found = []
    for row in city["merchants"]:
        start = local_dt(row["slot_start"], zone)
        end = start + timedelta(hours=row["hours"])
        found.append(Quote(
            invoice_id=_h(row["id"], row["sku"], start.isoformat()),
            merchant_id=row["id"],
            merchant_name=row["name"],
            merchant_address=f"r{row['id'].replace('-', '')}PLACEHOLDER",
            sku=row["sku"],
            title=row["title"],
            category=Category(row["category"]),
            amount=Decimal(row["amount"]),
            currency="RLUSD",
            viator_price=None,
            slot_start=start,
            slot_end=end,
            location=_point(row["lat"], row["lng"]),
            cancel_after=end + escrow,
            expires_at=end + valid,
            merchant_signature="00" * 64,
            merchant_verified=row["verified"],
        ))
    return found


def _attraction(row: dict) -> Attraction:
    return Attraction(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        location=_point(row["lat"], row["lng"]),
        area=row["area"],
        description=row["description"],
        popularity=row["popularity"],
        typical_duration_min=row["minutes"],
        opening_hours="09:00-17:00",
        price=None if row["free"] else Decimal("5.00"),
        free=row["free"],
        source="curated",
    )


def candidate_set(city: dict | None = None) -> CandidateSet:
    city = city or load()
    rows = [_attraction(row) for row in city["attractions"]]
    found = [Candidate(id=item.id, kind=CandidateKind.ATTRACTION, attraction=item) for item in rows]
    by_id = {merchant.merchant_id: merchant for merchant in merchants(city)}
    for quote in quotes(city):
        row = _merchant_row(city, quote.merchant_id)
        if not row["verified"]:
            continue
        found.append(Candidate(
            id=quote.merchant_id,
            kind=CandidateKind.MERCHANT,
            merchant=by_id[quote.merchant_id],
            quote=quote,
        ))
    return CandidateSet(plan_id=city["plan_id"], candidates=found, available_hours=24)


def _segment(city: dict, spec: dict, origin: dict, dest: dict) -> TravelSegment:
    return TravelSegment(
        mode=SegmentMode.FLIGHT,
        carrier=spec["carrier"],
        number=spec["number"],
        from_place=PlaceRef(code=origin["code"], name=origin["name"], location=_point(origin["lat"], origin["lng"])),
        to_place=PlaceRef(code=dest["code"], name=dest["name"], location=_point(dest["lat"], dest["lng"])),
        depart_at=local_dt(spec["depart_local"], origin["timezone"]),
        arrive_at=local_dt(spec["arrive_local"], dest["timezone"]),
        status="scheduled",
        source="fixture",
    )


def flight_offer(city: dict, key: str, direction: str) -> FlightOffer:
    spec = city["flights"][key]
    outbound = key == "outbound"
    origin = city["origin"] if outbound else city["destination_airport"]
    dest = city["destination_airport"] if outbound else city["origin"]
    if not outbound:
        origin = {**origin, "timezone": city["timezone"]}
        dest = {**dest, "timezone": city["origin"]["timezone"]}
    else:
        dest = {**dest, "timezone": city["timezone"]}
    return FlightOffer(
        id=spec["id"],
        segments=[_segment(city, spec, origin, dest)],
        carrier=spec["carrier"],
        stops=0,
        duration_min=spec["duration_min"],
        price=Decimal(spec["price"]),
        currency=city["currency"],
        fare_conditions=FareConditions(refundable=True, changeable=True),
        score=spec["score"],
        why=list(spec["why"]),
        deep_link=f"https://www.united.com/book/{spec['id']}",
        direction=direction,
    )


def hotel_offer(city: dict, row: dict) -> HotelOffer:
    primary = _hotel_row(city, True)
    return HotelOffer(
        id=row["id"],
        name=row["name"],
        stars=row["stars"],
        location=_point(row["lat"], row["lng"]),
        area=row["area"],
        price_per_night=Decimal(row["price_per_night"]),
        total=Decimal(row["total"]),
        currency=city["currency"],
        amenities=["wifi"],
        refundable=True,
        avg_travel_min_to_attractions=15 if row["primary"] else 20,
        score=row["score"],
        why=list(row["why"]),
        source=HotelSource.PROVIDER,
        check_in=primary["check_in_local"][:10],
        check_out=primary["check_out_local"][:10],
    )


def brief(city: dict | None = None) -> TripBrief:
    city = city or load()
    zone = city["timezone"]
    outbound = flight_offer(city, "outbound", "outbound").segments[0]
    inbound = flight_offer(city, "return", "return").segments[0]
    hotel = _hotel_row(city, True)
    lodging = Lodging(
        name=hotel["name"],
        address=hotel["area"],
        location=_point(hotel["lat"], hotel["lng"]),
        check_in=local_dt(hotel["check_in_local"], zone),
        check_out=local_dt(hotel["check_out_local"], zone),
    )
    return TripBrief(
        destination=city["destination"],
        timezone=zone,
        arrival=outbound,
        departure=inbound,
        lodging=[lodging],
        start_date=local_dt(city["dates"]["start"] + "T00:00", zone),
        end_date=local_dt(city["dates"]["end"] + "T00:00", zone),
        budget=Decimal(city["budget"]),
        interests=list(city["interests"]),
        pace=Pace(city["pace"]),
        preferred_modes=[TravelMode.WALK, TravelMode.TRANSIT],
        daily_start=city["daily_start"],
        daily_end=city["daily_end"],
    )


def itinerary(city: dict | None = None) -> Itinerary:
    city = city or load()
    zone = city["timezone"]
    trip = brief(city)
    attractions = {row["id"]: _attraction(row) for row in city["attractions"]}
    by_sku = {quote.merchant_id: quote for quote in quotes(city)}
    days = []
    for day in city["days"]:
        stops = []
        for spec in day["stops"]:
            start = local_dt(spec["start"], zone)
            quote = by_sku.get(spec["id"]) if spec["kind"] == "merchant" else None
            attraction = attractions.get(spec["id"]) if spec["kind"] == "attraction" else None
            stops.append(Stop(
                id=spec["id"],
                kind=StopKind(spec["kind"]),
                start=start,
                end=start + timedelta(minutes=spec["minutes"]),
                location=_place(city, spec["at"]),
                title=spec["title"],
                attraction=attraction,
                quote=quote,
                required=spec["id"] in city["selection"]["must_visit"],
            ))
        legs = [
            Leg(
                from_stop_id=leg["from"],
                to_stop_id=leg["to"],
                mode=TravelMode(leg["mode"]),
                minutes=leg["minutes"],
                distance_km=leg["distance_km"],
                source=LegSource.ESTIMATE,
            )
            for leg in day["legs"]
        ]
        days.append(ItineraryDay(date=day["date"], stops=stops, legs=legs))
    bookable = sum((quote.amount for quote in by_sku.values() if _merchant_row(city, quote.merchant_id)["on_itinerary"]), Decimal("0"))
    return Itinerary(
        plan_id=city["plan_id"],
        brief=trip,
        selection=PlanSelection(**city["selection"]),
        days=days,
        transport_summary=city["transport_summary"],
        estimated_total=bookable,
        bookable_total=bookable,
        warnings=[],
    )


def flight_offers(city: dict | None = None) -> list[FlightOffer]:
    city = city or load()
    return [flight_offer(city, "outbound", "outbound"), flight_offer(city, "return", "return")]


def hotel_offers(city: dict | None = None) -> list[HotelOffer]:
    city = city or load()
    return [hotel_offer(city, row) for row in city["hotels"]]


def package(city: dict | None = None) -> TravelPackage:
    city = city or load()
    plan = itinerary(city)
    outbound = flight_offer(city, "outbound", "outbound")
    inbound = flight_offer(city, "return", "return")
    stay_row = _hotel_row(city, True)
    stay = HotelStay(
        offer=hotel_offer(city, stay_row),
        check_in=stay_row["check_in_local"][:10],
        check_out=stay_row["check_out_local"][:10],
    )
    flights = outbound.price + inbound.price
    hotels_total = stay.offer.total
    activities = plan.bookable_total
    return TravelPackage(
        plan_id=city["plan_id"],
        outbound=outbound,
        return_flight=inbound,
        hotels=[stay],
        itinerary=plan,
        totals=PackageTotals(
            flights=flights,
            hotels=hotels_total,
            activities=activities,
            total=flights + hotels_total + activities,
            currency=city["currency"],
        ),
        reasons=["Demo data", city["transport_summary"]],
    )


def _at(minutes: int) -> datetime:
    return WHEN + timedelta(minutes=minutes)


def _facts(city: dict) -> TripFacts:
    return TripFacts(
        destination=city["destination"],
        origin=TripOrigin(from_home=False, airport_codes=[city["origin"]["code"]]),
        start_date=city["dates"]["start"],
        end_date=city["dates"]["end"],
        travellers=city["travellers"],
        pace=Pace(city["pace"]),
        interests=list(city["interests"]),
    )


def _label(iso: str) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[int(iso[5:7]) - 1]} {int(iso[8:10])}"


def _day_word(count: int) -> str:
    return {1: "one", 2: "two", 3: "three", 4: "four"}.get(count, str(count))


def _conversation(city: dict) -> TripConversation:
    start = _label(city["dates"]["start"])
    end = _label(city["dates"]["end"])
    days = _day_word(len(city["days"]))
    return TripConversation(
        trip_id=city["trip_id"],
        phase=ConversationPhase.PROPOSAL,
        brief=_facts(city),
        messages=[
            ChatMessage(id="m1", role=ChatRole.USER, text=city["opening_prompt"], created_at=_at(0)),
            ChatMessage(
                id="m2",
                role=ChatRole.ASSISTANT,
                text=(
                    f"{city['destination']} from {start} to {end} for {city['travellers']} travellers, "
                    f"leaving {city['origin']['code']}. I'll assume a mid-range budget. "
                    "You can change that later. Plan it whenever you are ready."
                ),
                created_at=_at(1),
            ),
            ChatMessage(id="m3", role=ChatRole.USER, text="Plan it now", created_at=_at(2)),
            ChatMessage(
                id="m4",
                role=ChatRole.ASSISTANT,
                text=f"Your {city['destination']} trip is ready. It has flights, a hotel, and {days} days of stops.",
                created_at=_at(3),
            ),
        ],
    )


def _replace(rows: list[Suggestion], sid: str, **changes) -> list[Suggestion]:
    return [row.model_copy(update=changes) if row.id == sid else row for row in rows]


def _swap_hotel(pack: TravelPackage, stay: HotelStay) -> TravelPackage:
    updated = pack.model_copy(deep=True)
    updated.hotels = [stay]
    lodging = updated.itinerary.brief.lodging
    if lodging:
        lodging[0] = lodging[0].model_copy(update={"name": stay.offer.name, "location": stay.offer.location})
    for day in updated.itinerary.days:
        day.stops = [
            stop.model_copy(update={
                "title": stop.title.replace(pack.hotels[0].offer.name, stay.offer.name),
                "location": stay.offer.location,
            }) if stop.kind == StopKind.LODGING else stop
            for stop in day.stops
        ]
    return updated


def _drop_stop(pack: TravelPackage, stop_id: str) -> TravelPackage:
    updated = pack.model_copy(deep=True)
    for day in updated.itinerary.days:
        if not any(stop.id == stop_id for stop in day.stops):
            continue
        removed = next(stop for stop in day.stops if stop.id == stop_id)
        rest = [stop for stop in day.stops if stop.id != stop_id]
        if not rest:
            day.stops = []
            day.legs = []
            continue
        delta = rest[0].start - removed.start
        day.stops = [stop.model_copy(update={"start": stop.start - delta, "end": stop.end - delta}) for stop in rest]
        day.legs = [leg for leg in day.legs if leg.from_stop_id != stop_id and leg.to_stop_id != stop_id]
    return updated


def conversation_fixture(city: dict | None = None, pack: TravelPackage | None = None) -> ConversationFixture:
    city = city or load()
    pack = pack or package(city)
    base = TravelPackage.model_validate(pack.model_dump(mode="json", by_alias=True))
    proposal = Proposal.from_package(city["trip_id"], base)
    suggestions = proposal.suggestions
    accepted = proposal.model_copy(update={
        "suggestions": _replace(suggestions, "sug-out", status=SuggestionStatus.ACCEPTED),
    })
    alternate = hotel_offer(city, _hotel_row(city, False))
    stay = HotelStay(offer=alternate, check_in=alternate.check_in or city["dates"]["start"], check_out=alternate.check_out or city["dates"]["end"])
    swapped = _swap_hotel(base, stay)
    hotel_id = next(row.id for row in suggestions if row.kind == SuggestionKind.HOTEL)
    hotel_totals = PackageTotals(
        flights=base.totals.flights,
        hotels=stay.offer.total,
        activities=base.totals.activities,
        total=base.totals.flights + stay.offer.total + base.totals.activities,
        currency=base.totals.currency,
    )
    modified = proposal.model_copy(update={
        "package": swapped,
        "totals": hotel_totals,
        "suggestions": _replace(suggestions, hotel_id, status=SuggestionStatus.ACCEPTED, item=stay, why=list(stay.offer.why)),
    })
    dropped = _drop_stop(base, city["reject_stop_id"])
    rejected = proposal.model_copy(update={
        "package": dropped,
        "suggestions": _replace(suggestions, f"sug-stop-{city['reject_stop_id']}", status=SuggestionStatus.REJECTED),
    })
    return ConversationFixture(
        conversation=_conversation(city),
        proposal=proposal,
        accept=ScriptedChange(
            action=SuggestionAction(suggestion_id="sug-out", action=SuggestionActionName.ACCEPT),
            proposal=accepted,
        ),
        modify=ScriptedChange(
            action=SuggestionAction(suggestion_id=hotel_id, action=SuggestionActionName.MODIFY, alternative_id=stay.offer.id),
            proposal=modified,
        ),
        reject=ScriptedChange(
            action=SuggestionAction(
                suggestion_id=f"sug-stop-{city['reject_stop_id']}",
                action=SuggestionActionName.REJECT,
                reason="Bad time",
            ),
            proposal=rejected,
        ),
    )


def plan_events(city: dict, cset: CandidateSet, plan: Itinerary) -> list[InspectorEvent]:
    start = local_dt(city["dates"]["start"] + "T08:00", city["timezone"])

    def ev(i: int, type_: str, msg: str, **data) -> InspectorEvent:
        return InspectorEvent(
            id=f"plan-{i:03d}",
            ts=start + timedelta(seconds=2 * i),
            source=EventSource.AGENT,
            level=EventLevel.INFO,
            type=type_,
            message=msg,
            data=data,
        )

    return [
        ev(1, "plan.tool_call", f"Transport profile for {city['destination']}", plan_id=city["plan_id"], tool="get_transport_profile", summary=city["transport_summary"]),
        ev(2, "plan.tool_call", "Searching museums, food, and walks", plan_id=city["plan_id"], tool="search_attractions", summary=city["destination"]),
        ev(3, "plan.tool_call", "Finding demo shops", plan_id=city["plan_id"], tool="find_merchants", summary=city["destination"]),
        ev(4, "plan.candidates", "Candidates ready", candidates=cset.model_dump(mode="json")),
        ev(5, "plan.tool_call", "JFK to Midtown by AirTrain and subway (70 min)", plan_id=city["plan_id"], tool="get_transport_profile", summary="Arrival transfer"),
        ev(6, "plan.tool_call", "Walking times between Central Park and Midtown", plan_id=city["plan_id"], tool="optimize_route", summary="Four-day order"),
        ev(7, "plan.ready", "Itinerary ready", itinerary=plan.model_dump(mode="json")),
    ]


def trip_request(city: dict) -> TripRequest:
    return TripFacts(
        destination=city["destination"],
        origin=TripOrigin(from_home=False, place=city["origin"]["name"], airport_codes=[city["origin"]["code"]]),
        start_date=city["dates"]["start"],
        end_date=city["dates"]["end"],
        travellers=city["travellers"],
        budget=Decimal(city["budget"]),
        pace=Pace(city["pace"]),
        interests=list(city["interests"]),
    ).to_request()


def _dump(path: Path, obj) -> None:
    if isinstance(obj, list):
        data = [item.model_dump(mode="json", by_alias=True) if hasattr(item, "model_dump") else item for item in obj]
    elif hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json", by_alias=True)
    else:
        data = obj
    path.write_text(json.dumps(data, indent=2) + "\n")


def _merge(path: Path, rows: list, key: str) -> None:
    current = json.loads(path.read_text()) if path.exists() else []
    incoming = [row.model_dump(mode="json", by_alias=True) if hasattr(row, "model_dump") else row for row in rows]
    ids = {row[key] for row in incoming}
    kept = [row for row in current if row.get(key) not in ids]
    path.write_text(json.dumps(kept + incoming, indent=2) + "\n")


def _check_transfer(city: dict) -> None:
    jfk = next(row for row in city["transport"]["transfers"] if row["from_code"] == "JFK")
    minutes = min(option["minutes"] for option in jfk["options"])
    for day in city["days"]:
        for leg in day["legs"]:
            if leg["mode"] == "transit":
                if leg["minutes"] != minutes:
                    raise RuntimeError(f"{leg['from']} transfer is {leg['minutes']} min, JFK profile is {minutes}")


def write_plan(folder: Path) -> None:
    city = load()
    _check_transfer(city)
    _dump(folder.parents[1] / "features" / "agent" / "roam_tools" / "data" / "transport" / "new-york.json", {
        "place": city["transport"]["place"],
        "modes": city["transport"]["modes"],
        "passes": city["transport"]["passes"],
        "transfers": city["transport"]["transfers"],
        "tips": city["transport"]["tips"],
        "source": city["transport"]["source"],
    })
    plan = itinerary(city)
    errors = validate_itinerary(plan)
    if errors:
        raise RuntimeError("demo itinerary failed validation: " + "; ".join(errors))
    cset = candidate_set(city)
    pack = package(city)
    _dump(folder / "candidates_demo.json", cset)
    _dump(folder / "itinerary_demo.json", plan)
    _dump(folder / "package_demo.json", pack)
    _dump(folder / "plan_events_demo.json", plan_events(city, cset, plan))


def write_catalogs(folder: Path) -> None:
    city = load()
    _dump(folder / "trip_request_demo.json", trip_request(city))
    _merge(folder / "merchants.json", merchants(city), "merchant_id")
    _merge(folder / "quotes.json", quotes(city), "sku")
    _merge(folder / "flight_offers.json", flight_offers(city), "id")
    _merge(folder / "hotel_offers.json", hotel_offers(city), "id")


def write_conversation_file(folder: Path) -> None:
    city = load()
    pack = TravelPackage.model_validate(json.loads((folder / "package_demo.json").read_text()))
    _dump(folder / "conversation_demo.json", conversation_fixture(city, pack))
