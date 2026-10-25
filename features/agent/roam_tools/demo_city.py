from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from roam_contracts.models import Quote, TravelPackage

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "contracts" / "fixtures" / "demo_city.json"


def load() -> dict:
    return json.loads(PATH.read_text())


def opening_prompt() -> str:
    return load()["opening_prompt"]


def merchant_ids() -> set[str]:
    return {row["id"] for row in load()["merchants"]}


def is_demo_destination(name: str | None) -> bool:
    text = (name or "").lower()
    city = load()
    names = [city["destination"], *city["aliases"]]
    return any(alias.lower() in text for alias in names)


def local_dt(text: str, zone_name: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(zone_name))


def _hours(city: dict) -> tuple[timedelta, timedelta]:
    return timedelta(hours=city["quote_valid_hours"]), timedelta(hours=city["escrow_cancel_after_hours"])


def freshen_quote(quote: Quote, now: datetime, city: dict | None = None) -> Quote:
    city = city or load()
    valid, escrow = _hours(city)
    moment = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return quote.model_copy(update={
        "expires_at": max(moment, quote.slot_end) + valid,
        "cancel_after": moment + escrow,
    })


def freshen_package(package: TravelPackage, now: datetime | None = None) -> TravelPackage:
    city = load()
    if package.plan_id != city["plan_id"] and not is_demo_destination(package.itinerary.brief.destination):
        return package
    moment = now or datetime.now(timezone.utc)
    updated = package.model_copy(deep=True)
    for day in updated.itinerary.days:
        day.stops = [
            stop.model_copy(update={"quote": freshen_quote(stop.quote, moment, city)}) if stop.quote is not None else stop
            for stop in day.stops
        ]
    stays = []
    for stay in updated.hotels:
        offer = stay.offer
        if offer.quote is not None:
            offer = offer.model_copy(update={"quote": freshen_quote(offer.quote, moment, city)})
        stays.append(stay.model_copy(update={"offer": offer}))
    updated.hotels = stays
    return updated
