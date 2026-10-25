from decimal import Decimal
from unittest.mock import patch

from roam_contracts.models import FareConditions, FlightOffer, PlaceRef, SegmentMode, TravelSegment
from roam_tools.aviationstack import fetch_schedule_offers
from roam_tools.flight_search import clear_flight_cache, search_flights
from roam_tools.hotel_search import search_hotels
from roam_tools.osm_lodging import fetch_hotels_near
from datetime import datetime, timezone


def test_aviationstack_maps_a_schedule_row(monkeypatch):
    monkeypatch.setenv("AVIATIONSTACK_ACCESS_KEY", "test-key")
    sample = {
        "data": [
            {
                "airline": {"iata": "JL"},
                "flight": {"iata": "JL001"},
                "departure": {"iata": "SFO", "scheduled": "2026-11-13T09:05:00-08:00", "airport": "San Francisco"},
                "arrival": {"iata": "KIX", "scheduled": "2026-11-14T13:10:00+09:00", "airport": "Kansai"},
            }
        ]
    }

    def fake_get(path, params):
        # Patched _get receives caller params only; access_key is added inside real _get.
        assert "dep_iata" in params or path == "/flightsFuture"
        if path == "/flightsFuture":
            return {"data": []}
        assert params.get("dep_iata") == "SFO"
        assert params.get("arr_iata") == "KIX"
        return sample

    with patch("roam_tools.aviationstack._get", side_effect=fake_get):
        offers = fetch_schedule_offers(["SFO"], ["KIX"], "2026-11-13", None)
    assert len(offers) == 1
    assert offers[0].price == Decimal("0")
    assert offers[0].carrier == "JL"
    assert "schedule only" in " ".join(offers[0].why)


def test_search_flights_uses_aviationstack(monkeypatch):
    monkeypatch.setenv("AVIATIONSTACK_ACCESS_KEY", "test-key")
    monkeypatch.setenv("FLIGHT_SEARCH_PROVIDER", "aviationstack")
    clear_flight_cache()
    segment = TravelSegment(
        mode=SegmentMode.FLIGHT,
        carrier="JL",
        number="JL001",
        from_place=PlaceRef(code="SFO", name="SFO"),
        to_place=PlaceRef(code="KIX", name="KIX"),
        depart_at=datetime(2026, 11, 13, 9, 5, tzinfo=timezone.utc),
        arrive_at=datetime(2026, 11, 14, 13, 10, tzinfo=timezone.utc),
        source="aviationstack",
    )
    offer = FlightOffer(
        id="avs-out",
        segments=[segment],
        carrier="JL",
        stops=0,
        duration_min=665,
        price=Decimal("0"),
        why=["schedule only, fare not quoted"],
        fare_conditions=FareConditions(),
        direction="outbound",
    )
    with patch("roam_tools.aviationstack.fetch_schedule_offers", return_value=[offer]) as mocked:
        ranked = search_flights(["SFO"], ["KIX"], "2026-11-13", None, "morning", "any")
    assert ranked[0].id == "avs-out"
    mocked.assert_called()


def test_osm_hotels_map_overpass():
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": 35.01,
                "lon": 135.77,
                "tags": {"name": "Test Inn", "tourism": "hotel", "stars": "3", "wifi": "yes"},
            }
        ]
    }

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    with patch("roam_tools.osm_lodging.httpx.post", return_value=Resp()):
        hotels = fetch_hotels_near(35.01, 135.77, check_in="2026-11-14", check_out="2026-11-16", budget_level="mid")
    assert hotels[0].name == "Test Inn"
    assert hotels[0].total == Decimal("320")
    assert "rate not confirmed" in hotels[0].why


def test_search_hotels_osm_provider(monkeypatch):
    monkeypatch.setenv("HOTEL_SEARCH_PROVIDER", "osm")
    with patch("roam_tools.osm_lodging.fetch_hotels_near", return_value=[]) as mocked:
        points = [{"id": "a", "lat": 35.0, "lng": 135.0, "day": "2026-11-14", "weight": 1}]
        assert search_hotels(points, "2026-11-14", "2026-11-16") == []
        mocked.assert_called()
