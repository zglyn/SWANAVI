from __future__ import annotations

import hashlib
import hmac
import os

from pydantic import BaseModel

from roam_contracts.models import (
    AutonomyDefaults,
    Cabin,
    FlightPreferences,
    GeoPoint,
    HotelPreferences,
    LoyaltyProgram,
    SeatPref,
    SleepSchedule,
    TravelPreferences,
    UserProfile,
)

_PROCESS_KEY: bytes | None = None


def profile_key() -> bytes:
    global _PROCESS_KEY
    raw = os.environ.get("ROAM_PROFILE_KEY")
    if raw:
        return hashlib.sha256(raw.encode()).digest()
    if _PROCESS_KEY is None:
        _PROCESS_KEY = os.urandom(32)
    return _PROCESS_KEY


def _parts(secret: bytes) -> tuple[bytes, bytes]:
    return hmac.new(secret, b"enc", hashlib.sha256).digest(), hmac.new(secret, b"mac", hashlib.sha256).digest()


def seal(plain: str, key: bytes | None = None) -> str:
    secret = key or profile_key()
    enc_key, mac_key = _parts(secret)
    nonce = os.urandom(16)
    data = plain.encode()
    stream = _stream(enc_key, nonce, len(data))
    cipher = bytes(left ^ right for left, right in zip(data, stream))
    mac = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    return "enc:" + (nonce + mac + cipher).hex()


def open_secret(token: str, key: bytes | None = None) -> str:
    if not token.startswith("enc:"):
        return token
    secret = key or profile_key()
    enc_key, mac_key = _parts(secret)
    blob = bytes.fromhex(token[4:])
    nonce, mac, cipher = blob[:16], blob[16:48], blob[48:]
    expected = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("profile field failed its integrity check")
    stream = _stream(enc_key, nonce, len(cipher))
    return bytes(left ^ right for left, right in zip(cipher, stream)).decode()


def _stream(key: bytes, nonce: bytes, size: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:size])


def seal_profile(profile: UserProfile, key: bytes | None = None) -> dict:
    raw = profile.model_dump(mode="json")
    raw["home"]["address"] = seal(raw["home"]["address"], key)
    for group in (raw["hotels"]["loyalty"], raw["flights"]["loyalty"]):
        for item in group:
            if item.get("number"):
                item["number"] = seal(item["number"], key)
    return raw


def open_profile(raw: dict, key: bytes | None = None) -> UserProfile:
    data = json_copy(raw)
    data["home"]["address"] = open_secret(data["home"]["address"], key)
    for group in (data["hotels"]["loyalty"], data["flights"]["loyalty"]):
        for item in group:
            if item.get("number"):
                item["number"] = open_secret(item["number"], key)
    return UserProfile.model_validate(data)


class PlannerHome(BaseModel):
    airport_codes: list[str]
    location: GeoPoint


class PlannerLoyalty(BaseModel):
    program: str
    member: bool


class PlannerHotels(BaseModel):
    favourite_brands: list[str]
    min_stars: float | None
    must_have: list[str]
    room_type: str | None
    loyalty: list[PlannerLoyalty]


class PlannerFlights(BaseModel):
    favourite_airlines: list[str]
    alliances: list[str]
    cabin: Cabin
    max_stops: int
    seat: SeatPref
    loyalty: list[PlannerLoyalty]
    avoid_red_eye: bool


class PlannerProfile(BaseModel):
    user_id: str
    name: str
    home: PlannerHome
    currency: str
    travel: TravelPreferences
    sleep: SleepSchedule
    hotels: PlannerHotels
    flights: PlannerFlights
    autonomy: AutonomyDefaults


def _loyalty(items: list[LoyaltyProgram]) -> list[PlannerLoyalty]:
    return [PlannerLoyalty(program=item.program, member=bool(item.number)) for item in items]


def planning_profile(profile: UserProfile) -> PlannerProfile:
    hotels: HotelPreferences = profile.hotels
    flights: FlightPreferences = profile.flights
    return PlannerProfile(
        user_id=profile.user_id,
        name=profile.name,
        home=PlannerHome(airport_codes=list(profile.home.airport_codes), location=profile.home.location),
        currency=profile.currency,
        travel=profile.travel,
        sleep=profile.sleep,
        hotels=PlannerHotels(
            favourite_brands=list(hotels.favourite_brands),
            min_stars=hotels.min_stars,
            must_have=list(hotels.must_have),
            room_type=hotels.room_type,
            loyalty=_loyalty(hotels.loyalty),
        ),
        flights=PlannerFlights(
            favourite_airlines=list(flights.favourite_airlines),
            alliances=list(flights.alliances),
            cabin=flights.cabin,
            max_stops=flights.max_stops,
            seat=flights.seat,
            loyalty=_loyalty(flights.loyalty),
            avoid_red_eye=flights.avoid_red_eye,
        ),
        autonomy=profile.autonomy,
    )


def json_copy(raw: dict) -> dict:
    import json
    return json.loads(json.dumps(raw))
