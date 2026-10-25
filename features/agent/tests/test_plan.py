import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from roam_contracts.models import (
    GeoPoint,
    Itinerary,
    Leg,
    LegSource,
    Pace,
    PlaceRef,
    PlanRevision,
    PlanSelection,
    RevisionAction,
    SegmentMode,
    SegmentStatus,
    Stop,
    StopKind,
    StopRevision,
    TravelMode,
    TravelSegment,
    TripBrief,
    Lodging,
)
from roam_agent.plan import collect_candidates, plan, revise
from roam_agent.validate import validate_itinerary

JST = timezone(timedelta(hours=9))


def _brief() -> TripBrief:
    return TripBrief(
        destination="Kyoto, Japan",
        timezone="Asia/Tokyo",
        arrival=TravelSegment(
            mode=SegmentMode.FLIGHT, number="JL3020", carrier="JL",
            from_place=PlaceRef(code="HND", name="Haneda"),
            to_place=PlaceRef(code="KIX", name="Kansai", location=GeoPoint(lat=34.4347, lng=135.244)),
            depart_at=datetime(2026, 11, 14, 9, 20, tzinfo=JST),
            arrive_at=datetime(2026, 11, 14, 10, 35, tzinfo=JST),
            source="fixture",
        ),
        departure=TravelSegment(
            mode=SegmentMode.FLIGHT, number="JL3025", carrier="JL",
            from_place=PlaceRef(code="KIX", name="Kansai", location=GeoPoint(lat=34.4347, lng=135.244)),
            to_place=PlaceRef(code="HND", name="Haneda"),
            depart_at=datetime(2026, 11, 16, 18, 20, tzinfo=JST),
            arrive_at=datetime(2026, 11, 16, 19, 35, tzinfo=JST),
            source="fixture",
        ),
        lodging=[Lodging(name="Hotel Granvia Kyoto", location=GeoPoint(lat=34.9858, lng=135.7588), check_in=datetime(2026, 11, 14, 15, tzinfo=JST), check_out=datetime(2026, 11, 16, 11, tzinfo=JST))],
        start_date=datetime(2026, 11, 14, tzinfo=JST),
        end_date=datetime(2026, 11, 16, tzinfo=JST),
        budget=Decimal("200"),
        interests=["temples", "nature"],
        pace=Pace.BALANCED,
        preferred_modes=[TravelMode.WALK, TravelMode.TRANSIT],
    )


def test_scripted_flow_keeps_must_visits(monkeypatch):
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    brief = _brief()
    candidates = collect_candidates(brief, plan_id="kyoto-demo")
    selection = PlanSelection(must_visit=["bamboo-grove", "tenryuji"], maybe=["kissa-matcha"], excluded=["lucky-souvenir"])
    itinerary = plan(brief, selection, candidates, plan_id="kyoto-demo")
    ids = {stop.id for day in itinerary.days for stop in day.stops}
    assert "bamboo-grove" in ids and "tenryuji" in ids
    assert validate_itinerary(itinerary) == []
    first_activity = next(stop for day in itinerary.days for stop in day.stops if stop.kind == StopKind.ATTRACTION)
    assert first_activity.start >= brief.arrival.arrive_at + timedelta(minutes=75)


def test_invalid_itinerary_is_rejected(monkeypatch):
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    brief = _brief()
    candidates = collect_candidates(brief)
    good = plan(brief, PlanSelection(must_visit=["bamboo-grove", "tenryuji"]), candidates)
    dropped = good.model_copy(update={
        "days": [day.model_copy(update={"stops": [stop for stop in day.stops if stop.id != "bamboo-grove"]}) for day in good.days],
        "warnings": [],
    })
    errors = validate_itinerary(dropped)
    assert any("bamboo-grove" in error for error in errors)
    during_flight = good.model_copy(deep=True)
    during_flight.days[0].stops[2].start = brief.arrival.depart_at
    during_flight.days[0].stops[2].end = brief.arrival.depart_at + timedelta(minutes=20)
    assert validate_itinerary(during_flight)
    made_up = good.model_copy(deep=True)
    made_up.days[0].legs.append(Leg(
        from_stop_id="bamboo-grove", to_stop_id="kissa-matcha", mode=TravelMode.WALK,
        minutes=1, distance_km=40, source=LegSource.ORS,
    ))
    assert any("claims" in error for error in validate_itinerary(made_up))


