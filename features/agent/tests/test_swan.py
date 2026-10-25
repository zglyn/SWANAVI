import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from roam_agent.auth import MemoryAuth
from roam_agent.autopilot import advance, apply_choices, begin, pick_attractions
from roam_agent.profile_crypto import planning_profile
from roam_agent.profile_store import MemoryProfileStore, SqliteProfileStore
from roam_agent.swan_http import reset
from roam_contracts.models import (
    AttractionPick,
    AttractionSelection,
    Autonomy,
    CandidateSet,
    CategoryAmount,
    Destination,
    PackageChoices,
    Priority,
    StopKind,
    SwanPhase,
    TravelPackage,
    TripRequest,
    UserProfile,
)
from roam_tools.flight_search import clear_flight_cache, flight_load_count, search_flights
from roam_tools.hotel_search import search_hotels

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
KEY = b"swan-test-key"


def _profile() -> UserProfile:
    return UserProfile.model_validate(json.loads((FIXTURES / "profile.json").read_text()))


def _request() -> TripRequest:
    request = TripRequest.model_validate(json.loads((FIXTURES / "trip_request_kyoto.json").read_text()))
    return request.model_copy(update={"place": Destination(
        city="Kyoto",
        country_code="JP",
        lat=35.0116,
        lng=135.7681,
        timezone="Asia/Tokyo",
        currency="JPY",
        airports=["KIX", "ITM"],
    )})


def _pool() -> CandidateSet:
    return CandidateSet.model_validate(json.loads((FIXTURES / "candidates_kyoto.json").read_text()))


def test_profile_fixture_roundtrip_and_sealed_secrets(tmp_path):
    person = _profile()
    assert person.home.airport_codes[0] == "SFO"
    assert person.flights.favourite_airlines == ["JL"]
    store = SqliteProfileStore(str(tmp_path / "profiles.sqlite"), key=KEY)
    store.put(person)
    stored = store.stored_text(person.user_id)
    assert "JL998877" not in stored
    assert "HH123456" not in stored
    assert "1 Market Street" not in stored
    loaded = store.get(person.user_id)
    assert loaded.flights.loyalty[0].number == "JL998877"
    assert loaded.home.address.startswith("1 Market")
    view = planning_profile(loaded).model_dump(mode="json")
    assert "JL998877" not in json.dumps(view)
    assert "address" not in view["home"]
    assert view["flights"]["loyalty"][0]["member"] is True


def test_sqlite_refuses_to_start_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ROAM_PROFILE_KEY", raising=False)
    with pytest.raises(RuntimeError):
        SqliteProfileStore(str(tmp_path / "profiles.sqlite"))


def test_flight_search_ranks_jal_and_caches():
    clear_flight_cache()
    offers = search_flights(
        ["SFO"], ["KIX"], "2026-11-13", "2026-11-16",
        "morning", "evening", favourite_airlines=["JL"], avoid_red_eye=True,
    )
    outbound = [item for item in offers if item.direction == "outbound"]
    assert outbound[0].carrier == "JL"
    assert outbound[0].why
    assert any("favourite" in line for line in outbound[0].why)
    loads = flight_load_count()
    again = search_flights(
        ["SFO"], ["KIX"], "2026-11-13", "2026-11-16",
        "morning", "evening", favourite_airlines=["JL"], avoid_red_eye=True,
    )
    assert [item.id for item in again] == [item.id for item in offers]
    assert flight_load_count() == loads


