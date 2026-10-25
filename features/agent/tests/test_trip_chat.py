import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from roam_contracts.models import (
    ChatMessage,
    ChatRole,
    ConversationPhase,
    TripConversation,
    TripFacts,
    TripOrigin,
    UserProfile,
)

from roam_agent.agentcore_app import set_trip_store
from roam_agent.conversation import extract_facts, next_questions, reply
from roam_agent.store import MemoryTripStore
from roam_agent.trips import Caller, build_proposal, load_script, plan_trip, start_trip

TODAY = date(2026, 10, 24)
KYOTO = "Kyoto in late November, 4 days, 2 of us, love food"
OPENING = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "demo_city.json").read_text()
)["opening_prompt"]


def _events():
    found = []

    def emit(kind, message, data, level="info"):
        found.append((kind, message, data, level))

    return found, emit


def test_kyoto_sentence_fills_the_facts_it_states():
    facts = extract_facts(KYOTO, TripFacts(), TODAY)
    assert facts.destination == "Kyoto"
    assert facts.start_date == "2026-11-21"
    assert facts.end_date == "2026-11-24"
    assert facts.travellers == 2
    assert facts.interests == ["food"]
    assert facts.budget is None
    assert facts.origin is None


def test_the_next_questions_are_the_two_most_important_gaps():
    facts = extract_facts(KYOTO, TripFacts(), TODAY)
    assert next_questions(facts, set()) == ["origin", "budget"]
    answered = facts.model_copy(update={"origin": TripOrigin(from_home=False, airport_codes=["SFO"])})
    assert next_questions(answered, {"origin", "budget"}) == []
    blank = TripFacts()
    assert next_questions(blank, set()) == ["destination", "dates"]
    assert next_questions(blank, set(), late=True) == ["destination", "dates"]
    only_people = blank.model_copy(update={
        "destination": "Kyoto", "start_date": "2026-11-21", "end_date": "2026-11-24",
        "origin": TripOrigin(from_home=False, airport_codes=["SFO"]),
    })
    assert next_questions(only_people, set(), late=True) == []


def test_a_profile_airport_is_confirmed_and_a_turn_asks_at_most_two_things():
    profile = UserProfile.model_validate(json.loads(
        (Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "profile.json").read_text()
    ))
    facts = extract_facts(KYOTO, TripFacts(), TODAY)
    conversation = TripConversation(
        trip_id="t1",
        phase=ConversationPhase.CHATTING,
        messages=[ChatMessage(id="m1", role=ChatRole.USER, text=KYOTO, created_at="2026-10-24T15:00:00Z")],
        brief=facts,
    )
    said = reply(conversation, TripFacts(), profile)
    assert len(said.controls) <= 2
    assert said.controls == []
    assert "SFO" in said.text
    assert "budget" in said.text
    assert said.facts.origin.airport_codes[0] == "SFO"
    asked = reply(conversation, TripFacts(), None)
    assert [control.slot for control in asked.controls] == ["origin", "budget"]


def test_conversation_core_does_not_import_fastapi():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "roam_agent"
    for name in ("conversation.py", "trips.py"):
        assert "fastapi" not in (root / name).read_text(encoding="utf-8")


def test_scripted_opening_reaches_a_new_york_proposal_without_an_api_key(monkeypatch):
    monkeypatch.setattr("roam_agent.trips.lookup_destination", lambda words: None)
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_ACCESS_KEY_ID", "ROAM_LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    def live_search(*_args, **_kwargs):
        raise AssertionError("scripted mode called a live search")

    monkeypatch.setattr("roam_agent.autopilot.search_flights", live_search)
    monkeypatch.setattr("roam_agent.autopilot.search_hotels", live_search)
    store = MemoryTripStore()
    events, emit = _events()
    record = start_trip(store, emit, Caller(), OPENING, TODAY, load_script())
    question_rounds = [message for message in record.conversation.messages if message.controls]
    assert len(question_rounds) <= 2
    assert all(len(message.controls) <= 2 for message in question_rounds)
    started = plan_trip(store, emit, store.get(record.trip_id), Caller())
    assert started is True
    build_proposal(store, emit, record.trip_id, Caller())
    saved = store.get(record.trip_id)
    assert saved.conversation.phase == ConversationPhase.PROPOSAL
    package = saved.proposal.package
    assert package.outbound is not None
    assert package.outbound.segments[-1].to_place.code == "JFK"
    assert package.return_flight is not None
    assert package.return_flight.segments[0].from_place.code == "JFK"
    assert package.hotels
    assert package.itinerary.brief.destination == "New York"
    assert len(package.itinerary.days) == 4
    assert any(kind == "proposal.ready" for kind, *_rest in events)


