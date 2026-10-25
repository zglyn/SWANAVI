import json
from pathlib import Path

from fastapi.testclient import TestClient
from roam_contracts.models import (
    ConversationFixture,
    SuggestionAction,
    SuggestionActionName,
    SuggestionKind,
    SuggestionStatus,
    UserProfile,
)

from roam_agent.agentcore_app import set_trip_store
from roam_agent.store import MemoryTripStore, TripRecord
from roam_agent.suggestions import alternatives, apply_action, load_catalog, relax_day, remember_reason
from roam_agent.trips import accept_remaining, act_on_suggestion
from roam_agent.validate import validate_itinerary

FIXTURE = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "conversation_kyoto.json"
PROFILE = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "profile.json"


def _proposal():
    return ConversationFixture.model_validate(json.loads(FIXTURE.read_text())).proposal


def _clock(package):
    return [[(stop.id, stop.start.isoformat()) for stop in day.stops] for day in package.itinerary.days]


def _legs_follow(day):
    pairs = list(zip(day.stops, day.stops[1:]))
    assert [(leg.from_stop_id, leg.to_stop_id) for leg in day.legs] == [(left.id, right.id) for left, right in pairs]
    assert all(leg.minutes >= 1 for leg in day.legs)


def _events():
    found = []

    def emit(kind, message, data, level="info"):
        found.append(kind)

    return found, emit


def test_rejecting_the_hotel_picks_a_different_valid_hotel():
    proposal = _proposal()
    before = validate_itinerary(proposal.package.itinerary)
    hotel = next(row for row in proposal.suggestions if row.kind == SuggestionKind.HOTEL)
    change = apply_action(proposal, [], SuggestionAction(suggestion_id=hotel.id, action=SuggestionActionName.REJECT, reason="Too expensive"), load_catalog())
    stay = change.proposal.package.hotels[0]
    assert stay.offer.id != hotel.item.offer.id
    assert stay.offer.id == "gion-house"
    assert stay.offer.total < hotel.item.offer.total
    assert "Gion" in change.proposal.package.itinerary.brief.lodging[0].name
    after = validate_itinerary(change.proposal.package.itinerary)
    assert after == before
    profile = UserProfile.model_validate(json.loads(PROFILE.read_text()))
    saved = remember_reason(profile, "Too expensive")
    assert saved.travel.avoid[-1] == "Too expensive"
    assert remember_reason(saved, "Too expensive").travel.avoid == saved.travel.avoid


def test_rejecting_an_attraction_reflows_that_day():
    proposal = _proposal()
    before = _clock(proposal.package)
    change = apply_action(
        proposal, [],
        SuggestionAction(suggestion_id="sug-stop-tenryuji", action=SuggestionActionName.REJECT),
        load_catalog(),
    )
    day = change.proposal.package.itinerary.days[1]
    assert [stop.id for stop in day.stops] == ["nishiki", "pontocho"]
    assert day.stops[0].start < proposal.package.itinerary.days[1].stops[1].start
    _legs_follow(day)
    assert _clock(change.proposal.package)[0] == before[0]
    assert _clock(change.proposal.package)[2] == before[2]
    assert not any("overlaps" in problem for problem in validate_itinerary(change.proposal.package.itinerary))
    events, emit = _events()
    store = MemoryTripStore()
    record = TripRecord(conversation=ConversationFixture.model_validate(json.loads(FIXTURE.read_text())).conversation, proposal=proposal)
    store.put(record)
    act_on_suggestion(store, emit, store.get(record.trip_id), SuggestionAction(suggestion_id="sug-stop-tenryuji", action=SuggestionActionName.REJECT))
    act_on_suggestion(store, emit, store.get(record.trip_id), SuggestionAction(suggestion_id="sug-stop-tenryuji", action=SuggestionActionName.UNDO))
    restored = store.get(record.trip_id).proposal
    assert [stop.id for stop in restored.package.itinerary.days[1].stops] == [stop.id for stop in proposal.package.itinerary.days[1].stops]
    assert "suggestion.updated" in events
    assert "itinerary.reflowed" in events


def test_make_day_2_more_relaxed_keeps_accepted_stops_and_other_days():
    proposal = _proposal()
    before = _clock(proposal.package)
    accepted = apply_action(
        proposal, [],
        SuggestionAction(suggestion_id="sug-stop-pontocho", action=SuggestionActionName.ACCEPT),
        load_catalog(),
    ).proposal
    assert accepted.package.hotels[0].offer.id == proposal.package.hotels[0].offer.id
    change = relax_day(accepted, [], 2)
    day = change.proposal.package.itinerary.days[1]
    ids = [stop.id for stop in day.stops]
    assert "pontocho" in ids
    assert "nishiki" not in ids
    assert "tenryuji" in ids
    _legs_follow(day)
    assert _clock(change.proposal.package)[0] == before[0]
    assert _clock(change.proposal.package)[2] == before[2]
    kept = next(row for row in change.proposal.suggestions if row.id == "sug-stop-pontocho")
    assert kept.status == SuggestionStatus.ACCEPTED


