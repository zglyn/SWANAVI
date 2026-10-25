from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from roam_contracts.models import (
    Autonomy,
    AutonomyDefaults,
    BudgetLevel,
    Cabin,
    Category,
    FareConditions,
    FlightOffer,
    FlightPreferences,
    GeoPoint,
    HomeBase,
    HotelOffer,
    HotelPreferences,
    HotelSource,
    LoyaltyProgram,
    PlaceRef,
    Quote,
    SeatPref,
    SegmentMode,
    SleepSchedule,
    TimeOfDayWindow,
    TravelPackage,
    TravelPreferences,
    TravelSegment,
    TripOrigin,
    TripRequest,
    UserProfile,
)

PST = timezone(timedelta(hours=-8))
JST = timezone(timedelta(hours=9))
OUT_DEFAULT = Path(__file__).parent


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def profile() -> UserProfile:
    return UserProfile(
        user_id="demo",
        name="Maya Chen",
        home=HomeBase(
            address="1 Market Street, San Francisco, CA",
            location=GeoPoint(lat=37.7936, lng=-122.3946),
            airport_codes=["SFO", "OAK", "SJC"],
        ),
        currency="USD",
        travel=TravelPreferences(
            interests=["temples", "food"],
            pace="balanced",
            budget_level=BudgetLevel.MID,
            preferred_modes=["walk", "transit"],
            dietary=[],
            accessibility=[],
            avoid=["crowds"],
        ),
        sleep=SleepSchedule(wake_time="07:30", sleep_time="23:00", jet_lag_buffer=True),
        hotels=HotelPreferences(
            favourite_brands=["Hyatt"],
            min_stars=3,
            must_have=["wifi", "breakfast"],
            loyalty=[LoyaltyProgram(program="World of Hyatt", number="HH123456")],
        ),
        flights=FlightPreferences(
            favourite_airlines=["JL"],
            alliances=["oneworld"],
            cabin=Cabin.ECONOMY,
            max_stops=1,
            seat=SeatPref.WINDOW,
            loyalty=[LoyaltyProgram(program="JAL Mileage Bank", number="JL998877")],
            avoid_red_eye=True,
        ),
        autonomy=AutonomyDefaults(
            attractions=Autonomy.SWAN_DECIDES,
            hotels=Autonomy.SWAN_DECIDES,
            flights=Autonomy.SWAN_DECIDES,
        ),
    )


def trip_request() -> TripRequest:
    return TripRequest(
        destination="Kyoto, Japan",
        origin=TripOrigin(from_home=True),
        start_date="2026-11-14",
        end_date="2026-11-16",
        outbound_window=TimeOfDayWindow.MORNING,
        return_window=TimeOfDayWindow.EVENING,
        travellers=1,
        budget=Decimal("2500"),
        autonomy=AutonomyDefaults(),
        notes=None,
    )


def _segment(carrier: str, number: str, origin: str, dest: str, depart: datetime, arrive: datetime, olat, olng, dlat, dlng) -> TravelSegment:
    names = {"SFO": "San Francisco", "KIX": "Kansai", "HND": "Haneda", "NRT": "Narita"}
    return TravelSegment(
        mode=SegmentMode.FLIGHT,
        carrier=carrier,
        number=number,
        from_place=PlaceRef(code=origin, name=names.get(origin, origin), location=GeoPoint(lat=olat, lng=olng)),
        to_place=PlaceRef(code=dest, name=names.get(dest, dest), location=GeoPoint(lat=dlat, lng=dlng)),
        depart_at=depart,
        arrive_at=arrive,
        status="scheduled",
        source="fixture",
    )


AIRLINE_SITES = {"JL": "https://www.jal.co.jp", "UA": "https://www.united.com", "AA": "https://www.aa.com"}


def flight_offers() -> list[FlightOffer]:
    sfo = (37.6213, -122.379)
    kix = (34.4347, 135.244)
    out_jl = _segment("JL", "JL001", "SFO", "KIX", datetime(2026, 11, 13, 9, 5, tzinfo=PST), datetime(2026, 11, 14, 13, 10, tzinfo=JST), *sfo, *kix)
    out_ua = _segment("UA", "UA875", "SFO", "KIX", datetime(2026, 11, 13, 9, 30, tzinfo=PST), datetime(2026, 11, 14, 14, 5, tzinfo=JST), *sfo, *kix)
    out_red = _segment("UA", "UA35", "SFO", "KIX", datetime(2026, 11, 13, 0, 40, tzinfo=PST), datetime(2026, 11, 14, 5, 10, tzinfo=JST), *sfo, *kix)
    out_stop = _segment("AA", "AA173", "SFO", "KIX", datetime(2026, 11, 13, 15, 10, tzinfo=PST), datetime(2026, 11, 14, 20, 40, tzinfo=JST), *sfo, *kix)
    back_jl = _segment("JL", "JL002", "KIX", "SFO", datetime(2026, 11, 16, 18, 20, tzinfo=JST), datetime(2026, 11, 16, 11, 40, tzinfo=PST), *kix, *sfo)
    back_late = _segment("UA", "UA876", "KIX", "SFO", datetime(2026, 11, 16, 10, 15, tzinfo=JST), datetime(2026, 11, 16, 4, 5, tzinfo=PST), *kix, *sfo)

    def offer(key: str, segments: list[TravelSegment], carrier: str, stops: int, duration: int, price: str, direction: Literal["outbound", "return"], refundable: bool) -> FlightOffer:
        return FlightOffer(
            id=key,
            segments=segments,
            carrier=carrier,
            cabin=Cabin.ECONOMY,
            stops=stops,
            duration_min=duration,
            price=Decimal(price),
            currency="USD",
            fare_conditions=FareConditions(refundable=refundable, changeable=True),
            score=0,
            why=[],
            deep_link=f"{AIRLINE_SITES[carrier]}/book/{key}",
            direction=direction,
        )

    return [
        offer("out-jl", [out_jl], "JL", 0, 665, "680.00", "outbound", True),
        offer("out-ua", [out_ua], "UA", 0, 695, "640.00", "outbound", True),
        offer("out-red", [out_red], "UA", 0, 690, "590.00", "outbound", False),
        offer("out-aa", [out_stop], "AA", 1, 890, "610.00", "outbound", True),
        offer("ret-jl", [back_jl], "JL", 0, 620, "690.00", "return", True),
        offer("ret-ua", [back_late], "UA", 0, 650, "640.00", "return", False),
    ]


