from __future__ import annotations

import json

from roam_contracts.models import CandidateSet, Itinerary, PlanStatus, TripBrief

from roam_agent.store import PlanRecord


class DynamoPlanStore:
    def __init__(self, table_name: str, client=None) -> None:
        self.table_name = table_name
        if client is None:
            import boto3

            client = boto3.client("dynamodb")
        self.client = client

    def put(self, record: PlanRecord) -> None:
        self.client.put_item(
            TableName=self.table_name,
            Item={
                "plan_id": {"S": record.plan_id},
                "payload": {"S": _dump(record)},
            },
        )

    def get(self, plan_id: str) -> PlanRecord | None:
        found = self.client.get_item(TableName=self.table_name, Key={"plan_id": {"S": plan_id}})
        item = found.get("Item")
        if not item:
            return None
        return _load(item["payload"]["S"])


def _dump(record: PlanRecord) -> str:
    return json.dumps({
        "plan_id": record.plan_id,
        "brief": record.brief.model_dump(mode="json"),
        "status": record.status.value,
        "candidates": None if record.candidates is None else record.candidates.model_dump(mode="json"),
        "itinerary": None if record.itinerary is None else record.itinerary.model_dump(mode="json"),
        "error": record.error,
    })


def _load(payload: str) -> PlanRecord:
    raw = json.loads(payload)
    return PlanRecord(
        plan_id=raw["plan_id"],
        brief=TripBrief.model_validate(raw["brief"]),
        status=PlanStatus(raw["status"]),
        candidates=None if raw["candidates"] is None else CandidateSet.model_validate(raw["candidates"]),
        itinerary=None if raw["itinerary"] is None else Itinerary.model_validate(raw["itinerary"]),
        error=raw.get("error"),
    )
