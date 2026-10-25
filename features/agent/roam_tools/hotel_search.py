from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from roam_contracts.geo import haversine_km
from roam_contracts.models import HotelOffer, HotelSource
from roam_tools.routing import get_travel_matrix

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts" / "fixtures" / "hotel_offers.json"
BUDGET_NIGHTLY = {"budget": 120, "mid": 220, "premium": 380, "luxury": 700}
DOLLAR_LIKE = {"USD", "RLUSD", "USDC"}


def _money(amount, currency: str) -> str:
    value = float(amount)
    text = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
    return f"${text}" if currency.upper() in DOLLAR_LIKE else f"{text} {currency}"


@dataclass
class StayPoint:
    id: str
    lat: float
    lng: float
    day: str | None = None
    weight: float = 1


def _median(points: list[StayPoint]) -> tuple[float, float]:
    weight = sum(point.weight for point in points) or 1
    lat = sum(point.lat * point.weight for point in points) / weight
    lng = sum(point.lng * point.weight for point in points) / weight
    for _ in range(16):
        num_lat = num_lng = den = 0.0
        for point in points:
            dist = haversine_km(lat, lng, point.lat, point.lng) or 0.05
            num_lat += point.weight * point.lat / dist
            num_lng += point.weight * point.lng / dist
            den += point.weight / dist
        if den == 0:
            break
        lat, lng = num_lat / den, num_lng / den
    return lat, lng


def _minutes(matrix: dict, modes: list[str], origin: str, dest: str) -> int:
    best = None
    for mode in modes:
        cell = matrix.get(mode, {}).get(origin, {}).get(dest)
        if not cell:
            continue
        minutes = int(cell["minutes"])
        best = minutes if best is None else min(best, minutes)
    return best if best is not None else 999


def _average(matrix: dict, modes: list[str], hotel_id: str, points: list[StayPoint]) -> int:
    if not points:
        return 0
    total = 0.0
    weight = 0.0
    for point in points:
        total += _minutes(matrix, modes, hotel_id, point.id) * point.weight
        weight += point.weight
    return round(total / weight) if weight else 0


def _clusters(points: list[StayPoint]) -> list[list[StayPoint]]:
    by_day: dict[str, list[StayPoint]] = {}
    for point in points:
        by_day.setdefault(point.day or "stay", []).append(point)
    groups = list(by_day.values())
    if len(groups) < 2:
        return [points]
    far = False
    for left in groups:
        for right in groups:
            if left is right:
                continue
            a = _median(left)
            b = _median(right)
            if haversine_km(a[0], a[1], b[0], b[1]) > 25:
                far = True
    if not far:
        return [points]
    return groups


