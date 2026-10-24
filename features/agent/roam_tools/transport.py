from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import BaseModel

DATA = Path(__file__).parent / "data" / "transport"


class ModeInfo(BaseModel):
    mode: str
    typical_speed_kmh: float
    typical_cost: str
    best_for: str
    notes: str


class TransferOption(BaseModel):
    mode: str
    name: str
    minutes: int
    cost: str
    frequency: str
    notes: str


class Transfer(BaseModel):
    from_code: str
    to_area: str
    options: list[TransferOption]


class TransportProfile(BaseModel):
    place: str
    modes: list[ModeInfo]
    passes: list[str]
    transfers: list[Transfer]
    tips: list[str]
    source: str


def normalize_place(place: str) -> str:
    text = place.lower()
    for name in ("kyoto", "osaka", "tokyo"):
        if name in text:
            return name
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _load(key: str) -> TransportProfile | None:
    path = DATA / f"{key}.json"
    if not path.exists():
        return None
    return TransportProfile.model_validate(json.loads(path.read_text()))


def _unverified(place: str) -> TransportProfile:
    return TransportProfile(
        place=place,
        modes=[
            ModeInfo(mode="walk", typical_speed_kmh=4.5, typical_cost="0", best_for="short hops", notes="Generic city speed."),
            ModeInfo(mode="transit", typical_speed_kmh=18, typical_cost="varies", best_for="across town", notes="Unverified."),
            ModeInfo(mode="taxi", typical_speed_kmh=22, typical_cost="meter", best_for="luggage", notes="Unverified."),
        ],
        passes=[],
        transfers=[],
        tips=[f"No curated guide for {place}. This profile was not checked by a model."],
        source="llm",
    )


def _from_model(place: str) -> TransportProfile | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=os.environ.get("ROAM_ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": (
                "Return JSON only for a TransportProfile with keys place, modes, passes, transfers, tips, source. "
                "source must be llm. modes items have mode, typical_speed_kmh, typical_cost, best_for, notes. "
                f"Describe how people get around {place}, including airport transfers."
            ),
        }],
    )
    text = message.content[0].text
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start : end + 1])
    data["source"] = "llm"
    return TransportProfile.model_validate(data)


def get_transport_profile(place: str) -> TransportProfile:
    curated = _load(normalize_place(place))
    if curated is not None:
        return curated
    modeled = _from_model(place)
    if modeled is not None:
        return modeled
    return _unverified(place)


def arrival_transfer_minutes(profile: TransportProfile, from_code: str | None) -> int:
    if not from_code:
        return 45
    for transfer in profile.transfers:
        if transfer.from_code.upper() == from_code.upper() and transfer.options:
            return min(option.minutes for option in transfer.options)
    return 45
