from __future__ import annotations

import os
import uuid

from roam_contracts.models import PlanRevision, PlanSelection, PlanStatus, TripBrief

from roam_agent.dynamo_store import DynamoPlanStore
from roam_agent.llm import runtime_endpoints
from roam_agent.plan import collect_candidates, plan as build_plan, revise
from roam_agent.store import MemoryPlanStore, PlanRecord, PlanStore

_store: PlanStore | None = None


def get_store() -> PlanStore:
    global _store
    if _store is None:
        if os.environ.get("ROAM_PLAN_STORE") == "dynamodb":
            _store = DynamoPlanStore(os.environ.get("ROAM_PLAN_TABLE", "roam-plans"))
        else:
            _store = MemoryPlanStore()
    return _store


def set_store(store: PlanStore | None) -> None:
    global _store
    _store = store


def handle_invocation(payload: dict) -> dict:
    action = payload.get("action") or "plan"
    events: list[dict] = []
    store = get_store()
    if action == "revise":
        record = store.get(payload["plan_id"])
        if record is None or record.itinerary is None:
            return {"error": "no itinerary"}
        updated = revise(record.itinerary, PlanRevision.model_validate(payload["revision"]), events.append)
        record.itinerary = updated
        record.status = PlanStatus.READY
        store.put(record)
        return {"plan_id": record.plan_id, "itinerary": updated.model_dump(mode="json"), "events": events}
    brief = TripBrief.model_validate(payload["brief"])
    plan_id = payload.get("plan_id") or uuid.uuid4().hex[:12]
    selection = PlanSelection.model_validate(payload.get("selection") or {"must_visit": [], "maybe": [], "excluded": []})
    candidates = collect_candidates(brief, events.append, plan_id)
    itinerary = build_plan(brief, selection, candidates, events.append, plan_id)
    store.put(PlanRecord(
        plan_id=plan_id, brief=brief, status=PlanStatus.READY,
        candidates=candidates, itinerary=itinerary,
    ))
    return {
        "plan_id": plan_id,
        "itinerary": itinerary.model_dump(mode="json"),
        "events": events,
        "config": runtime_endpoints(),
    }


def main() -> None:
    from bedrock_agentcore import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload):
        return handle_invocation(payload or {})

    app.run()


if __name__ == "__main__":
    main()
