from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from roam_contracts.models import (
    ChatAnswer,
    ChatMessage,
    ChatRole,
    ConversationFixture,
    ConversationPhase,
    GeoPoint,
    HomeBase,
    Proposal,
    SuggestionAction,
    SuggestionActionName,
    SuggestionResult,
    TripConversation,
    TripFacts,
    UserProfile,
)
from roam_agent import conversation as talk
from roam_agent import suggestions as cards
from roam_agent.autopilot import begin
from roam_agent.store import TripRecord, TripSnapshot, TripStore
from roam_agent.validate import validate_itinerary

SCRIPT = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "conversation_kyoto.json"
Emit = Callable[..., None]


class TripConflict(Exception):
    pass


@dataclass(frozen=True)
class Caller:
    user_id: str | None = None
    profile: UserProfile | None = None


def load_script() -> ConversationFixture | None:
    if os.environ.get("ROAM_SCRIPTED_AGENT") != "1":
        return None
    return ConversationFixture.model_validate_json(SCRIPT.read_text())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _message(messages: list[ChatMessage], role: ChatRole, text: str, **extra) -> ChatMessage:
    return ChatMessage(id=f"m{len(messages) + 1}", role=role, text=text, created_at=_now(), **extra)


def _say(emit: Emit, trip_id: str, message: ChatMessage) -> None:
    for chunk in re.findall(r"\S+\s*", message.text):
        emit("chat.delta", chunk, {"trip_id": trip_id, "message_id": message.id, "delta": chunk})
    emit("chat.message", message.text, {"trip_id": trip_id, "message": message.model_dump(mode="json")})


def _brief_changed(emit: Emit, conversation: TripConversation) -> None:
    emit("brief.updated", "Trip details updated", {
        "trip_id": conversation.trip_id,
        "brief": conversation.brief.model_dump(mode="json"),
        "missing": conversation.missing,
    })


def _with_answer(messages: list[ChatMessage], answer: ChatAnswer, facts: TripFacts) -> list[ChatMessage]:
    last = messages[-1]
    if last.role == ChatRole.USER and last.answers is not None:
        answers = [item for item in last.answers if item.slot != answer.slot] + [answer]
        return [*messages[:-1], last.model_copy(update={"answers": answers, "text": talk.answers_text(answers, facts)})]
    return [*messages, _message(messages, ChatRole.USER, talk.answers_text([answer], facts), answers=[answer])]


def _turn(
    store: TripStore, emit: Emit, record: TripRecord, caller: Caller, today: date,
    script: ConversationFixture | None, text: str | None, answer: ChatAnswer | None,
) -> TripRecord:
    conversation = record.conversation
    before = conversation.brief
    if answer is not None:
        facts = talk.apply_answer(before, answer)
        messages = _with_answer(conversation.messages, answer, facts)
    else:
        facts = talk.extract_facts(text or "", before, today)
        if script is not None and not conversation.messages:
            facts = talk.pin_script(facts, script)
        messages = [*conversation.messages, _message(conversation.messages, ChatRole.USER, text or "")]
    conversation = conversation.model_copy(update={"brief": facts, "messages": messages})
    said = None
    if not talk.awaiting_answers(conversation):
        reply = talk.reply(conversation, before, caller.profile)
        said = _message(messages, ChatRole.ASSISTANT, reply.text, controls=reply.controls)
        conversation = conversation.model_copy(update={"brief": reply.facts, "messages": [*messages, said]})
    record = record.model_copy(update={"user_id": record.user_id or caller.user_id, "conversation": conversation})
    store.put(record)
    if conversation.brief != before:
        _brief_changed(emit, conversation)
    if said is not None:
        _say(emit, record.trip_id, said)
    return record


def start_trip(
    store: TripStore, emit: Emit, caller: Caller, text: str, today: date, script: ConversationFixture | None = None,
) -> TripRecord:
    conversation = TripConversation(trip_id=uuid.uuid4().hex[:12], phase=ConversationPhase.CHATTING)
    return _turn(store, emit, TripRecord(conversation=conversation), caller, today, script, text, None)


