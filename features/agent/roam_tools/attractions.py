from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from roam_contracts.geo import haversine_km
from roam_contracts.models import Attraction

ROOT = Path(__file__).resolve().parents[3]
CANDIDATES = ROOT / "contracts" / "fixtures" / "candidates_kyoto.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
_CACHE: dict[str, list[dict]] = {}

INTEREST_TAGS = {
    "temples": {"temples", "place_of_worship"},
    "nature": {"nature", "park", "viewpoint"},
    "museums": {"museums", "museum"},
    "food": {"food"},
    "nightlife": {"nightlife"},
    "crafts": {"crafts"},
    "shopping": {"shopping"},
}


def _curated() -> list[Attraction]:
    if not CANDIDATES.exists():
        return []
    payload = json.loads(CANDIDATES.read_text())
    found = []
    for row in payload["candidates"]:
        if row.get("attraction"):
            found.append(Attraction.model_validate(row["attraction"]))
    return found


def _matches(attraction: Attraction, interests: list[str]) -> bool:
    if not interests:
        return True
    wanted: set[str] = set()
    for interest in interests:
        wanted |= INTEREST_TAGS.get(interest, {interest})
    return attraction.category in wanted or any(tag in (attraction.description or "").lower() for tag in wanted)


def _normalize_category(tags: dict) -> str:
    if tags.get("amenity") == "place_of_worship":
        return "temples"
    tourism = tags.get("tourism") or ""
    if tourism in {"museum", "viewpoint", "attraction", "gallery", "artwork"}:
        if tourism == "museum":
            return "museums"
        if tourism == "viewpoint":
            return "nature"
        return tourism
    if tags.get("leisure") in {"park", "garden"}:
        return "nature"
    if tags.get("amenity") in {"restaurant", "cafe", "fast_food"}:
        return "food"
    return "attraction"


def _overpass(place: str, interests: list[str]) -> list[Attraction]:
    key = f"{place}|{','.join(interests)}"
    if key in _CACHE:
        elements = _CACHE[key]
    else:
        city = place.split(",")[0].strip()
        filters = []
        if not interests or "temples" in interests:
            filters.append('nwr["amenity"="place_of_worship"]["name"]')
        if not interests or "museums" in interests:
            filters.append('nwr["tourism"="museum"]["name"]')
        if not interests or "nature" in interests:
            filters.append('nwr["tourism"="viewpoint"]["name"]')
            filters.append('nwr["leisure"="park"]["name"]')
        if not interests or "food" in interests:
            filters.append('nwr["amenity"="restaurant"]["name"]')
        if not filters:
            filters.append('nwr["tourism"="attraction"]["name"]')
        body = "".join(f"{item}(area.search);" for item in filters)
        query = f'[out:json][timeout:25];area[name="{city}"]->.search;({body});out center 30;'
        response = httpx.post(OVERPASS, data={"data": query}, timeout=30)
        response.raise_for_status()
        elements = response.json().get("elements", [])
        _CACHE[key] = elements
    attractions = []
    for element in elements:
        tags = element.get("tags") or {}
        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lng = element.get("lon") or (element.get("center") or {}).get("lon")
        if lat is None or lng is None or "name" not in tags:
            continue
        category = _normalize_category(tags)
        attractions.append(
            Attraction(
                id=f"osm-{element.get('id')}",
                name=tags["name"],
                category=category,
                location={"lat": lat, "lng": lng},
                area=place.split(",")[0].strip(),
                description=tags.get("description") or tags.get("tourism") or tags.get("amenity") or "OpenStreetMap place",
                image_url=None,
                popularity=0.45,
                typical_duration_min=60 if category in {"museums", "temples"} else 45,
                opening_hours=tags.get("opening_hours"),
                free=True,
                source="osm",
            )
        )
    return attractions


def search_attractions(
    place: str,
    interests: list[str] | None = None,
    near: dict | None = None,
    radius_km: float | None = None,
    limit: int = 20,
) -> list[Attraction]:
    interests = interests or []
    chosen: list[Attraction] = []
    if os.environ.get("ROAM_ATTRACTIONS", "live") == "fixture":
        chosen = [item for item in _curated() if _matches(item, interests)]
    else:
        try:
            chosen = _overpass(place, interests)
        except Exception:
            chosen = []
        if not chosen and "kyoto" in place.lower():
            chosen = [item for item in _curated() if _matches(item, interests)]
        else:
            chosen = [item for item in chosen if _matches(item, interests)] or chosen
    if near is not None and radius_km is not None:
        chosen = [
            item
            for item in chosen
            if haversine_km(near["lat"], near["lng"], item.location.lat, item.location.lng) <= radius_km
        ]
    chosen.sort(key=lambda item: item.popularity, reverse=True)
    return chosen[:limit]
