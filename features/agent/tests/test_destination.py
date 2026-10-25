from datetime import date
from pathlib import Path

from babel.numbers import get_territory_currencies
from timezonefinder import TimezoneFinder

from roam_agent.conversation import extract_facts
from roam_agent.store import MemoryTripStore
from roam_agent.trips import Caller, attach_place, post_message, start_trip
from roam_contracts.models import TripFacts
from roam_tools import destination as resolver
from roam_tools.destination import clear_destination_cache, destination_from_bodies, lookup_destination

TODAY = date(2026, 10, 24)
MANHATTAN_LAT = 40.7580
MANHATTAN_LNG = -73.9855
NOMINATIM = [{
    "lat": "40.7580",
    "lon": "-73.9855",
    "name": "New York",
    "display_name": "New York, United States",
    "address": {
        "city": "New York",
        "country": "United States",
        "country_code": "us",
    },
}]
AIRPORTS = {
    "count": 3,
    "items": [
        {
            "iata": "EWR",
            "name": "Newark Liberty",
            "location": {"lat": 40.6895, "lon": -74.1745},
            "distance": {"km": 16.0},
        },
        {
            "iata": "JFK",
            "name": "John F. Kennedy",
            "location": {"lat": 40.6413, "lon": -73.7781},
            "distance": {"km": 20.0},
        },
        {
            "iata": "LGA",
            "name": "LaGuardia",
            "location": {"lat": 40.7769, "lon": -73.8740},
            "distance": {"km": 9.0},
        },
    ],
}


def test_new_york_record_comes_from_the_recorded_payloads():
    place = destination_from_bodies(NOMINATIM, AIRPORTS)
    lat = float(NOMINATIM[0]["lat"])
    lng = float(NOMINATIM[0]["lon"])
    assert lat == MANHATTAN_LAT
    assert lng == MANHATTAN_LNG
    assert place.city == "New York"
    assert place.country_code == "US"
    assert place.lat == lat
    assert place.lng == lng
    assert place.timezone == "America/New_York"
    assert place.timezone == TimezoneFinder().timezone_at(lat=lat, lng=lng)
    assert place.currency == "USD"
    assert place.currency == get_territory_currencies("US", tender=True)[0]
    assert "JFK" in place.airports
    assert place.airports[0] == "LGA"
    source = Path(resolver.__file__).read_text(encoding="utf-8")
    for banned in ("Kyoto", "Japan", "Asia/Tokyo", "JPY"):
        assert banned not in source


def test_new_york_aliases_resolve_to_the_same_record():
    clear_destination_cache()
    calls = {"geocode": 0, "airports": 0}

    def geocode(query: str):
        calls["geocode"] += 1
        assert query == "new york"
        return NOMINATIM

    def airports(lat: float, lng: float):
        calls["airports"] += 1
        assert (lat, lng) == (MANHATTAN_LAT, MANHATTAN_LNG)
        return AIRPORTS

    first = lookup_destination("New York", geocoder=geocode, airport_search=airports)
    second = lookup_destination("NYC", geocoder=geocode, airport_search=airports)
    third = lookup_destination("New York City", geocoder=geocode, airport_search=airports)
    assert first is second is third
    assert first.country_code == "US"
    assert first.timezone == "America/New_York"
    assert first.currency == "USD"
    assert first.lat == MANHATTAN_LAT
    assert first.lng == MANHATTAN_LNG
    assert "JFK" in first.airports
    assert calls == {"geocode": 1, "airports": 1}
    for words in ("New York", "New York City", "NYC"):
        assert extract_facts(f"{words} in late November, 4 days", TripFacts(), TODAY).destination == "New York"


def test_a_trip_stores_one_place_when_the_words_are_known(monkeypatch):
    clear_destination_cache()
    resolved = destination_from_bodies(NOMINATIM, AIRPORTS)
    seen: list[str] = []

    def resolve(words: str):
        seen.append(words)
        return resolved

    monkeypatch.setattr("roam_agent.trips.lookup_destination", resolve)
    store = MemoryTripStore()
    events = []

    def emit(kind, message, data, level="info"):
        events.append(kind)

    blank = start_trip(store, emit, Caller(), "hello", TODAY, None)
    assert blank.conversation.brief.destination is None
    assert blank.conversation.brief.place is None
    assert seen == []

    record = start_trip(store, emit, Caller(), "New York in late November, 4 days, 2 of us", TODAY, None)
    assert record.conversation.brief.destination == "New York"
    assert record.conversation.brief.place == resolved
    assert record.conversation.brief.place.lat == MANHATTAN_LAT
    assert record.conversation.brief.place.lng == MANHATTAN_LNG
    assert "JFK" in record.conversation.brief.place.airports
    assert seen == ["New York"]

    again = post_message(store, emit, record, Caller(), TODAY, text="NYC love food")
    assert again.conversation.brief.destination == "New York"
    assert again.conversation.brief.place == resolved
    assert seen == ["New York"]

    cleared = attach_place(
        again.conversation.brief,
        again.conversation.brief.model_copy(update={"destination": None}),
    )
    assert cleared.destination is None
    assert cleared.place is None