def post_message(
    store: TripStore, emit: Emit, record: TripRecord, caller: Caller, today: date,
    script: ConversationFixture | None = None, *, text: str | None = None, answer: ChatAnswer | None = None,
) -> TripRecord:
    if record.conversation.phase == ConversationPhase.PROPOSAL and text:
        return apply_note(store, emit, record, text)
    if record.conversation.phase != ConversationPhase.CHATTING:
        raise TripConflict("This trip already has a plan. Change it from the proposal.")
    return _turn(store, emit, record, caller, today, script, text, answer)


def plan_trip(store: TripStore, emit: Emit, record: TripRecord, caller: Caller) -> bool:
    conversation = record.conversation
    if conversation.phase != ConversationPhase.CHATTING:
        return False
    facts, assumed = talk.with_defaults(conversation.brief, caller.profile)
    missing = facts.missing_required()
    if missing:
        raise TripConflict(talk.still_need(missing))
    messages = [*conversation.messages, _message(conversation.messages, ChatRole.USER, talk.PLAN_NOW)]
    asked = next(message for message in reversed(conversation.messages) if message.role == ChatRole.ASSISTANT)
    note = _message(messages, ChatRole.ASSISTANT, talk.assume(assumed)) if assumed and asked.controls else None
    conversation = conversation.model_copy(update={
        "phase": ConversationPhase.PLANNING,
        "brief": facts,
        "messages": [*messages, note] if note else messages,
    })
    store.put(record.model_copy(update={"user_id": record.user_id or caller.user_id, "conversation": conversation}))
    if facts != record.conversation.brief:
        _brief_changed(emit, conversation)
    if note is not None:
        _say(emit, conversation.trip_id, note)
    return True


def _planner(profile: UserProfile | None, facts: TripFacts) -> UserProfile:
    base = profile or UserProfile(
        user_id="guest", name="Guest",
        home=HomeBase(address="", location=GeoPoint(lat=0, lng=0), airport_codes=list(facts.origin.airport_codes)),
    )
    travel = base.travel.model_copy(update={
        "pace": facts.pace or base.travel.pace,
        "interests": facts.interests or base.travel.interests,
    })
    return base.model_copy(update={"travel": travel})


def build_proposal(store: TripStore, emit: Emit, trip_id: str, caller: Caller) -> None:
    record = store.get(trip_id)
    if record is None or record.conversation.phase != ConversationPhase.PLANNING:
        return
    conversation = record.conversation
    facts = conversation.brief

    def tool(name: str, summary: str, level: str = "info") -> None:
        emit("plan.tool_call", summary, {"plan_id": trip_id, "trip_id": trip_id, "tool": name, "summary": summary}, level)

    tool("search_flights", f"Finding flights from {talk.origin_label(facts.origin)} to {facts.destination}")
    try:
        package = begin(caller.user_id or "guest", facts.to_request(), _planner(caller.profile, facts), plan_id=trip_id).package
        if package is None:
            raise RuntimeError("the planner stopped before it had a package")
    except Exception as exc:
        failed = _message(conversation.messages, ChatRole.ASSISTANT, f"I could not finish the plan: {exc}. Try again in a moment.")
        store.put(record.model_copy(update={"conversation": conversation.model_copy(update={
            "phase": ConversationPhase.CHATTING,
            "messages": [*conversation.messages, failed],
        })}))
        _say(emit, trip_id, failed)
        emit("plan.failed", str(exc), {"plan_id": trip_id, "trip_id": trip_id, "error": str(exc)}, "error")
        return
    problems = validate_itinerary(package.itinerary)
    for name, summary, level in talk.progress(package, problems):
        tool(name, summary, level)
    proposal = Proposal.from_package(trip_id, package)
    ready = _message(conversation.messages, ChatRole.ASSISTANT, talk.ready_text(proposal, problems))
    store.put(record.model_copy(update={
        "proposal": proposal,
        "conversation": conversation.model_copy(update={
            "phase": ConversationPhase.PROPOSAL,
            "messages": [*conversation.messages, ready],
        }),
    }))
    _say(emit, trip_id, ready)
    emit("proposal.ready", ready.text, {"trip_id": trip_id, "proposal": proposal.model_dump(mode="json", by_alias=True)}, "success")


