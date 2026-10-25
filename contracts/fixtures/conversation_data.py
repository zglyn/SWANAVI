from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from roam_contracts.models import (
    ChatAnswer,
    ChatMessage,
    ChatRole,
    Control,
    ControlType,
    ConversationFixture,
    ConversationPhase,
    HotelOffer,
    HotelStay,
    PackageTotals,
    Proposal,
    ScriptedChange,
    Stop,
    StopKind,
    Suggestion,
    SuggestionAction,
    SuggestionActionName,
    SuggestionKind,
    SuggestionStatus,
    TravelPackage,
    TripConversation,
    TripFacts,
    TripOrigin,
)

TRIP_ID = "kyoto-demo"
WHEN = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)


def _at(minutes: int) -> datetime:
    return WHEN + timedelta(minutes=minutes)


def _suggestions(package: TravelPackage) -> list[Suggestion]:
    rows: list[Suggestion] = []
    if package.outbound is not None:
        rows.append(Suggestion(
            id="sug-out",
            kind=SuggestionKind.FLIGHT,
            item=package.outbound,
            why=list(package.outbound.why),
            alternatives_available=True,
            required=True,
        ))
    if package.return_flight is not None:
        rows.append(Suggestion(
            id="sug-ret",
            kind=SuggestionKind.FLIGHT,
            item=package.return_flight,
            why=list(package.return_flight.why),
            alternatives_available=True,
            required=True,
        ))
    for stay in package.hotels:
        rows.append(Suggestion(
            id=f"sug-hotel-{stay.offer.id}",
            kind=SuggestionKind.HOTEL,
            item=stay,
            why=list(stay.offer.why),
            alternatives_available=True,
            required=True,
        ))
    for day in package.itinerary.days:
        for stop in day.stops:
            if stop.kind != StopKind.ATTRACTION:
                continue
            why = [stop.attraction.category] if stop.attraction is not None else []
            rows.append(Suggestion(
                id=f"sug-stop-{stop.id}",
                kind=SuggestionKind.ATTRACTION,
                item=stop,
                why=why,
                alternatives_available=True,
                required=False,
            ))
    return rows


def _proposal(package: TravelPackage, suggestions: list[Suggestion], totals: PackageTotals | None = None) -> Proposal:
    return Proposal(
        trip_id=TRIP_ID,
        package=package,
        suggestions=suggestions,
        totals=totals or package.totals,
    )


def _replace(suggestions: list[Suggestion], sid: str, **changes) -> list[Suggestion]:
    return [row.model_copy(update=changes) if row.id == sid else row for row in suggestions]


def _gion(out: Path) -> HotelStay:
    offers = json.loads((out / "hotel_offers.json").read_text())
    raw = next(row for row in offers if row["id"] == "gion-house")
    offer = HotelOffer.model_validate(raw)
    return HotelStay(offer=offer, check_in=offer.check_in or "2026-11-14", check_out=offer.check_out or "2026-11-16")


def _lodging_stop(stop: Stop, stay: HotelStay) -> Stop:
    if stop.kind != StopKind.LODGING:
        return stop
    if stop.title.startswith("Check in"):
        title = f"Check in at {stay.offer.name}"
    elif stop.title.startswith("Check out"):
        title = f"Check out of {stay.offer.name}"
    else:
        return stop
    return stop.model_copy(update={"title": title, "location": stay.offer.location})


def _swap_hotel(package: TravelPackage, stay: HotelStay) -> TravelPackage:
    pkg = package.model_copy(deep=True)
    pkg.hotels = [stay]
    lodging = pkg.itinerary.brief.lodging
    if lodging:
        lodging[0] = lodging[0].model_copy(update={
            "name": stay.offer.name,
            "location": stay.offer.location,
        })
    for day in pkg.itinerary.days:
        day.stops = [_lodging_stop(stop, stay) for stop in day.stops]
    return pkg


def _drop_stop(package: TravelPackage, stop_id: str) -> TravelPackage:
    pkg = package.model_copy(deep=True)
    for day in pkg.itinerary.days:
        if not any(stop.id == stop_id for stop in day.stops):
            continue
        removed = next(stop for stop in day.stops if stop.id == stop_id)
        rest = [stop for stop in day.stops if stop.id != stop_id]
        if not rest:
            day.stops = []
            day.legs = []
            continue
        delta = rest[0].start - removed.start
        day.stops = [
            stop.model_copy(update={"start": stop.start - delta, "end": stop.end - delta})
            for stop in rest
        ]
        day.legs = [
            leg for leg in day.legs
            if leg.from_stop_id != stop_id and leg.to_stop_id != stop_id
        ]
    return pkg


