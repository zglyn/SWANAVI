from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from roam_contracts.models import CandidateSet, Itinerary, PlanStatus, TripBrief, TripView


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


class TripRecord(TripView):
    user_id: str | None = None

    @property
    def trip_id(self) -> str:
        return self.conversation.trip_id

    def view(self) -> TripView:
        return TripView(conversation=self.conversation, proposal=self.proposal, bookings=self.bookings)


class TripStore(Protocol):
    def put(self, record: TripRecord) -> None: ...
    def get(self, trip_id: str) -> TripRecord | None: ...


class MemoryTripStore:
    def __init__(self) -> None:
        self._rows: dict[str, TripRecord] = {}

    def put(self, record: TripRecord) -> None:
        self._rows[record.trip_id] = record.model_copy(deep=True)

    def get(self, trip_id: str) -> TripRecord | None:
        found = self._rows.get(trip_id)
        return None if found is None else found.model_copy(deep=True)