def rank_hotels(
    catalog: list[HotelOffer],
    points: list[StayPoint],
    *,
    budget_level: str = "mid",
    brands: list[str] | None = None,
    min_stars: float | None = None,
    must_have: list[str] | None = None,
    modes: list[str] | None = None,
    member_programs: list[str] | None = None,
) -> list[HotelOffer]:
    if not catalog or not points:
        return []
    modes = modes or ["walk", "transit"]
    brands = [item.lower() for item in (brands or [])]
    must = [item.lower() for item in (must_have or [])]
    members = [item.lower() for item in (member_programs or [])]
    matrix_points = [{"id": point.id, "lat": point.lat, "lng": point.lng} for point in points]
    matrix_points += [{"id": hotel.id, "lat": hotel.location.lat, "lng": hotel.location.lng} for hotel in catalog]
    matrix = get_travel_matrix(matrix_points, modes)
    target = BUDGET_NIGHTLY.get(budget_level, 220)
    ranked: list[HotelOffer] = []
    for hotel in catalog:
        minutes = _average(matrix, modes, hotel.id, points)
        why: list[str] = [f"{minutes} min average to your picks"]
        score = 100 - minutes
        nightly = float(hotel.price_per_night)
        score -= abs(nightly - target) / 20
        if hotel.brand and hotel.brand.lower() in brands:
            score += 15
            member = any(hotel.brand.lower() in program for program in members)
            why.append(f"{hotel.brand}: you're a member" if member else f"{hotel.brand} is a favourite brand")
        if min_stars is not None and hotel.stars is not None and hotel.stars + 0.01 < min_stars:
            score -= 10
            why.append(f"below your {min_stars:g}-star minimum")
        elif hotel.stars:
            why.append(f"{hotel.stars:g} stars")
        missing = [item for item in must if item not in {amenity.lower() for amenity in hotel.amenities}]
        if missing:
            score -= 4 * len(missing)
        else:
            if must:
                why.append("has " + ", ".join(must))
        if hotel.refundable:
            score += 4
            why.append("refundable")
        if hotel.source == HotelSource.MERCHANT:
            score += 6
            why.append("Swanavi merchant: pay with your wallet")
            if hotel.quote and hotel.quote.viator_price:
                saved = hotel.quote.viator_price - hotel.quote.amount
                why.append(f"save {_money(saved, hotel.quote.currency)} vs the aggregator")
        ranked.append(hotel.model_copy(update={
            "avg_travel_min_to_attractions": minutes,
            "score": round(score, 2),
            "why": why,
        }))
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def propose_split(
    catalog: list[HotelOffer],
    points: list[StayPoint],
    **rank_kwargs,
) -> list[HotelOffer]:
    groups = _clusters(points)
    if len(groups) < 2:
        return []
    single = rank_hotels(catalog, points, **rank_kwargs)
    if not single:
        return []
    per_group = []
    for group in groups:
        ranked = rank_hotels(catalog, group, **rank_kwargs)
        if not ranked:
            return []
        per_group.append((group, ranked[0]))
    single_minutes = single[0].avg_travel_min_to_attractions
    split_total = 0.0
    split_weight = 0.0
    for group, hotel in per_group:
        split_total += hotel.avg_travel_min_to_attractions * len(group)
        split_weight += len(group)
    split_avg = split_total / split_weight if split_weight else single_minutes
    if single_minutes - split_avg <= 45:
        return []
    stays = []
    for group, hotel in per_group:
        days = sorted({point.day for point in group if point.day})
        check_in = days[0] if days else hotel.check_in
        check_out = days[-1] if days else hotel.check_out
        stays.append(hotel.model_copy(update={
            "check_in": check_in,
            "check_out": check_out,
            "why": [*hotel.why, "Split stay: the days are too far apart for one hotel"],
        }))
    return stays


def _load_catalog() -> list[HotelOffer]:
    provider = os.environ.get("HOTEL_SEARCH_PROVIDER", "fixture")
    if provider == "amadeus" and not os.environ.get("AMADEUS_API_KEY"):
        raise RuntimeError("AMADEUS_API_KEY is not set")
    if provider not in {"fixture", "amadeus"}:
        raise RuntimeError(f"Unknown HOTEL_SEARCH_PROVIDER {provider}")
    if provider == "amadeus":
        raise RuntimeError("Amadeus hotel search is not enabled in this build; set HOTEL_SEARCH_PROVIDER=fixture")
    payload = json.loads(FIXTURE.read_text())
    return [HotelOffer.model_validate(row) for row in payload]


def search_hotels(
    attraction_points: list[dict],
    check_in: str,
    check_out: str,
    budget_level: str = "mid",
    brands: list[str] | None = None,
    min_stars: float | None = None,
    must_have: list[str] | None = None,
    travellers: int = 1,
    modes: list[str] | None = None,
    member_programs: list[str] | None = None,
) -> list[HotelOffer]:
    del travellers
    points = [
        StayPoint(
            id=str(item["id"]),
            lat=float(item["lat"]),
            lng=float(item["lng"]),
            day=item.get("day"),
            weight=float(item.get("weight") or 1),
        )
        for item in attraction_points
    ]
    catalog = _load_catalog()
    kwargs = dict(
        budget_level=budget_level,
        brands=brands,
        min_stars=min_stars,
        must_have=must_have,
        modes=modes,
        member_programs=member_programs,
    )
    ranked = rank_hotels(catalog, points, **kwargs)
    splits = propose_split(catalog, points, **kwargs)
    if splits:
        for stay in splits:
            stay.check_in = stay.check_in or check_in
            stay.check_out = stay.check_out or check_out
        others = [item for item in ranked if item.id not in {stay.id for stay in splits}]
        for item in others:
            item.check_in = item.check_in or check_in
            item.check_out = item.check_out or check_out
        return splits + others
    for item in ranked:
        item.check_in = check_in
        item.check_out = check_out
    return ranked