def test_hotel_near_picks_and_brand_and_split():
    near = [
        {"id": "bamboo", "lat": 35.017, "lng": 135.671, "weight": 2},
        {"id": "boat", "lat": 35.015, "lng": 135.676, "weight": 1},
    ]
    ranked = search_hotels(near, "2026-11-14", "2026-11-16", brands=["Hyatt"], member_programs=["World of Hyatt"])
    assert ranked[0].id == "hyatt-arashiyama"
    assert ranked[0].avg_travel_min_to_attractions <= 15
    assert ranked[0].score > next(item.score for item in ranked if item.id == "inn-arashiyama")
    merchant = next(item for item in ranked if item.id == "gion-house")
    assert merchant.source.value == "merchant_mcp"
    assert merchant.quote is not None
    split_points = [
        {"id": "west", "lat": 35.017, "lng": 135.671, "day": "2026-11-14", "weight": 1},
        {"id": "east", "lat": 34.6937, "lng": 135.5023, "day": "2026-11-15", "weight": 1},
    ]
    stayed = search_hotels(split_points, "2026-11-14", "2026-11-16", brands=["Hyatt"])
    splits = [item for item in stayed if any("Split stay" in line for line in item.why)]
    assert len(splits) == 2


def test_amounts_prefer_food_over_museums():
    selection = AttractionSelection(
        mode=Autonomy.I_CHOOSE,
        amounts=[
            CategoryAmount(category="food", level="lots"),
            CategoryAmount(category="museums", level="a_little"),
        ],
        daily_density="packed",
    )
    chosen = pick_attractions(_profile(), selection, _pool(), nights=2)
    pool = {item.id: item for item in _pool().candidates}
    def category(item: str) -> str:
        row = pool[item]
        if row.attraction:
            return row.attraction.category.lower()
        if row.merchant:
            return row.merchant.category.value.lower()
        return ""

    food = sum(1 for item in chosen if category(item) == "food")
    museums = sum(1 for item in chosen if "museum" in category(item))
    assert food > museums


def test_autopilot_respects_wake_and_pauses_for_hotels():
    person = _profile()
    trip = begin("demo", _request(), person)
    assert trip.phase == SwanPhase.READY
    assert trip.package is not None
    assert trip.package.outbound is not None
    assert trip.package.outbound.carrier == "JL"
    first_activities = [
        stop for stop in trip.package.itinerary.days[0].stops
        if stop.kind in {StopKind.ATTRACTION, StopKind.MERCHANT}
    ]
    assert len(first_activities) <= 1
    for day in trip.package.itinerary.days:
        for stop in day.stops:
            if stop.kind not in {StopKind.ATTRACTION, StopKind.MERCHANT}:
                continue
            local = stop.start.hour * 60 + stop.start.minute
            end = stop.end.hour * 60 + stop.end.minute
            assert local >= 8 * 60 + 15
            assert end <= 22 * 60
    paused = _request()
    paused.autonomy.hotels = Autonomy.I_CHOOSE
    waiting = begin("demo", paused, person)
    assert waiting.phase == SwanPhase.HOTELS
    assert waiting.package is None
    chosen = waiting.hotels[0].id
    apply_choices(waiting, PackageChoices(hotel_ids=[chosen]))
    assert waiting.phase == SwanPhase.READY
    assert waiting.package.hotels[0].offer.id == chosen


def test_dates_with_no_flights_still_get_a_hotel_and_days_in_kyoto_time():
    request = _request().model_copy(update={"start_date": "2026-11-21", "end_date": "2026-11-24"})
    trip = begin("demo", request, _profile())
    package = trip.package
    assert package is not None
    assert package.outbound is None and package.return_flight is None
    assert package.hotels
    assert [day.date for day in package.itinerary.days] == ["2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24"]
    assert package.itinerary.brief.start_date.utcoffset() == timedelta(hours=9)


def test_changing_outbound_shifts_only_day_one():
    trip = begin("demo", _request(), _profile())
    package = trip.package
    assert package is not None and len(package.itinerary.days) > 1
    before = package.itinerary.days[0].stops[0].start
    later_days = [stop.start for day in package.itinerary.days[1:] for stop in day.stops]
    apply_choices(trip, PackageChoices(outbound_id="out-aa"))
    assert trip.package.outbound.id == "out-aa"
    assert trip.package.itinerary.days[0].stops[0].start > before
    assert [stop.start for day in trip.package.itinerary.days[1:] for stop in day.stops] == later_days