def _quote(merchant_id: str, sku: str, title: str, amount: str, viator: str, loc: GeoPoint) -> Quote:
    start = datetime(2026, 11, 14, 15, 0, tzinfo=JST)
    return Quote(
        invoice_id=hashlib.sha256(sku.encode()).hexdigest().upper(),
        merchant_id=merchant_id,
        merchant_name=title,
        merchant_address=f"r{merchant_id}PLACEHOLDER",
        sku=sku,
        title=title,
        category=Category.LODGING,
        amount=Decimal(amount),
        currency="RLUSD",
        viator_price=Decimal(viator),
        slot_start=start,
        slot_end=start + timedelta(days=2),
        location=loc,
        cancel_after=start - timedelta(hours=24),
        expires_at=datetime(2026, 11, 20, tzinfo=JST),
        merchant_signature="00" * 64,
        merchant_verified=True,
    )


def hotel_catalog() -> list[HotelOffer]:
    near = GeoPoint(lat=35.0162, lng=135.6784)
    same = GeoPoint(lat=35.0162, lng=135.6784)
    gion = GeoPoint(lat=35.0037, lng=135.7758)
    osaka = GeoPoint(lat=34.6937, lng=135.5023)
    return [
        HotelOffer(
            id="inn-arashiyama",
            name="Arashiyama Riverside Inn",
            brand=None,
            stars=4,
            location=same,
            area="Arashiyama",
            price_per_night=Decimal("180"),
            total=Decimal("360"),
            amenities=["wifi", "breakfast"],
            refundable=True,
            source=HotelSource.PROVIDER,
            deep_link="https://www.booking.com/hotel/jp/arashiyama-riverside-inn",
        ),
        HotelOffer(
            id="hyatt-arashiyama",
            name="Hyatt Place Arashiyama",
            brand="Hyatt",
            stars=4,
            location=near,
            area="Arashiyama",
            price_per_night=Decimal("180"),
            total=Decimal("360"),
            amenities=["wifi", "breakfast", "gym"],
            refundable=True,
            source=HotelSource.PROVIDER,
            deep_link="https://www.hyatt.com/hyatt-place/kyoto-arashiyama",
        ),
        HotelOffer(
            id="gion-house",
            name="Gion House",
            brand=None,
            stars=3,
            location=gion,
            area="Gion",
            price_per_night=Decimal("90"),
            total=Decimal("180"),
            currency="RLUSD",
            amenities=["wifi"],
            refundable=True,
            source=HotelSource.MERCHANT,
            quote=_quote("gion-house", "GION-ROOM", "Gion House, two nights", "180.00", "220.00", gion),
        ),
        HotelOffer(
            id="osaka-hyatt",
            name="Hyatt Regency Osaka",
            brand="Hyatt",
            stars=4,
            location=osaka,
            area="Osaka",
            price_per_night=Decimal("160"),
            total=Decimal("160"),
            amenities=["wifi", "breakfast", "pool"],
            refundable=True,
            source=HotelSource.PROVIDER,
            deep_link="https://www.hyatt.com/hyatt-regency/osaka",
        ),
    ]


def write_swan(folder: Path, plan_id: str) -> TravelPackage:
    def dump(name: str, obj) -> None:
        if isinstance(obj, list):
            data = [item.model_dump(mode="json", by_alias=True) for item in obj]
        else:
            data = obj.model_dump(mode="json", by_alias=True)
        (folder / name).write_text(json.dumps(data, indent=2) + "\n")

    people = profile()
    request = trip_request()
    dump("profile.json", people)
    dump("trip_request_kyoto.json", request)
    dump("flight_offers.json", flight_offers())
    dump("hotel_offers.json", hotel_catalog())

    # The search tools read the two catalogs just written, so the package below
    # is what the planner really produces for this profile, not a hand-made copy.
    os.environ.pop("ROAM_SCRIPTED_AGENT", None)
    from roam_agent.autopilot import begin

    trip = begin(people.user_id, request, people, plan_id=plan_id)
    if trip.package is None:
        raise RuntimeError("autopilot did not reach a package")
    dump("flight_offers.json", trip.flights)
    dump("hotel_offers.json", trip.hotels)
    dump("package_kyoto.json", trip.package)
    return trip.package
