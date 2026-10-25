from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from roam_contracts.models import (
    ConversationFixture,
    ConversationPhase,
    FlightOffer,
    HotelStay,
    Stop,
    Suggestion,
    SuggestionKind,
    SuggestionStatus,
    TravelPackage,
    TripFacts,
    TripOrigin,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "conversation_kyoto.json"


def _load() -> ConversationFixture:
    return ConversationFixture.model_validate(json.loads(FIXTURE.read_text()))


def _stop_start(package: TravelPackage, stop_id: str) -> datetime:
    for day in package.itinerary.days:
        for stop in day.stops:
            if stop.id == stop_id:
                return stop.start
    raise AssertionError(f"{stop_id} missing")


def test_partial_brief_names_the_required_gaps_and_refuses_to_plan():
    facts = TripFacts()
    assert facts.missing_required() == ["destination", "dates", "origin", "travellers"]
    with pytest.raises(ValueError, match="destination"):
        facts.to_request()


def test_complete_brief_becomes_the_planner_request():
    facts = TripFacts(
        destination="Kyoto",
        origin=TripOrigin(from_home=True, place="San Francisco", airport_codes=["SFO"]),
        start_date="2026-11-14",
        end_date="2026-11-17",
        travellers=2,
        budget=Decimal("2000"),
    )
    request = facts.to_request()
    assert request.destination == "Kyoto"
    assert request.travellers == 2
    assert request.origin.airport_codes == ["SFO"]
    assert request.start_date == "2026-11-14"


def test_suggestion_item_must_match_its_kind():
    package = TravelPackage.model_validate(json.loads(
        (FIXTURE.parent / "package_kyoto.json").read_text()
    ))
    stop = package.itinerary.days[0].stops[0]
    with pytest.raises(ValidationError):
        Suggestion(id="bad", kind=SuggestionKind.FLIGHT, item=stop, required=True)


def test_kyoto_script_asks_at_most_two_questions_then_proposes():
    fixture = _load()
    users = [message for message in fixture.conversation.messages if message.role.value == "user"]
    assert [message.text for message in users] == [
        "Kyoto in late November, 4 days, from SFO",
        "2 of us, about $2,000",
        "Plan it now",
    ]
    assistant_questions = [
        message for message in fixture.conversation.messages
        if message.role.value == "assistant" and message.controls
    ]
    assert len(assistant_questions) == 1
    assert len(assistant_questions[0].controls) <= 2
    assert {control.slot for control in assistant_questions[0].controls} == {"travellers", "budget"}
    assert fixture.conversation.phase == ConversationPhase.PROPOSAL
    assert fixture.conversation.missing == []
    assert fixture.conversation.brief.to_request().travellers == 2


def test_proposal_covers_flights_hotel_and_attractions():
    proposal = _load().proposal
    kinds = {row.kind for row in proposal.suggestions}
    assert SuggestionKind.FLIGHT in kinds
    assert SuggestionKind.HOTEL in kinds
    assert SuggestionKind.ATTRACTION in kinds
    required = [row for row in proposal.suggestions if row.required]
    assert required
    assert all(row.kind in {SuggestionKind.FLIGHT, SuggestionKind.HOTEL} for row in required)
    assert all(isinstance(row.item, FlightOffer) for row in proposal.suggestions if row.kind == SuggestionKind.FLIGHT)
    assert all(isinstance(row.item, HotelStay) for row in proposal.suggestions if row.kind == SuggestionKind.HOTEL)


def test_scripted_accept_modify_and_reject():
    fixture = _load()
    base_hotel = next(row for row in fixture.proposal.suggestions if row.kind == SuggestionKind.HOTEL)
    assert isinstance(base_hotel.item, HotelStay)
    base_nightly = base_hotel.item.offer.price_per_night

    accepted = next(row for row in fixture.accept.proposal.suggestions if row.id == "sug-out")
    assert fixture.accept.action.action.value == "accept"
    assert accepted.status == SuggestionStatus.ACCEPTED
    assert fixture.accept.proposal.package.outbound is not None
    assert fixture.accept.proposal.package.outbound.id == fixture.proposal.package.outbound.id

    modified = next(row for row in fixture.modify.proposal.suggestions if row.kind == SuggestionKind.HOTEL)
    assert isinstance(modified.item, HotelStay)
    assert modified.status == SuggestionStatus.ACCEPTED
    assert modified.item.offer.id == "gion-house"
    assert modified.item.offer.price_per_night < base_nightly
    assert fixture.modify.proposal.package.hotels[0].offer.name == "Gion House"
    assert fixture.modify.proposal.totals.total < fixture.proposal.totals.total

    day_stops = [
        stop.id
        for day in fixture.reject.proposal.package.itinerary.days
        for stop in day.stops
    ]
    assert "tenryuji" not in day_stops
    assert _stop_start(fixture.reject.proposal.package, "nishiki") < _stop_start(fixture.proposal.package, "nishiki")
    rejected = next(row for row in fixture.reject.proposal.suggestions if row.id == "sug-stop-tenryuji")
    assert rejected.status == SuggestionStatus.REJECTED
    assert isinstance(rejected.item, Stop)


def test_fixture_round_trip_keeps_the_phase_and_suggestion_ids():
    fixture = _load()
    again = ConversationFixture.model_validate(fixture.model_dump(mode="json", by_alias=True))
    assert again.conversation.phase == fixture.conversation.phase
    assert [row.id for row in again.proposal.suggestions] == [row.id for row in fixture.proposal.suggestions]
    assert again.conversation.messages[0].created_at == datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)
