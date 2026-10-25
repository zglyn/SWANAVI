from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from roam_contracts.models import (
    AttractionSelection,
    FlightOffer,
    HotelOffer,
    PackageChoices,
    SwanView,
    TravelPackage,
    TripRequest,
    UserProfile,
)
from roam_agent.auth import MemoryAuth
from roam_agent.autopilot import SwanTrip, advance, apply_choices, begin, submit_attractions
from roam_agent.profile_store import MemoryProfileStore

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "contracts" / "fixtures" / "profile.json"
profiles = MemoryProfileStore()
auth = MemoryAuth()
trips: dict[str, SwanTrip] = {}


class MagicLink(BaseModel):
    email: str


class TokenBody(BaseModel):
    token: str


class AuthResult(BaseModel):
    token: str
    user_id: str


def reset() -> None:
    global profiles, auth, trips
    profiles = MemoryProfileStore()
    auth = MemoryAuth()
    trips = {}


def _user(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in first")
    user_id = auth.user_for(authorization.split(" ", 1)[1].strip())
    if not user_id:
        raise HTTPException(401, "That sign-in link is no longer valid")
    return user_id


def _view(trip: SwanTrip) -> SwanView:
    return SwanView(
        plan_id=trip.plan_id,
        phase=trip.phase,
        request=trip.request,
        flights=trip.flights,
        hotels=trip.hotels,
        package=trip.package,
        candidates=trip.candidates,
    )


def _publish(trip: SwanTrip) -> None:
    from datetime import datetime, timezone

    from roam_contracts.models import InspectorEvent
    from roam_agent.app import publish

    kind = {
        "waiting_flights": "plan.flights_ready",
        "waiting_hotels": "plan.hotels_ready",
        "ready": "plan.package_ready",
    }.get(trip.phase.value)
    if kind is None:
        return
    data = _view(trip).model_dump(mode="json", by_alias=True)
    publish(InspectorEvent(
        id=f"{kind}-{trip.plan_id}",
        ts=datetime.now(timezone.utc),
        source="agent",
        level="info",
        type=kind,
        message=trip.phase.value.replace("_", " "),
        data=data,
    ))


@router.post("/api/auth/magic-link", response_model=AuthResult)
def magic_link(body: MagicLink) -> AuthResult:
    token, user_id = auth.start(body.email)
    return AuthResult(token=token, user_id=user_id)


@router.post("/api/auth/verify", response_model=AuthResult)
def verify(body: TokenBody) -> AuthResult:
    user_id = auth.user_for(body.token)
    if not user_id:
        raise HTTPException(401, "That sign-in link is no longer valid")
    return AuthResult(token=body.token, user_id=user_id)


@router.post("/api/auth/demo", response_model=AuthResult)
def demo() -> AuthResult:
    token, user_id = auth.start("demo@swan.test")
    loaded = UserProfile.model_validate(json.loads(PROFILE.read_text()))
    loaded.user_id = user_id
    profiles.put(loaded)
    return AuthResult(token=token, user_id=user_id)


@router.get("/api/me/profile", response_model=UserProfile)
def get_profile(authorization: str | None = Header(default=None)) -> UserProfile:
    found = profiles.get(_user(authorization))
    if found is None:
        raise HTTPException(404, "No profile yet")
    return found


@router.put("/api/me/profile", response_model=UserProfile)
def put_profile(body: UserProfile, authorization: str | None = Header(default=None)) -> UserProfile:
    user_id = _user(authorization)
    body.user_id = user_id
    profiles.put(body)
    return profiles.get(user_id)


@router.delete("/api/me")
def delete_account(authorization: str | None = Header(default=None)) -> dict:
    user_id = _user(authorization)
    profiles.delete(user_id)
    auth.drop_user(user_id)
    for plan_id, trip in list(trips.items()):
        if trip.user_id == user_id:
            del trips[plan_id]
    return {"ok": True}


@router.post("/api/trips/request")
def request_trip(body: TripRequest, authorization: str | None = Header(default=None)) -> dict:
    user_id = _user(authorization)
    profile = profiles.get(user_id)
    if profile is None:
        raise HTTPException(409, "Save a profile before planning")
    trip = begin(user_id, body, profile)
    trips[trip.plan_id] = trip
    _publish(trip)
    return {"plan_id": trip.plan_id, "phase": trip.phase.value}


@router.get("/api/plans/{plan_id}/swan", response_model=SwanView)
def swan_view(plan_id: str, authorization: str | None = Header(default=None)) -> SwanView:
    return _view(_owned(plan_id, authorization))


@router.get("/api/plans/{plan_id}/flights")
def plan_flights(plan_id: str, authorization: str | None = Header(default=None)) -> list[FlightOffer]:
    return _owned(plan_id, authorization).flights


@router.get("/api/plans/{plan_id}/hotels")
def plan_hotels(plan_id: str, authorization: str | None = Header(default=None)) -> list[HotelOffer]:
    return _owned(plan_id, authorization).hotels


@router.post("/api/plans/{plan_id}/attractions")
def plan_attractions(plan_id: str, body: AttractionSelection, authorization: str | None = Header(default=None)) -> dict:
    trip = submit_attractions(_owned(plan_id, authorization), body)
    trips[plan_id] = trip
    _publish(trip)
    return {"ok": True, "phase": trip.phase.value}


@router.post("/api/plans/{plan_id}/choices")
def plan_choices(plan_id: str, body: PackageChoices, authorization: str | None = Header(default=None)) -> dict:
    trip = apply_choices(_owned(plan_id, authorization), body)
    trips[plan_id] = trip
    _publish(trip)
    return {"ok": True, "phase": trip.phase.value}


@router.get("/api/plans/{plan_id}/package", response_model=TravelPackage)
def plan_package(plan_id: str, authorization: str | None = Header(default=None)):
    trip = _owned(plan_id, authorization)
    if trip.package is None:
        raise HTTPException(409, trip.phase.value)
    return trip.package


def _owned(plan_id: str, authorization: str | None) -> SwanTrip:
    user_id = _user(authorization)
    trip = trips.get(plan_id)
    if trip is None or trip.user_id != user_id:
        raise HTTPException(404, "No trip with that id")
    return trip
