from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from roam_contracts.geo import haversine_km
from roam_contracts.models import Leg, LegSource, TravelMode

SPEED_KMH = {"walk": 4.5, "bike": 12, "transit": 18, "taxi": 22, "car": 22}
DETOUR = 1.3
_CACHE: dict[tuple, dict] = {}


@dataclass
class Point:
    id: str
    lat: float
    lng: float


@dataclass
class RoutedStop:
    id: str
    lat: float
    lng: float
    duration_min: int
    earliest: datetime | None = None
    latest: datetime | None = None
    fixed_start: datetime | None = None
    required: bool = False


def _minutes(a: Point, b: Point, mode: str) -> tuple[int, float]:
    if a.id == b.id:
        return 0, 0.0
    distance = haversine_km(a.lat, a.lng, b.lat, b.lng) * DETOUR
    speed = SPEED_KMH[mode]
    minutes = distance / speed * 60
    if mode == "transit":
        minutes += 8
    return max(1, round(minutes)) if distance > 0 else 0, round(distance, 2)


def estimate_matrix(points: list[Point], modes: list[str]) -> dict:
    grid: dict = {}
    for mode in modes:
        grid[mode] = {}
        for origin in points:
            grid[mode][origin.id] = {}
            for dest in points:
                minutes, distance = _minutes(origin, dest, mode)
                grid[mode][origin.id][dest.id] = {
                    "minutes": minutes,
                    "distance_km": distance,
                    "source": "estimate",
                }
    return grid


def _ors_matrix(points: list[Point], modes: list[str]) -> dict:
    key = os.environ.get("ORS_API_KEY")
    if not key:
        raise RuntimeError("ORS_API_KEY is not set")
    profile = {"walk": "foot-walking", "bike": "cycling-regular", "car": "driving-car", "taxi": "driving-car"}
    grid: dict = {}
    locations = [[p.lng, p.lat] for p in points]
    for mode in modes:
        if mode not in profile:
            raise RuntimeError(f"ORS has no {mode} profile")
        response = httpx.post(
            f"https://api.openrouteservice.org/v2/matrix/{profile[mode]}",
            headers={"Authorization": key},
            json={"locations": locations, "metrics": ["distance", "duration"]},
            timeout=8,
        )
        response.raise_for_status()
        body = response.json()
        grid[mode] = {}
        for i, origin in enumerate(points):
            grid[mode][origin.id] = {}
            for j, dest in enumerate(points):
                if i == j:
                    grid[mode][origin.id][dest.id] = {"minutes": 0, "distance_km": 0, "source": "ors"}
                    continue
                grid[mode][origin.id][dest.id] = {
                    "minutes": max(1, round(body["durations"][i][j] / 60)),
                    "distance_km": round(body["distances"][i][j] / 1000, 2),
                    "source": "ors",
                }
    return grid


def get_travel_matrix(points: list[dict], modes: list[str]) -> dict:
    typed = [Point(**p) if not isinstance(p, Point) else p for p in points]
    mode_names = [m.value if isinstance(m, TravelMode) else m for m in modes]
    cache_key = (tuple((p.id, p.lat, p.lng) for p in typed), tuple(mode_names), os.environ.get("ROAM_ROUTING", "estimate"))
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    choice = os.environ.get("ROAM_ROUTING", "estimate")
    try:
        if choice == "ors":
            grid = _ors_matrix(typed, mode_names)
        else:
            grid = estimate_matrix(typed, mode_names)
    except Exception:
        grid = estimate_matrix(typed, mode_names)
    _CACHE[cache_key] = grid
    return grid


def _travel(matrix: dict, mode: str, a: str, b: str) -> tuple[int, float, str]:
    cell = matrix[mode][a][b]
    return cell["minutes"], cell["distance_km"], cell["source"]


