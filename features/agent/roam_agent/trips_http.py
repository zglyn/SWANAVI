from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from roam_contracts.models import ChatAnswer, InspectorEvent, Proposal, Suggestion, SuggestionAction, SuggestionResult, TripView
from roam_agent import suggestions as cards
from roam_agent import swan_http, trips
from roam_agent.agentcore_app import get_trip_store
from roam_agent.store import TripRecord

router = APIRouter()


class StartBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class MessageBody(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    answer: ChatAnswer | None = None

    @model_validator(mode="after")
    def one_input(self) -> MessageBody:
        if (self.text is None) == (self.answer is None):
            raise ValueError("send either text or an answer")
        return self


def _emit(kind: str, message: str, data: dict, level: str = "info") -> None:
    from roam_agent.app import publish

    publish(InspectorEvent(
        id=f"{kind}-{uuid.uuid4().hex[:8]}",
        ts=datetime.now(timezone.utc),
        source="agent",
        level=level,
        type=kind,
        message=message,
        data=data,
    ))


def _caller(authorization: str | None) -> trips.Caller:
    if not authorization:
        return trips.Caller()
    user_id = swan_http._user(authorization)
    return trips.Caller(user_id=user_id, profile=swan_http.profiles.get(user_id))


def _record(trip_id: str, caller: trips.Caller) -> TripRecord:
    record = get_trip_store().get(trip_id)
    if record is None or (record.user_id is not None and record.user_id != caller.user_id):
        raise HTTPException(404, "No trip with that id")
    return record


@router.post("/api/trips")
def create_trip(body: StartBody, authorization: str | None = Header(default=None)) -> dict:
    record = trips.start_trip(get_trip_store(), _emit, _caller(authorization), body.message, date.today(), trips.load_script())
    return {"trip_id": record.trip_id}


@router.get("/api/trips/{trip_id}", response_model=TripView)
def get_trip(trip_id: str, authorization: str | None = Header(default=None)) -> TripView:
    return _record(trip_id, _caller(authorization)).view()


@router.post("/api/trips/{trip_id}/messages")
def post_message(trip_id: str, body: MessageBody, authorization: str | None = Header(default=None)) -> dict:
    caller = _caller(authorization)
    try:
        trips.post_message(
            get_trip_store(), _emit, _record(trip_id, caller), caller, date.today(), trips.load_script(),
            text=body.text, answer=body.answer,
        )
    except trips.TripConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


def _constraints(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        found = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "constraints must be JSON") from exc
    if not isinstance(found, dict):
        raise HTTPException(422, "constraints must be a JSON object")
    return found


@router.get("/api/trips/{trip_id}/suggestions/{sid}/alternatives", response_model=list[Suggestion])
def suggestion_alternatives(
    trip_id: str, sid: str, constraints: str | None = Query(default=None), authorization: str | None = Header(default=None),
) -> list[Suggestion]:
    record = _record(trip_id, _caller(authorization))
    if record.proposal is None or not any(row.id == sid for row in record.proposal.suggestions):
        raise HTTPException(404, "No suggestion with that id")
    return cards.alternatives(record.proposal, record.rejected_ids, sid, _constraints(constraints))


@router.post("/api/trips/{trip_id}/suggestions/{sid}", response_model=SuggestionResult)
def suggestion_action(
    trip_id: str, sid: str, body: SuggestionAction, authorization: str | None = Header(default=None),
) -> SuggestionResult:
    if body.suggestion_id != sid:
        raise HTTPException(422, "The suggestion id in the body does not match the path")
    caller = _caller(authorization)
    record = _record(trip_id, caller)
    if record.proposal is None or not any(row.id == sid for row in record.proposal.suggestions):
        raise HTTPException(404, "No suggestion with that id")
    try:
        result, reason = trips.act_on_suggestion(get_trip_store(), _emit, record, body)
    except trips.TripConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if reason and caller.profile is not None and caller.user_id:
        swan_http.profiles.put(cards.remember_reason(caller.profile, reason))
    return result


@router.post("/api/trips/{trip_id}/accept-all", response_model=Proposal)
def accept_all(trip_id: str, authorization: str | None = Header(default=None)) -> Proposal:
    caller = _caller(authorization)
    try:
        return trips.accept_remaining(get_trip_store(), _emit, _record(trip_id, caller))
    except trips.TripConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/api/trips/{trip_id}/plan")
def plan_trip(trip_id: str, background: BackgroundTasks, authorization: str | None = Header(default=None)) -> dict:
    caller = _caller(authorization)
    store = get_trip_store()
    try:
        started = trips.plan_trip(store, _emit, _record(trip_id, caller), caller)
    except trips.TripConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if started:
        background.add_task(trips.build_proposal, store, _emit, trip_id, caller)
    return {"ok": True}
