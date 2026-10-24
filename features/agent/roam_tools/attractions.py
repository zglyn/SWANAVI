from __future__ import annotations

import json
from pathlib import Path

import httpx

from roam_contracts.geo import haversine_km
from roam_contracts.models import Attraction

ROOT = Path(__file__).resolve().parents[3]
CANDIDATES = ROOT / "contracts" / "fixtures" / "candidates_kyoto.json"
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
    return attraction.category in wanted


def _overpass(place: str, interests: list[str]) -> list[Attraction]:
    key = f"{place}|{','.join(interests)}"
    if key in _CACHE:
        elements = _CACHE[key]
    else:
        filters = []
        if not interests or "temples" in interests:
            filters.append('node["amenity"="place_of_worship"]')
        if not interests or "museums" in interests:
            filters.append('node["tourism"="museum"]')
        if not interests or "nature" in interests:
            filters.append('node["tourism"="viewpoint"]')
        if not filters:
            filters.append('node["tourism"="attraction"]')
        body = ";".join(f'{item}(area.search);' for item in filters)
        query = f'[out:json][timeout:15];area[name="{place}"]->.search;({body});out center 15;'
        response = httpx.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=12)
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
        category = "temples" if tags.get("amenity") == "place_of_worship" else tags.get("tourism", "attraction")
        attractions.append(Attraction(
            id=f"osm-{element.get('id')}",
            name=tags["name"],
            category=category if category in {"museum", "viewpoint"} else "temples" if category == "temples" else category,
            location={"lat": lat, "lng": lng},
            area=place,
            description=tags.get("description") or tags.get("tourism") or tags.get("amenity") or "OpenStreetMap place",
            image_url=None,
            popularity=0.4,
            typical_duration_min=45,
            opening_hours=tags.get("opening_hours"),
            free=True,
            source="osm",
        ))
    return attractions


def search_attractions(
    place: str,
    interests: list[str] | None = None,
    near: dict | None = None,
    radius_km: float | None = None,
    limit: int = 20,
) -> list[Attraction]:
    interests = interests or []
    chosen = [item for item in _curated() if place.lower().startswith("kyoto") or "kyoto" in place.lower()]
    chosen = [item for item in chosen if _matches(item, interests)]
    if "kyoto" not in place.lower():
        try:
            chosen = _overpass(place, interests)
        except Exception:
            chosen = []
    if near is not None and radius_km is not None:
        chosen = [
            item for item in chosen
            if haversine_km(near["lat"], near["lng"], item.location.lat, item.location.lng) <= radius_km
        ]
    chosen.sort(key=lambda item: item.popularity, reverse=True)
    return chosen[:limit]