def test_accept_modify_and_accept_all_leave_rejected_rows_alone():
    proposal = _proposal()
    hotel = next(row for row in proposal.suggestions if row.kind == SuggestionKind.HOTEL)
    events, emit = _events()
    store = MemoryTripStore()
    fixture = ConversationFixture.model_validate(json.loads(FIXTURE.read_text()))
    store.put(TripRecord(conversation=fixture.conversation, proposal=proposal))
    record = store.get("kyoto-demo")
    listed = act_on_suggestion(store, emit, record, SuggestionAction(
        suggestion_id=hotel.id, action=SuggestionActionName.MODIFY, text="cheaper",
    ))[0]
    assert listed.proposal.package.hotels[0].offer.id == hotel.item.offer.id
    assert listed.alternatives
    assert all(row.item.offer.price_per_night < hotel.item.offer.price_per_night for row in listed.alternatives)
    changed = act_on_suggestion(store, emit, store.get("kyoto-demo"), SuggestionAction(
        suggestion_id=hotel.id, action=SuggestionActionName.MODIFY, alternative_id="gion-house",
    ))[0]
    stay = changed.proposal.package.hotels[0]
    assert stay.offer.id == "gion-house"
    assert next(row for row in changed.proposal.suggestions if row.id == hotel.id).status == SuggestionStatus.ACCEPTED
    done = accept_remaining(store, emit, store.get("kyoto-demo"))
    assert all(row.status == SuggestionStatus.ACCEPTED for row in done.suggestions if row.status != SuggestionStatus.REJECTED)
    rejected = apply_action(done, [], SuggestionAction(suggestion_id="sug-stop-tenryuji", action=SuggestionActionName.REJECT), load_catalog()).proposal
    again = accept_remaining(store, emit, TripRecord(conversation=fixture.conversation, proposal=rejected))
    assert next(row for row in again.suggestions if row.id == "sug-stop-tenryuji").status == SuggestionStatus.REJECTED


def test_flight_alternatives_honor_time_of_day_and_max_stops():
    proposal = _proposal()
    morning = alternatives(proposal, [], "sug-out", {"time_of_day": "morning", "max_stops": 0})
    ids = [row.item.id for row in morning]
    assert "out-ua" in ids
    assert "out-aa" not in ids
    assert "out-red" not in ids
    assert "out-jl" not in ids
    afternoon = alternatives(proposal, [], "sug-out", {"text": "afternoon", "max_stops": 0})
    assert afternoon == []
    one_stop = alternatives(proposal, [], "sug-out", {"time_of_day": "afternoon", "max_stops": 1})
    assert [row.item.id for row in one_stop] == ["out-aa"]
    assert one_stop[0].item.stops == 1


def test_suggestion_routes_apply_a_reject_and_a_typed_replan(monkeypatch):
    monkeypatch.delenv("ROAM_PLAN_STORE", raising=False)
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DUFFEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from roam_agent import swan_http
    from roam_agent.app import app

    swan_http.reset()
    fixture = ConversationFixture.model_validate(json.loads(FIXTURE.read_text()))
    store = MemoryTripStore()
    store.put(TripRecord(conversation=fixture.conversation, proposal=fixture.proposal))
    set_trip_store(store)
    client = TestClient(app)
    rejected = client.post(
        "/api/trips/kyoto-demo/suggestions/sug-hotel-hyatt-arashiyama",
        json={"suggestion_id": "sug-hotel-hyatt-arashiyama", "action": "reject", "reason": "Too expensive"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["proposal"]["package"]["hotels"][0]["offer"]["id"] == "gion-house"
    noted = client.post("/api/trips/kyoto-demo/messages", json={"text": "Make day 2 more relaxed"})
    assert noted.status_code == 200
    view = client.get("/api/trips/kyoto-demo").json()
    day = view["proposal"]["package"]["itinerary"]["days"][1]["stops"]
    assert [stop["id"] for stop in day] == ["tenryuji", "nishiki"]
    assert view["proposal"]["package"]["hotels"][0]["offer"]["id"] == "gion-house"
    assert any(message["text"].startswith("Day 2 is lighter") for message in view["conversation"]["messages"])
    missing = client.get("/api/trips/kyoto-demo/suggestions/nope/alternatives")
    assert missing.status_code == 404
    narrowed = client.get(
        "/api/trips/kyoto-demo/suggestions/sug-out/alternatives",
        params={"constraints": json.dumps({"time_of_day": "morning", "max_stops": 0})},
    )
    assert narrowed.status_code == 200
    assert "out-aa" not in {row["item"]["id"] for row in narrowed.json()}
    signed = client.post("/api/auth/magic-link", json={"email": "a@example.com"}).json()
    person = UserProfile.model_validate(json.loads(PROFILE.read_text()))
    person.user_id = signed["user_id"]
    saved = client.put("/api/me/profile", json=person.model_dump(mode="json"), headers={"Authorization": f"Bearer {signed['token']}"})
    assert saved.status_code == 200
    owned = TripRecord(
        user_id=signed["user_id"],
        conversation=fixture.conversation.model_copy(update={"trip_id": "owned-demo"}),
        proposal=fixture.proposal,
    )
    store.put(owned)
    client.post(
        "/api/trips/owned-demo/suggestions/sug-hotel-hyatt-arashiyama",
        json={"suggestion_id": "sug-hotel-hyatt-arashiyama", "action": "reject", "reason": "Too expensive"},
        headers={"Authorization": f"Bearer {signed['token']}"},
    )
    avoid = client.get("/api/me/profile", headers={"Authorization": f"Bearer {signed['token']}"}).json()["travel"]["avoid"]
    assert "Too expensive" in avoid
