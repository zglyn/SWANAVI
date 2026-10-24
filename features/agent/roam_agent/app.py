from __future__ import annotations

import asyncio
import os
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from roam_contracts.models import (
    InspectorEvent,
    PlanRevision,
    PlanSelection,
    PlanStatus,
    PlanView,
    TripBrief,
)
from roam_agent.plan import collect_candidates, plan as build_plan, revise
from roam_agent.store import MemoryPlanStore, PlanRecord
from roam_tools.flights import lookup_fixture_flight

app = FastAPI(title="Roam402 gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store = MemoryPlanStore()
_events: deque[InspectorEvent] = deque(maxlen=500)
_waiters: list[asyncio.Queue] = []


def publish(event: InspectorEvent) -> None:
    _events.append(event)
    for queue in list(_waiters):
        queue.put_nowait(event)


def _stamp(brief: TripBrief) -> datetime:
    if brief.arrival is not None:
        return brief.arrival.arrive_at
    if brief.start_date is not None:
        return brief.start_date
    return datetime.now(timezone.utc)


def _tool_event(plan_id: str, payload: dict) -> None:
    publish(InspectorEvent(
        id=f"plan-{uuid.uuid4().hex[:8]}",
        ts=datetime.now(timezone.utc),
        source="agent",
        level="info",
        type="plan.tool_call",
        message=payload.get("summary", payload.get("tool", "tool")),
        data={"plan_id": plan_id, **payload},
    ))


class Ok(BaseModel):
    ok: bool = True


@app.post("/api/plans")
def create_plan(brief: TripBrief, background: BackgroundTasks) -> dict:
    plan_id = "kyoto-demo" if os.environ.get("ROAM_SCRIPTED_AGENT") == "1" else uuid.uuid4().hex[:12]
    record = PlanRecord(plan_id=plan_id, brief=brief, status=PlanStatus.COLLECTING)
    store.put(record)

    def work() -> None:
        try:
            candidates = collect_candidates(brief, lambda payload: _tool_event(plan_id, payload), plan_id)
            record.candidates = candidates
            record.status = PlanStatus.CANDIDATES_READY
            store.put(record)
            publish(InspectorEvent(
                id=f"cand-{plan_id}", ts=_stamp(brief),
                source="agent", level="info", type="plan.candidates", message="Candidates ready",
                data={"candidates": candidates.model_dump(mode="json")},
            ))
        except Exception as exc:
            record.status = PlanStatus.FAILED
            record.error = str(exc)
            store.put(record)
            publish(InspectorEvent(
                id=f"fail-{plan_id}", ts=_stamp(brief),
                source="agent", level="error", type="plan.failed", message=str(exc),
                data={"plan_id": plan_id, "error": str(exc)},
            ))

    background.add_task(work)
    return {"plan_id": plan_id}


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str) -> PlanView:
    record = store.get(plan_id)
    if record is None:
        raise HTTPException(404, "unknown plan")
    return PlanView(status=record.status, candidates=record.candidates, itinerary=record.itinerary, error=record.error)


@app.post("/api/plans/{plan_id}/selection")
def select(plan_id: str, selection: PlanSelection) -> Ok:
    record = store.get(plan_id)
    if record is None or record.candidates is None:
        raise HTTPException(404, "candidates are not ready")
    record.status = PlanStatus.PLANNING
    store.put(record)
    try:
        itinerary = build_plan(record.brief, selection, record.candidates, lambda payload: _tool_event(plan_id, payload), plan_id)
        errors = []
        from roam_agent.validate import validate_itinerary

        errors = validate_itinerary(itinerary)
        if errors and os.environ.get("ROAM_SCRIPTED_AGENT") != "1":
            publish(InspectorEvent(
                id=f"invalid-{plan_id}", ts=_stamp(record.brief),
                source="agent", level="warning", type="plan.invalid", message="re-checking plan",
                data={"plan_id": plan_id, "errors": errors},
            ))
        record.itinerary = itinerary
        record.status = PlanStatus.READY
        store.put(record)
        publish(InspectorEvent(
            id=f"ready-{plan_id}", ts=_stamp(record.brief),
            source="agent", level="success", type="plan.ready", message="Itinerary ready",
            data={"itinerary": itinerary.model_dump(mode="json")},
        ))
    except Exception as exc:
        record.status = PlanStatus.FAILED
        record.error = str(exc)
        store.put(record)
        raise HTTPException(500, str(exc)) from exc
    return Ok()


@app.post("/api/plans/{plan_id}/revise")
def revise_plan(plan_id: str, revision: PlanRevision) -> Ok:
    record = store.get(plan_id)
    if record is None or record.itinerary is None:
        raise HTTPException(404, "no itinerary")
    record.itinerary = revise(record.itinerary, revision, lambda payload: _tool_event(plan_id, payload))
    record.status = PlanStatus.READY
    store.put(record)
    publish(InspectorEvent(
        id=f"revised-{plan_id}", ts=_stamp(record.brief),
        source="agent", level="info", type="plan.ready", message="Itinerary revised",
        data={"itinerary": record.itinerary.model_dump(mode="json")},
    ))
    return Ok()


@app.get("/api/flights/lookup")
def flights(number: str, date: str):
    segment = lookup_fixture_flight(number, date)
    if segment.status.value == "unverified":
        raise HTTPException(404, "flight lookup is not configured for that number")
    return segment


@app.get("/api/events")
async def events():
    queue: asyncio.Queue = asyncio.Queue()
    _waiters.append(queue)
    for event in list(_events):
        queue.put_nowait(event)

    async def gen():
        try:
            while True:
                event = await queue.get()
                yield {"event": "inspector", "data": event.model_dump_json()}
        finally:
            if queue in _waiters:
                _waiters.remove(queue)

    return EventSourceResponse(gen())