def _proposal(record: TripRecord) -> Proposal:
    if record.proposal is None:
        raise TripConflict("This trip has no proposal yet")
    return record.proposal


def _snapshot(record: TripRecord) -> TripSnapshot:
    proposal = _proposal(record)
    return TripSnapshot(proposal=proposal.model_copy(deep=True), rejected_ids=list(record.rejected_ids))


def _publish_change(emit: Emit, record: TripRecord, change: cards.Change) -> None:
    if change.suggestion is not None:
        emit("suggestion.updated", change.removed_title or "Suggestion updated", {
            "trip_id": record.trip_id,
            "suggestion": change.suggestion.model_dump(mode="json"),
            "reason": change.reason,
        })
    if change.reflowed and record.proposal is not None:
        emit("itinerary.reflowed", "The itinerary was updated", {
            "trip_id": record.trip_id,
            "problems": validate_itinerary(record.proposal.package.itinerary),
        })


def act_on_suggestion(store: TripStore, emit: Emit, record: TripRecord, action: SuggestionAction) -> tuple[SuggestionResult, str | None]:
    proposal = _proposal(record)
    if action.action == SuggestionActionName.UNDO:
        if not record.history:
            return SuggestionResult(proposal=proposal), None
        prior = record.history[-1]
        store.put(record.model_copy(update={
            "proposal": prior.proposal,
            "rejected_ids": list(prior.rejected_ids),
            "history": record.history[:-1],
        }))
        emit("suggestion.updated", "Restored the previous suggestion", {"trip_id": record.trip_id})
        return SuggestionResult(proposal=prior.proposal), None
    if action.action == SuggestionActionName.MODIFY and not action.alternative_id:
        constraints = dict(action.constraints or {})
        if action.text:
            constraints["text"] = action.text
        rows = cards.alternatives(proposal, record.rejected_ids, action.suggestion_id, constraints)
        return SuggestionResult(proposal=proposal, alternatives=rows), None
    change = cards.apply_action(proposal, record.rejected_ids, action, cards.load_catalog())
    if not change.changed:
        return SuggestionResult(proposal=proposal), None
    updated = record.model_copy(update={
        "proposal": change.proposal,
        "rejected_ids": change.rejected_ids,
        "history": [*record.history, _snapshot(record)],
    })
    store.put(updated)
    _publish_change(emit, updated, change)
    return SuggestionResult(proposal=change.proposal), change.reason


def accept_remaining(store: TripStore, emit: Emit, record: TripRecord) -> Proposal:
    proposal = cards.accept_all(_proposal(record))
    store.put(record.model_copy(update={"proposal": proposal, "history": [*record.history, _snapshot(record)]}))
    emit("suggestion.updated", "Accepted the open items", {"trip_id": record.trip_id})
    return proposal


def apply_note(store: TripStore, emit: Emit, record: TripRecord, text: str) -> TripRecord:
    proposal = _proposal(record)
    messages = [*record.conversation.messages, _message(record.conversation.messages, ChatRole.USER, text)]
    day = cards.relaxed_day_number(text)
    change = cards.relax_day(proposal, record.rejected_ids, day) if day is not None else None
    if change is not None and change.changed:
        note = f"Day {day} is lighter. I removed {change.removed_title}. Accepted stops stayed."
        said = _message(messages, ChatRole.ASSISTANT, note)
        updated = record.model_copy(update={
            "proposal": change.proposal,
            "rejected_ids": change.rejected_ids,
            "history": [*record.history, _snapshot(record)],
            "conversation": record.conversation.model_copy(update={"messages": [*messages, said]}),
        })
        store.put(updated)
        _say(emit, record.trip_id, said)
        _publish_change(emit, updated, change)
        return updated
    note = (
        f"Day {day} stays as it is. Those stops are already accepted."
        if day is not None
        else "Name the day to lighten, for example make day 2 more relaxed."
    )
    said = _message(messages, ChatRole.ASSISTANT, note)
    updated = record.model_copy(update={
        "conversation": record.conversation.model_copy(update={"messages": [*messages, said]}),
    })
    store.put(updated)
    _say(emit, record.trip_id, said)
    return updated