def test_revise_keeps_required_stops(monkeypatch):
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    brief = _brief()
    candidates = collect_candidates(brief)
    good = plan(brief, PlanSelection(must_visit=["bamboo-grove", "tenryuji"], maybe=["kissa-matcha"]), candidates)
    updated = revise(good, PlanRevision(actions=[StopRevision(stop_id="kissa-matcha", action=RevisionAction.REMOVE), StopRevision(stop_id="bamboo-grove", action=RevisionAction.REMOVE)], feedback="more food"))
    ids = {stop.id for day in updated.days for stop in day.stops}
    assert "kissa-matcha" not in ids
    assert "bamboo-grove" in ids and "tenryuji" in ids
    assert "more food" in updated.warnings
    swapped = revise(updated, PlanRevision(actions=[StopRevision(stop_id="kissa-matcha", action=RevisionAction.SWAP)]))
    assert any("Asked to swap" in warning for warning in swapped.warnings)


def test_unverified_flight_adds_a_warning(monkeypatch):
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    brief = _brief()
    brief.arrival.status = SegmentStatus.UNVERIFIED
    itinerary = plan(brief, PlanSelection(must_visit=["bamboo-grove"], maybe=[], excluded=[]), collect_candidates(brief))
    assert any(warning.startswith("Unverified flight times") for warning in itinerary.warnings)


def test_delayed_arrival_uses_the_revised_time(monkeypatch):
    monkeypatch.delenv("ROAM_SCRIPTED_AGENT", raising=False)
    brief = _brief()
    brief.arrival.status = SegmentStatus.DELAYED
    brief.arrival.arrive_at = datetime(2026, 11, 14, 13, 35, tzinfo=JST)
    itinerary = plan(brief, PlanSelection(must_visit=[], maybe=[], excluded=[]), collect_candidates(brief))
    arrival = next(stop for day in itinerary.days for stop in day.stops if stop.kind == StopKind.ARRIVAL)
    assert arrival.start == brief.arrival.arrive_at
    assert any("delayed" in warning for warning in itinerary.warnings)


def test_plan_module_does_not_import_fastapi():
    import roam_agent.plan as plan_module
    assert "fastapi" not in (plan_module.__file__ and open(plan_module.__file__, encoding="utf-8").read())


def test_gateway_scripted_round_trip(monkeypatch):
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    from fastapi.testclient import TestClient
    from roam_agent.app import app

    client = TestClient(app)
    created = client.post("/api/plans", json=_brief().model_dump(mode="json"))
    assert created.status_code == 200
    plan_id = created.json()["plan_id"]
    ready_candidates = client.get(f"/api/plans/{plan_id}")
    assert ready_candidates.json()["status"] == "candidates_ready"
    chosen = client.post(
        f"/api/plans/{plan_id}/selection",
        json={"must_visit": ["bamboo-grove", "tenryuji"], "maybe": ["kissa-matcha"], "excluded": []},
    )
    assert chosen.status_code == 200
    body = client.get(f"/api/plans/{plan_id}").json()
    assert body["status"] == "ready"
    ids = {stop["id"] for day in body["itinerary"]["days"] for stop in day["stops"]}
    assert {"bamboo-grove", "tenryuji"} <= ids
    flight = client.get("/api/flights/lookup", params={"number": "JL3020", "date": "2026-11-14"})
    assert flight.status_code == 200
    assert flight.json()["to_place"]["code"] == "KIX"
    missing = client.get("/api/flights/lookup", params={"number": "NOPE", "date": "2026-11-14"})
    assert missing.status_code == 404
