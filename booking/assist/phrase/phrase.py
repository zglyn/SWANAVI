"""Build a driver card the traveler can show when a ride is requested.

Sandbox only: no translation API, no network, and no AWS. The master agent
calls this on the Amazon Bedrock AgentCore runtime when it requests a ride.
This module does not run that loop. Place, address, and arrival are copied
as given.
"""

from __future__ import annotations

import json

JA_PREFIX = "こちらまでお願いします"
FR_PREFIX = "À cette adresse, s'il vous plaît"

_PREFIX = {
    "ja": JA_PREFIX,
    "fr": FR_PREFIX,
}

_FIELD_KEYS = ("language", "placeName", "place_name", "address", "arriveAt", "arrive_at")


def phrase_card(language=None, placeName=None, address=None, arriveAt=None) -> dict:
    """Return ``language`` and ``card``. Never raises.

    ``language`` may be the language code, or one object with ``language``,
    ``placeName``, ``address``, and ``arriveAt``. ``card`` is three lines:
    place, address, and arrival. ``ja`` and ``fr`` put a fixed phrase on the
    first line. A missing place name returns an empty card.
    """
    try:
        code, place, street, arrival = _normalize(language, placeName, address, arriveAt)
        return _compose(code, place, street, arrival)
    except Exception:
        return {"language": "", "card": ""}


def _normalize(language, placeName, address, arriveAt):
    if isinstance(language, str) and placeName is None and address is None and arriveAt is None:
        loaded = _json_object(language)
        if isinstance(loaded, dict):
            language = loaded
        else:
            return _line(language), "", "", ""
    if isinstance(language, dict) and placeName is None and address is None and arriveAt is None:
        source = _unwrap(language)
        return (
            _line(source.get("language")),
            _line(source.get("placeName", source.get("place_name"))),
            _line(source.get("address")),
            _line(source.get("arriveAt", source.get("arrive_at"))),
        )
    return _line(language), _line(placeName), _line(address), _line(arriveAt)


def _compose(language: str, place: str, street: str, arrival: str) -> dict:
    if not place:
        return {"language": language, "card": ""}
    lines = [place, street, arrival]
    prefix = _PREFIX.get(language)
    if prefix:
        lines.insert(0, prefix)
    return {"language": language, "card": "\n".join(lines)}


def _unwrap(source: dict) -> dict:
    arguments = source.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = source.get("input")
    if isinstance(nested, dict) and not any(key in source for key in _FIELD_KEYS):
        return nested
    return source


def _json_object(text: str):
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return loaded
    return None


def _line(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