def _order_cost(order: list[str], matrix: dict, mode: str, start_id: str) -> int:
    total = 0
    prev = start_id
    for stop_id in order:
        total += _travel(matrix, mode, prev, stop_id)[0]
        prev = stop_id
    return total


def _nearest(stops: list[RoutedStop], matrix: dict, mode: str, start_id: str) -> list[str]:
    remaining = {s.id for s in stops}
    order: list[str] = []
    current = start_id
    while remaining:
        nxt = min(remaining, key=lambda stop_id: _travel(matrix, mode, current, stop_id)[0])
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return order


def _two_opt(order: list[str], matrix: dict, mode: str, start_id: str) -> list[str]:
    best = list(order)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                trial = best[:i] + list(reversed(best[i : j + 1])) + best[j + 1 :]
                if _order_cost(trial, matrix, mode, start_id) < _order_cost(best, matrix, mode, start_id):
                    best = trial
                    improved = True
    return best


def optimize_route(
    stops: list[dict],
    start: dict,
    mode: str,
    window_start: datetime,
    window_end: datetime,
    end: dict | None = None,
) -> dict:
    typed = [RoutedStop(**s) for s in stops]
    mode_name = mode.value if isinstance(mode, TravelMode) else mode
    points = [Point(id="__start__", lat=start["lat"], lng=start["lng"])]
    points.extend(Point(id=s.id, lat=s.lat, lng=s.lng) for s in typed)
    if end is not None:
        points.append(Point(id="__end__", lat=end["lat"], lng=end["lng"]))
    matrix = get_travel_matrix([{"id": p.id, "lat": p.lat, "lng": p.lng} for p in points], [mode_name])
    by_id = {s.id: s for s in typed}
    order = _two_opt(_nearest(typed, matrix, mode_name, "__start__"), matrix, mode_name, "__start__")
    cursor = window_start
    previous = "__start__"
    scheduled: list[str] = []
    unscheduled: list[str] = []
    warnings: list[str] = []
    legs: list[Leg] = []
    starts: dict[str, datetime] = {}
    for stop_id in order:
        stop = by_id[stop_id]
        ride, distance, source = _travel(matrix, mode_name, previous, stop_id)
        arrival = cursor + timedelta(minutes=ride)
        if stop.fixed_start is not None:
            begin = stop.fixed_start
        else:
            begin = arrival
            if stop.earliest is not None and begin < stop.earliest:
                begin = stop.earliest
            if begin < window_start:
                begin = window_start
        finish = begin + timedelta(minutes=stop.duration_min)
        overflows = finish > window_end or (stop.latest is not None and finish > stop.latest)
        if overflows and not stop.required:
            unscheduled.append(stop_id)
            continue
        if overflows and stop.required:
            warnings.append(
                f"Must-visits need more time than the day has; {stop_id} still stays on the plan"
            )
        if begin < window_start:
            begin = window_start
            finish = begin + timedelta(minutes=stop.duration_min)
        starts[stop_id] = begin
        legs.append(Leg(
            from_stop_id=previous, to_stop_id=stop_id, mode=TravelMode(mode_name),
            minutes=ride, distance_km=distance, source=LegSource(source),
        ))
        scheduled.append(stop_id)
        cursor = finish
        previous = stop_id
    required_left = [s.id for s in typed if s.required and s.id in unscheduled]
    for stop_id in required_left:
        unscheduled.remove(stop_id)
        scheduled.append(stop_id)
        warnings.append(f"Must-visits need more time than the day has; {stop_id} still stays on the plan")
    if any(s.required for s in typed) and warnings:
        extra = sum(s.duration_min for s in typed if s.required) 
        warnings.append(f"Must-visits need ~{extra} min more than a tight day can absorb")
    return {
        "order": scheduled,
        "legs": [leg.model_dump(mode="json") for leg in legs],
        "unscheduled": unscheduled,
        "warnings": warnings,
        "starts": {key: value.isoformat() for key, value in starts.items()},
    }
