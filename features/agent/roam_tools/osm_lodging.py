"""OpenStreetMap hotels via Overpass. No live rates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx

from roam_contracts.models import GeoPoint, HotelOffer, HotelSource

OVERPASS = "https://overpass-api.de/api/interpreter"
PLACEHOLDER_NIGHTLY = {
    "budget": Decimal("90"),
    "mid": Decimal("160"),
    "premium": Decimal("260"),
    "luxury": Decimal("420"),
}


def _nights(check_in: str, check_out: str) -> int:
    start = date.fromisoformat(check_in[:10])
    end = date.fromisoformat(check_out[:10])
    return max(1, (end - start).days)


def fetch_hotels_near(
    lat: float,
    lng: float,
    *,
    check_in: str,
    check_out: str,
    budget_level: str = "mid",
    radius_m: int = 8000,
    limit: int = 30,
) -> list[HotelOffer]:
    query = f"""
    [out:json][timeout:25];
    (
      node["tourism"="hotel"](around:{radius_m},{lat},{lng});
      way["tourism"="hotel"](around:{radius_m},{lat},{lng});
      node["tourism"="guest_house"](around:{radius_m},{lat},{lng});
      way["tourism"="guest_house"](around:{radius_m},{lat},{lng});
      node["tourism"="hostel"](around:{radius_m},{lat},{lng});
    );
    out center {limit};
    """
    response = httpx.post(OVERPASS, data={"data": query}, timeout=30)
    response.raise_for_status()
    elements = response.json().get("elements") or []
    nightly = PLACEHOLDER_NIGHTLY.get(budget_level, PLACEHOLDER_NIGHTLY["mid"])
    nights = _nights(check_in, check_out)
    offers: list[HotelOffer] = []
    for element in elements:
        tags = element.get("tags") or {}
        name = tags.get("name")
        point_lat = element.get("lat") or (element.get("center") or {}).get("lat")
        point_lng = element.get("lon") or (element.get("center") or {}).get("lon")
        if not name or point_lat is None or point_lng is None:
            continue
        stars = None
        if tags.get("stars"):
            try:
                stars = float(tags["stars"])
            except ValueError:
                stars = None
        amenity_tags = []
        for key in ("wifi", "internet_access", "breakfast", "parking", "air_conditioning"):
            if tags.get(key) in {"yes", "wlan", "free"}:
                amenity_tags.append(key.replace("_", " "))
        osm_id = element.get("id")
        offers.append(
            HotelOffer(
                id=f"osm-{osm_id}",
                name=name,
                brand=tags.get("brand"),
                stars=stars,
                location=GeoPoint(lat=float(point_lat), lng=float(point_lng)),
                area=tags.get("addr:suburb") or tags.get("addr:city"),
                price_per_night=nightly,
                total=nightly * nights,
                currency="USD",
                amenities=amenity_tags,
                refundable=False,
                why=["OpenStreetMap listing", "rate not confirmed"],
                image_url=None,
                source=HotelSource.PROVIDER,
                deep_link=f"https://www.openstreetmap.org/{element.get('type', 'node')}/{osm_id}",
                check_in=check_in,
                check_out=check_out,
            )
        )
    return offers
