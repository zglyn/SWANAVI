from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from roam_contracts.models import (
    Attraction,
    Candidate,
    CandidateKind,
    CandidateSet,
    EventLevel,
    EventSource,
    GeoPoint,
    InspectorEvent,
    Itinerary,
    ItineraryDay,
    Leg,
    LegSource,
    Lodging,
    MerchantProfile,
    Pace,
    PlaceRef,
    PlanSelection,
    PlanStatus,
    Quote,
    SegmentMode,
    SegmentStatus,
    Stop,
    StopKind,
    TravelMode,
    TravelSegment,
    TripBrief,
)

JST = timezone(timedelta(hours=9))
PLAN_ID = "kyoto-demo"

ATTRACTIONS = [
    ("bamboo-grove", "Arashiyama Bamboo Grove", "nature", 35.0170, 135.6716, "Arashiyama", "A walking path through towering bamboo.", 0.95, 45, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/5/56/Bamboo_grove_arashiyama.jpg/640px-Bamboo_grove_arashiyama.jpg"),
    ("tenryuji", "Tenryū-ji", "temples", 35.0156, 135.6737, "Arashiyama", "A Zen temple garden beside the bamboo grove.", 0.9, 60, False, "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Tenryuji_Kyoto05s3s4592.jpg/640px-Tenryuji_Kyoto05s3s4592.jpg"),
    ("fushimi-inari", "Fushimi Inari", "temples", 34.9671, 135.7727, "Fushimi", "Thousands of torii gates climbing the mountain.", 0.98, 90, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/FushimiInari_Torii.jpg/640px-FushimiInari_Torii.jpg"),
    ("kinkakuji", "Kinkaku-ji", "temples", 35.0394, 135.7292, "Kita", "The gold-leaf pavilion over a reflecting pond.", 0.97, 50, False, "https://upload.wikimedia.org/wikipedia/commons/thumb/8/84/Kinkaku-ji_the_Golden_Pavilion_in_Kyoto.jpg/640px-Kinkaku-ji_the_Golden_Pavilion_in_Kyoto.jpg"),
    ("kiyomizu", "Kiyomizu-dera", "temples", 34.9949, 135.7850, "Higashiyama", "A wooden stage looking over the city.", 0.93, 70, False, "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Kiyomizu.jpg/640px-Kiyomizu.jpg"),
    ("philosophers-path", "Philosopher's Path", "nature", 35.0270, 135.7980, "Higashiyama", "A canal walk lined with cherry trees.", 0.8, 50, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Philosopher%27s_Walk_Kyoto.jpg/640px-Philosopher%27s_Walk_Kyoto.jpg"),
    ("gion", "Gion", "nightlife", 35.0037, 135.7758, "Gion", "Lanterned streets of teahouses.", 0.88, 60, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/Gion_Kyoto.jpg/640px-Gion_Kyoto.jpg"),
    ("nishiki", "Nishiki Market", "food", 35.0050, 135.7649, "Downtown", "A covered market of pickles, tofu and seafood.", 0.86, 45, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Nishiki_Market.jpg/640px-Nishiki_Market.jpg"),
    ("nijo", "Nijō Castle", "museums", 35.0142, 135.7481, "Nakagyo", "A shogun's palace with nightingale floors.", 0.84, 75, False, "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/Nijo_Castle.jpg/640px-Nijo_Castle.jpg"),
    ("pontocho", "Pontocho", "food", 35.0038, 135.7712, "Pontocho", "A narrow alley of restaurants along the river.", 0.82, 40, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1e/Pontocho.jpg/640px-Pontocho.jpg"),
    ("arashiyama-park", "Arashiyama Park", "nature", 35.0152, 135.6788, "Arashiyama", "Riverbank park with views of the Togetsukyo bridge.", 0.7, 40, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Togetsukyo_Bridge.jpg/640px-Togetsukyo_Bridge.jpg"),
    ("imperial-palace", "Kyoto Imperial Palace", "museums", 35.0254, 135.7621, "Nakagyo", "Gardens of the former imperial residence.", 0.75, 60, True, "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Kyoto_Imperial_Palace.jpg/640px-Kyoto_Imperial_Palace.jpg"),
]


def _attr(row) -> Attraction:
    id_, name, category, lat, lng, area, description, popularity, minutes, free, image = row
    return Attraction(
        id=id_, name=name, category=category, location=GeoPoint(lat=lat, lng=lng), area=area,
        description=description, image_url=image, popularity=popularity, typical_duration_min=minutes,
        opening_hours="09:00-17:00", price=None if free else Decimal("5.00"), free=free, source="curated",
    )


def brief() -> TripBrief:
    arrival = TravelSegment(
        mode=SegmentMode.FLIGHT, carrier="JL", number="JL3020",
        from_place=PlaceRef(code="HND", name="Tokyo Haneda"),
        to_place=PlaceRef(code="KIX", name="Kansai International", location=GeoPoint(lat=34.4347, lng=135.2440)),
        depart_at=datetime(2026, 11, 14, 9, 20, tzinfo=JST),
        arrive_at=datetime(2026, 11, 14, 10, 35, tzinfo=JST),
        status=SegmentStatus.SCHEDULED, source="fixture",
    )
    departure = TravelSegment(
        mode=SegmentMode.FLIGHT, carrier="JL", number="JL3025",
        from_place=PlaceRef(code="KIX", name="Kansai International", location=GeoPoint(lat=34.4347, lng=135.2440)),
        to_place=PlaceRef(code="HND", name="Tokyo Haneda"),
        depart_at=datetime(2026, 11, 16, 18, 20, tzinfo=JST),
        arrive_at=datetime(2026, 11, 16, 19, 35, tzinfo=JST),
        status=SegmentStatus.SCHEDULED, source="fixture",
    )
    hotel = Lodging(
        name="Hotel Granvia Kyoto", address="Kyoto Station",
        location=GeoPoint(lat=34.9858, lng=135.7588),
        check_in=datetime(2026, 11, 14, 15, 0, tzinfo=JST),
        check_out=datetime(2026, 11, 16, 11, 0, tzinfo=JST),
    )
    return TripBrief(
        destination="Kyoto, Japan", timezone="Asia/Tokyo", arrival=arrival, departure=departure,
        lodging=[hotel], start_date=datetime(2026, 11, 14, tzinfo=JST), end_date=datetime(2026, 11, 16, tzinfo=JST),
        budget=Decimal("200.00"), interests=["temples", "nature", "food"], pace=Pace.BALANCED,
        preferred_modes=[TravelMode.WALK, TravelMode.TRANSIT, TravelMode.BIKE],
        daily_start="09:00", daily_end="21:00",
    )


def candidates(merchants: list[MerchantProfile], quotes: list[Quote]) -> CandidateSet:
    rows = [_attr(row) for row in ATTRACTIONS]
    found: list[Candidate] = [
        Candidate(id=a.id, kind=CandidateKind.ATTRACTION, attraction=a) for a in rows
    ]
    by_id = {m.merchant_id: m for m in merchants}
    for q in quotes:
        if q.merchant_id == "lucky-souvenir":
            continue
        merchant = by_id[q.merchant_id]
        found.append(Candidate(id=q.merchant_id, kind=CandidateKind.MERCHANT, merchant=merchant, quote=q))
    return CandidateSet(plan_id=PLAN_ID, candidates=found, available_hours=18)


def _stop(id_: str, kind: StopKind, start: datetime, minutes: int, loc: GeoPoint, title: str, **kw) -> Stop:
    return Stop(id=id_, kind=kind, start=start, end=start + timedelta(minutes=minutes), location=loc, title=title, **kw)


def itinerary(merchants: list[MerchantProfile], quotes: list[Quote]) -> Itinerary:
    trip = brief()
    hotel = trip.lodging[0]
    kix = GeoPoint(lat=34.4347, lng=135.2440)
    by_sku = {q.sku: q for q in quotes}
    grove = _attr(ATTRACTIONS[0])
    temple = _attr(ATTRACTIONS[1])
    day1_arrival = datetime(2026, 11, 14, 10, 35, tzinfo=JST)
    check_in = datetime(2026, 11, 14, 15, 0, tzinfo=JST)
    grove_start = datetime(2026, 11, 14, 16, 0, tzinfo=JST)
    matcha_start = datetime(2026, 11, 14, 17, 15, tzinfo=JST)
    day2_temple = datetime(2026, 11, 15, 9, 30, tzinfo=JST)
    tea_start = datetime(2026, 11, 15, 15, 0, tzinfo=JST)
    checkout = datetime(2026, 11, 16, 11, 0, tzinfo=JST)
    depart = datetime(2026, 11, 16, 18, 20, tzinfo=JST)
    day1 = [
        _stop("arrival", StopKind.ARRIVAL, day1_arrival, 20, kix, "Arrive JL3020 at KIX"),
        _stop("check-in", StopKind.LODGING, check_in, 30, hotel.location, "Check in at Hotel Granvia Kyoto"),
        _stop("bamboo-grove", StopKind.ATTRACTION, grove_start, 45, grove.location, grove.name, attraction=grove, required=True),
        _stop("kissa-matcha", StopKind.MERCHANT, matcha_start, 60, GeoPoint(lat=35.0136, lng=135.6779), "Matcha workshop", quote=by_sku["MATCHA-WS"], required=False),
    ]
    day2 = [
        _stop("tenryuji", StopKind.ATTRACTION, day2_temple, 60, temple.location, temple.name, attraction=temple, required=True),
        _stop("gion-tea", StopKind.MERCHANT, tea_start, 60, GeoPoint(lat=35.0036, lng=135.7750), "Tea ceremony", quote=by_sku["TEA-SET"]),
    ]
    day3 = [
        _stop("check-out", StopKind.LODGING, checkout, 20, hotel.location, "Check out"),
        _stop("departure", StopKind.DEPARTURE, depart, 30, kix, "Depart JL3025 from KIX"),
    ]
    legs1 = [
        Leg(from_stop_id="arrival", to_stop_id="check-in", mode=TravelMode.TRANSIT, minutes=75, distance_km=45, cost=Decimal("20.00"), source=LegSource.ESTIMATE),
        Leg(from_stop_id="check-in", to_stop_id="bamboo-grove", mode=TravelMode.TRANSIT, minutes=35, distance_km=10, source=LegSource.ESTIMATE),
        Leg(from_stop_id="bamboo-grove", to_stop_id="kissa-matcha", mode=TravelMode.WALK, minutes=12, distance_km=0.8, source=LegSource.ESTIMATE),
    ]
    legs2 = [
        Leg(from_stop_id="tenryuji", to_stop_id="gion-tea", mode=TravelMode.TRANSIT, minutes=40, distance_km=12, source=LegSource.ESTIMATE),
    ]
    legs3 = [
        Leg(from_stop_id="check-out", to_stop_id="departure", mode=TravelMode.TRANSIT, minutes=75, distance_km=45, cost=Decimal("20.00"), source=LegSource.ESTIMATE),
    ]
    selection = PlanSelection(must_visit=["bamboo-grove", "tenryuji"], maybe=["kissa-matcha", "gion-tea"], excluded=["lucky-souvenir"])
    return Itinerary(
        plan_id=PLAN_ID, brief=trip, selection=selection,
        days=[
            ItineraryDay(date="2026-11-14", stops=day1, legs=legs1),
            ItineraryDay(date="2026-11-15", stops=day2, legs=legs2),
            ItineraryDay(date="2026-11-16", stops=day3, legs=legs3),
        ],
        transport_summary="Haruka limited express between KIX and Kyoto. Walk or bike inside Arashiyama. City bus elsewhere.",
        estimated_total=Decimal("86.00"), bookable_total=Decimal("58.00"), warnings=[],
    )


def plan_events(cset: CandidateSet, plan: Itinerary) -> list[InspectorEvent]:
    t0 = datetime(2026, 11, 14, 8, 0, tzinfo=JST)

    def ev(i: int, type_: str, msg: str, **data) -> InspectorEvent:
        return InspectorEvent(
            id=f"plan-{i:03d}", ts=t0 + timedelta(seconds=2 * i), source=EventSource.AGENT,
            level=EventLevel.INFO, type=type_, message=msg, data=data,
        )

    return [
        ev(1, "plan.tool_call", "Transport profile for Kyoto", plan_id=PLAN_ID, tool="get_transport_profile", summary="Haruka from KIX, about 75 min"),
        ev(2, "plan.tool_call", "Searching temples and nature", plan_id=PLAN_ID, tool="search_attractions", summary="Curated Kyoto sights"),
        ev(3, "plan.tool_call", "Finding registered shops", plan_id=PLAN_ID, tool="find_merchants", summary="Kyoto merchants near the hotel"),
        ev(4, "plan.candidates", "Candidates ready", candidates=cset.model_dump(mode="json")),
        ev(5, "plan.tool_call", "KIX to Kyoto by Haruka (75 min)", plan_id=PLAN_ID, tool="get_transport_profile", summary="Arrival transfer"),
        ev(6, "plan.tool_call", "Computing walking times between stops", plan_id=PLAN_ID, tool="optimize_route", summary="Two-day order"),
        ev(7, "plan.ready", "Itinerary ready", itinerary=plan.model_dump(mode="json")),
    ]


def flights(trip: TripBrief) -> dict:
    return {"arrival": trip.arrival.model_dump(mode="json"), "departure": trip.departure.model_dump(mode="json")}