def test_a_trip_with_no_budget_still_plans_and_says_the_assumption(monkeypatch):
    monkeypatch.setattr("roam_agent.trips.lookup_destination", lambda words: None)
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    store = MemoryTripStore()
    events, emit = _events()
    record = start_trip(
        store, emit, Caller(),
        "Kyoto from Nov 21 to Nov 24, 2 of us, from SFO",
        TODAY, None,
    )
    assert record.conversation.brief.budget is None
    assert any("budget" in message.text for message in record.conversation.messages if message.role.value == "assistant")
    assert plan_trip(store, emit, store.get(record.trip_id), Caller()) is True
    build_proposal(store, emit, record.trip_id, Caller())
    saved = store.get(record.trip_id)
    assert saved.conversation.phase == ConversationPhase.PROPOSAL
    assert saved.proposal.package.hotels
    assert saved.conversation.brief.budget is None


def test_trip_routes_stream_the_chat_and_refuse_a_bad_turn(monkeypatch):
    monkeypatch.setattr("roam_agent.trips.lookup_destination", lambda words: None)
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    monkeypatch.delenv("ROAM_PLAN_STORE", raising=False)
    from roam_agent import swan_http
    from roam_agent.app import app

    swan_http.reset()
    set_trip_store(MemoryTripStore())
    client = TestClient(app)
    created = client.post("/api/trips", json={"message": OPENING})
    assert created.status_code == 200
    trip_id = created.json()["trip_id"]
    view = client.get(f"/api/trips/{trip_id}")
    assert view.status_code == 200
    assert view.json()["conversation"]["brief"]["destination"] == "New York"
    both = client.post(f"/api/trips/{trip_id}/messages", json={"text": "hi", "answer": {"slot": "budget", "value": "2000"}})
    assert both.status_code == 422
    neither = client.post(f"/api/trips/{trip_id}/messages", json={})
    assert neither.status_code == 422
    missing = client.post("/api/trips/missing/plan")
    assert missing.status_code == 404
    first = client.post("/api/auth/magic-link", json={"email": "a@example.com"}).json()
    second = client.post("/api/auth/magic-link", json={"email": "b@example.com"}).json()
    owned = client.post(
        "/api/trips",
        json={"message": "Osaka in December, 3 days, 2 of us, from SFO"},
        headers={"Authorization": f"Bearer {first['token']}"},
    )
    hidden = client.get(f"/api/trips/{owned.json()['trip_id']}", headers={"Authorization": f"Bearer {second['token']}"})
    assert hidden.status_code == 404
    monkeypatch.delenv("ROAM_SCRIPTED_AGENT")
    early = client.post("/api/trips", json={"message": "hello"})
    refused = client.post(f"/api/trips/{early.json()['trip_id']}/plan")
    assert refused.status_code == 409
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    answered = client.post(
        f"/api/trips/{trip_id}/messages",
        json={"answer": {"slot": "origin", "value": "SFO"}},
    )
    assert answered.status_code == 200
    planned = client.post(f"/api/trips/{trip_id}/plan")
    assert planned.status_code == 200
    ready = client.get(f"/api/trips/{trip_id}").json()
    assert ready["conversation"]["phase"] == "proposal"
    assert ready["proposal"]["package"]["outbound"]["carrier"]