def test_planning_log_omits_loyalty_numbers(caplog):
    caplog.set_level(logging.INFO, logger="swan.autopilot")
    begin("demo", _request(), _profile())
    assert "JL998877" not in caplog.text
    assert "HH123456" not in caplog.text
    assert "1 Market Street" not in caplog.text


def test_accounts_are_isolated_and_delete_removes_data():
    reset()
    from roam_agent.app import app
    from roam_agent import swan_http

    swan_http.profiles = MemoryProfileStore(key=KEY)
    swan_http.auth = MemoryAuth()
    client = TestClient(app)
    first = client.post("/api/auth/magic-link", json={"email": "a@example.com"}).json()
    second = client.post("/api/auth/magic-link", json={"email": "b@example.com"}).json()
    person = _profile()
    person.user_id = "ignored"
    saved = client.put(
        "/api/me/profile",
        json=person.model_dump(mode="json"),
        headers={"Authorization": f"Bearer {first['token']}"},
    )
    assert saved.status_code == 200
    other = client.get("/api/me/profile", headers={"Authorization": f"Bearer {second['token']}"})
    assert other.status_code == 404
    mine = client.get("/api/me/profile", headers={"Authorization": f"Bearer {first['token']}"})
    assert mine.json()["flights"]["loyalty"][0]["number"] == "JL998877"
    created = client.post(
        "/api/trips/request",
        json=_request().model_dump(mode="json"),
        headers={"Authorization": f"Bearer {first['token']}"},
    )
    assert created.status_code == 200
    plan_id = created.json()["plan_id"]
    hidden = client.get(f"/api/plans/{plan_id}/package", headers={"Authorization": f"Bearer {second['token']}"})
    assert hidden.status_code == 404
    deleted = client.delete("/api/me", headers={"Authorization": f"Bearer {first['token']}"})
    assert deleted.status_code == 200
    gone = client.get("/api/me/profile", headers={"Authorization": f"Bearer {first['token']}"})
    assert gone.status_code == 401
    assert swan_http.profiles.get(first["user_id"]) is None
    assert plan_id not in swan_http.trips


def test_package_fixture_has_return_flight():
    payload = json.loads((FIXTURES / "package_kyoto.json").read_text())
    assert payload["return"]["carrier"] == "JL"
    assert payload["hotels"][0]["offer"]["brand"] == "Hyatt"


def _coherent(package):
    hotel = package.hotels[0].offer
    first = package.itinerary.days[0]
    titles = [stop.title for stop in first.stops]
    assert f"Check in at {hotel.name}" in titles or f"Drop bags at {hotel.name}" in titles
    assert first.stops[0].kind == StopKind.ARRIVAL
    assert first.stops[1].kind == StopKind.LODGING
    for day in package.itinerary.days:
        for left, right in zip(day.stops, day.stops[1:]):
            assert right.start >= left.end
        assert [(leg.from_stop_id, leg.to_stop_id) for leg in day.legs] == [
            (left.id, right.id) for left, right in zip(day.stops, day.stops[1:])
        ]
        for leg, left, right in zip(day.legs, day.stops, day.stops[1:]):
            assert leg.minutes <= (right.start - left.end).total_seconds() / 60
            assert leg.minutes < 240


def test_itinerary_matches_the_chosen_hotel_and_explains_every_gap():
    trip = begin("demo", _request(), _profile())
    _coherent(trip.package)
    first_leg = trip.package.itinerary.days[0].legs[0]
    assert first_leg.mode.value == "transit"
    assert first_leg.minutes >= 60
    assert all(hotel.avg_travel_min_to_attractions > 0 for hotel in trip.hotels)
    apply_choices(trip, PackageChoices(outbound_id="out-red"))
    _coherent(trip.package)
    assert trip.package.itinerary.days[0].stops[1].title.startswith("Drop bags")


def test_fixture_package_is_coherent():
    payload = json.loads((FIXTURES / "package_kyoto.json").read_text())
    _coherent(TravelPackage.model_validate(payload))
