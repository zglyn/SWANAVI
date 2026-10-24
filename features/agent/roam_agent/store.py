from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from roam_contracts.models import CandidateSet, Itinerary, PlanStatus, TripBrief


@dataclass
class PlanRecord:
    plan_id: str
    brief: TripBrief
    status: PlanStatus = PlanStatus.COLLECTING
    candidates: CandidateSet | None = None
    itinerary: Itinerary | None = None
    error: str | None = None
    events: list = field(default_factory=list)


class PlanStore(Protocol):
    def put(self, record: PlanRecord) -> None: ...
    def get(self, plan_id: str) -> PlanRecord | None: ...


class MemoryPlanStore:
    def __init__(self) -> None:
        self._rows: dict[str, PlanRecord] = {}

    def put(self, record: PlanRecord) -> None:
        self._rows[record.plan_id] = record

    def get(self, plan_id: str) -> PlanRecord | None:
        return self._rows.get(plan_id)
