from __future__ import annotations

import json
import os
import time
from pathlib import Path

from roam_contracts.models import FlightOffer, TimeOfDayWindow

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts" / "fixtures" / "flight_offers.json"
TTL_SEC = 15 * 60
_CACHE: dict[tuple, tuple[float, list[FlightOffer]]] = {}
_LOADS = {"fixture": 0}

WINDOWS = {
    "red_eye": range(0, 5),
    "early_morning": range(5, 8),
    "morning": range(8, 12),
    "afternoon": range(12, 17),
    "evening": range(17, 22),
}


def clear_flight_cache() -> None:
    _CACHE.clear()
    _LOADS["fixture"] = 0


def flight_load_count() -> int:
    return _LOADS["fixture"]


def _hour(moment: str) -> int:
    return int(moment[11:13])


def _fits(window: str, depart_at: str) -> bool:
    if window in ("any", TimeOfDayWindow.ANY.value):
        return True
    return _hour(depart_at) in WINDOWS.get(window, range(0, 24))


def _asleep(arrive_at: str, sleep_time: str, wake_time: str) -> bool:
    hour = _hour(arrive_at)
    sleep_h = int(sleep_time.split(":")[0])
    wake_h = int(wake_time.split(":")[0])
    if sleep_h > wake_h:
        return hour >= sleep_h or hour < wake_h
    return sleep_h <= hour < wake_h


def rank_flights(
    offers: list[FlightOffer],
    *,
    outbound_window: str,
    return_window: str,
    favourite_airlines: list[str] | None = None,
    avoid_red_eye: bool = False,
    sleep_time: str = "23:00",
    wake_time: str = "07:30",
    max_stops: int = 2,
    limit: int = 10,
) -> list[FlightOffer]:
    favourites = {item.upper() for item in (favourite_airlines or [])}
    ranked: list[FlightOffer] = []
    for offer in offers:
        if offer.stops > max_stops:
            continue
        depart = offer.segments[0].depart_at.isoformat()
        arrive = offer.segments[-1].arrive_at.isoformat()
        window = outbound_window if offer.direction == "outbound" else return_window
        why: list[str] = list(offer.why)
        price = float(offer.price)
        if price > 0:
            score = max(0, 1200 - price) / 20
        else:
            score = 40
            if "schedule only, fare not quoted" not in why:
                why.append("schedule only, fare not quoted")
        score += max(0, 18 - offer.duration_min / 60) * 2
        score += (2 - offer.stops) * 8
        if _fits(window, depart):
            score += 30
            why.append(f"leaves in your {window.replace('_', ' ')} window")
        else:
            why.append(f"outside the {window.replace('_', ' ')} window")
        if offer.carrier.upper() in favourites:
            score += 25
            why.append("your favourite airline")
        red_eye = _hour(depart) in WINDOWS["red_eye"]
        if red_eye and avoid_red_eye:
            score -= 40
            why.append("red-eye, which you asked to avoid")
        if _asleep(arrive, sleep_time, wake_time):
            score -= 20
            why.append("lands while you would be asleep")
        if offer.fare_conditions.refundable:
            why.append("refundable fare")
        ranked.append(offer.model_copy(update={"score": round(score, 2), "why": why}))
    ranked.sort(key=lambda item: item.score, reverse=True)
    kept: list[FlightOffer] = []
    for direction in ("outbound", "return"):
        kept.extend([item for item in ranked if item.direction == direction][:limit])
    return kept


def _load_fixture() -> list[FlightOffer]:
    _LOADS["fixture"] += 1
    payload = json.loads(FIXTURE.read_text())
    return [FlightOffer.model_validate(row) for row in payload]


def _default_provider() -> str:
    named = os.environ.get("FLIGHT_SEARCH_PROVIDER")
    if named:
        return named
    from roam_tools.aviationstack import access_key

    return "aviationstack" if access_key() else "fixture"


def _provider_offers(
    origin_codes: list[str],
    destination_codes: list[str],
    depart_date: str,
    return_date: str | None,
) -> list[FlightOffer]:
    provider = _default_provider()
    if provider == "aviationstack":
        from roam_tools.aviationstack import fetch_schedule_offers

        return fetch_schedule_offers(origin_codes, destination_codes, depart_date, return_date)
    if provider == "duffel":
        if not os.environ.get("DUFFEL_API_KEY"):
            raise RuntimeError("DUFFEL_API_KEY is not set")
        raise RuntimeError("Duffel search is not enabled in this build; set FLIGHT_SEARCH_PROVIDER=fixture or aviationstack")
    if provider != "fixture":
        raise RuntimeError(f"Unknown FLIGHT_SEARCH_PROVIDER {provider}")
    return _load_fixture()


def search_flights(
    origin_codes: list[str],
    destination_codes: list[str],
    depart_date: str,
    return_date: str | None = None,
    outbound_window: str = "any",
    return_window: str = "any",
    cabin: str = "economy",
    max_stops: int = 1,
    travellers: int = 1,
    favourite_airlines: list[str] | None = None,
    avoid_red_eye: bool = False,
    sleep_time: str = "23:00",
    wake_time: str = "07:30",
) -> list[FlightOffer]:
    del cabin, travellers
    key = (
        tuple(origin_codes), tuple(destination_codes), depart_date, return_date,
        outbound_window, return_window, max_stops, tuple(favourite_airlines or []),
        avoid_red_eye, sleep_time, wake_time, _default_provider(),
    )
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < TTL_SEC:
        return cached[1]
    provider = _default_provider()
    cap = int(os.environ.get("FLIGHT_SEARCH_MAX_CALLS", "20"))
    if provider == "fixture" and _LOADS["fixture"] >= cap:
        return []
    catalog = _provider_offers(origin_codes, destination_codes, depart_date, return_date)
    if provider == "aviationstack":
        picked = catalog
    else:
        origins = {code.upper() for code in origin_codes}
        destinations = {code.upper() for code in destination_codes}
        picked = []
        for offer in catalog:
            depart = offer.segments[0]
            arrive = offer.segments[-1]
            depart_code = (depart.from_place.code or "").upper()
            arrive_code = (arrive.to_place.code or "").upper()
            if offer.direction == "outbound":
                if depart_code not in origins or arrive_code not in destinations:
                    continue
            else:
                if depart_code not in destinations or arrive_code not in origins:
                    continue
            depart_day = depart.depart_at.date().isoformat()
            if offer.direction == "outbound" and depart_day != depart_date:
                continue
            if offer.direction == "return" and return_date and depart_day != return_date:
                continue
            picked.append(offer)
    ranked = rank_flights(
        picked,
        outbound_window=outbound_window,
        return_window=return_window,
        favourite_airlines=favourite_airlines,
        avoid_red_eye=avoid_red_eye,
        sleep_time=sleep_time,
        wake_time=wake_time,
        max_stops=max_stops,
    )
    _CACHE[key] = (time.monotonic(), ranked)
    return ranked
