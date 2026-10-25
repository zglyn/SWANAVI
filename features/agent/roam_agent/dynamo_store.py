from __future__ import annotations

import json

from roam_contracts.models import CandidateSet, Itinerary, PlanStatus, TripBrief

from roam_agent.store import PlanRecord, TripRecord


def _client(client):
    if client is not None:
        return client
    import boto3

    return boto3.client("dynamodb")


class DynamoPlanStore:
    def __init__(self, table_name: str, client=None) -> None:
        self.table_name = table_name
        self.client = _client(client)

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


class DynamoTripStore:
    def __init__(self, table_name: str, client=None) -> None:
        self.table_name = table_name
        self.client = _client(client)

    def put(self, record: TripRecord) -> None:
        self.client.put_item(
            TableName=self.table_name,
            Item={"trip_id": {"S": record.trip_id}, "payload": {"S": record.model_dump_json()}},
        )

    def get(self, trip_id: str) -> TripRecord | None:
        found = self.client.get_item(TableName=self.table_name, Key={"trip_id": {"S": trip_id}})
        item = found.get("Item")
        return None if not item else TripRecord.model_validate_json(item["payload"]["S"])


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