def _conversation() -> TripConversation:
    brief = TripFacts(
        destination="Kyoto",
        origin=TripOrigin(from_home=True, place="San Francisco", airport_codes=["SFO"]),
        start_date="2026-11-14",
        end_date="2026-11-17",
        travellers=2,
        budget=Decimal("2000"),
        pace="balanced",
    )
    questions = ChatMessage(
        id="m2",
        role=ChatRole.ASSISTANT,
        text="Kyoto from Nov 14 to Nov 17, leaving SFO. How many people are going, and what is the budget?",
        controls=[
            Control(slot="travellers", type=ControlType.CHIPS, options=["1", "2", "3", "4+"]),
            Control(slot="budget", type=ControlType.SLIDER, min=500, max=5000, value=1500),
        ],
        created_at=_at(1),
    )
    return TripConversation(
        trip_id=TRIP_ID,
        phase=ConversationPhase.PROPOSAL,
        brief=brief,
        messages=[
            ChatMessage(id="m1", role=ChatRole.USER, text="Kyoto in late November, 4 days, from SFO", created_at=_at(0)),
            questions,
            ChatMessage(
                id="m3",
                role=ChatRole.USER,
                text="2 of us, about $2,000",
                answers=[ChatAnswer(slot="travellers", value=2), ChatAnswer(slot="budget", value="2000")],
                created_at=_at(2),
            ),
            ChatMessage(
                id="m4",
                role=ChatRole.ASSISTANT,
                text="I'll assume a balanced pace. You can change that later. Plan it whenever you are ready.",
                created_at=_at(3),
            ),
            ChatMessage(id="m5", role=ChatRole.USER, text="Plan it now", created_at=_at(4)),
            ChatMessage(
                id="m6",
                role=ChatRole.ASSISTANT,
                text="Your Kyoto trip is ready. It has flights, a hotel, and three days of stops.",
                created_at=_at(5),
            ),
        ],
    )


def build(out: Path) -> ConversationFixture:
    package = TravelPackage.model_validate(json.loads((out / "package_kyoto.json").read_text()))
    suggestions = _suggestions(package)
    base = _proposal(package, suggestions)
    accepted = _proposal(package, _replace(suggestions, "sug-out", status=SuggestionStatus.ACCEPTED))

    stay = _gion(out)
    hotel_id = next(row.id for row in suggestions if row.kind == SuggestionKind.HOTEL)
    swapped = _swap_hotel(package, stay)
    hotel_totals = PackageTotals(
        flights=package.totals.flights,
        hotels=stay.offer.total,
        activities=package.totals.activities,
        total=package.totals.flights + stay.offer.total + package.totals.activities,
        currency=package.totals.currency,
        savings=Decimal("40"),
    )
    modified = _proposal(
        swapped,
        _replace(suggestions, hotel_id, status=SuggestionStatus.ACCEPTED, item=stay, why=list(stay.offer.why)),
        hotel_totals,
    )

    dropped = _drop_stop(package, "tenryuji")
    rejected = _proposal(
        dropped,
        _replace(suggestions, "sug-stop-tenryuji", status=SuggestionStatus.REJECTED),
    )
    return ConversationFixture(
        conversation=_conversation(),
        proposal=base,
        accept=ScriptedChange(
            action=SuggestionAction(suggestion_id="sug-out", action=SuggestionActionName.ACCEPT),
            proposal=accepted,
        ),
        modify=ScriptedChange(
            action=SuggestionAction(
                suggestion_id=hotel_id,
                action=SuggestionActionName.MODIFY,
                alternative_id="gion-house",
            ),
            proposal=modified,
        ),
        reject=ScriptedChange(
            action=SuggestionAction(
                suggestion_id="sug-stop-tenryuji",
                action=SuggestionActionName.REJECT,
                reason="Bad time",
            ),
            proposal=rejected,
        ),
    )


def write_conversation(out: Path) -> None:
    fixture = build(out)
    payload = fixture.model_dump(mode="json", by_alias=True)
    (out / "conversation_kyoto.json").write_text(json.dumps(payload, indent=2) + "\n")
