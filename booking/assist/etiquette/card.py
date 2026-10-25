"""Return a fixed etiquette card for one stop.

The master agent calls this on the Amazon Bedrock AgentCore runtime before
a shrine, temple, museum, restaurant, or other stop. This module does not
run that loop. A later integrator wires it into the master.

Sandbox only: Japan, France, and the United States, with fixed phrases.
No network and no translation API. The place name is not looked up. This
is etiquette, not a map, and not medical, legal, or safety advice.
"""

from __future__ import annotations

import json

REASON_NONE = "none"
UNKNOWN_COUNTRY = "unknown_country"

JA_PHOTO = "写真は大丈夫ですか"
JA_PHOTO_MEANING = "May I take a photo?"
JA_RESERVATION = "予約しています"
JA_RESERVATION_MEANING = "I have a reservation."
FR_PHOTO = "Pardon, une photo est-elle permise ?"
FR_PHOTO_MEANING = "Excuse me, are photos allowed?"

JAPAN_WORSHIP_RULES = (
    "shoes off before the hall",
    "bow once at the gate",
    "photography of the inner hall is restricted",
)
JAPAN_RESTAURANT_RULES = (
    "no tipping",
    "shoes off only at a tatami room",
)
FRANCE_MUSEUM_RULES = (
    "quiet inside",
    "shoulders covered",
)

_COUNTRY_NAME = {
    "japan": "Japan",
    "france": "France",
    "united states": "United States",
}

_ALIASES = {
    "japan": "japan",
    "jp": "japan",
    "jpn": "japan",
    "france": "france",
    "fr": "france",
    "fra": "france",
    "united states": "united states",
    "united states of america": "united states",
    "usa": "united states",
    "us": "united states",
}

_KINDS = ("shrine", "temple", "museum", "restaurant", "general")

# Fixed sandbox cards. A church-like stop in France is kind museum.
_CARDS = {
    ("Japan", "shrine"): (JAPAN_WORSHIP_RULES, JA_PHOTO, "ja", JA_PHOTO_MEANING),
    ("Japan", "temple"): (JAPAN_WORSHIP_RULES, JA_PHOTO, "ja", JA_PHOTO_MEANING),
    ("Japan", "restaurant"): (
        JAPAN_RESTAURANT_RULES,
        JA_RESERVATION,
        "ja",
        JA_RESERVATION_MEANING,
    ),
    ("France", "museum"): (FRANCE_MUSEUM_RULES, FR_PHOTO, "fr", FR_PHOTO_MEANING),
}

_ENVELOPE_KEYS = ("country", "placeName", "place_name", "kind")


def etiquette_card(country=None, placeName=None, kind=None) -> dict:
    """Return country, kind, rules, phrase, phraseLanguage, phraseMeaning, and reason.

    Never raises. ``country`` may be the country, or one object with
    ``country``, ``placeName``, and ``kind``. ``placeName`` is accepted and
    not used to choose the card.

    Japan shrine or temple: shoes off before the hall, bow once at the gate,
    photography of the inner hall is restricted, and the photo question.
    Japan restaurant: no tipping, shoes off only at a tatami room, and the
    reservation line. France museum, including a church-like stop passed as
    kind museum: quiet inside, shoulders covered, and the photo question.
    The United States returns empty rules, a null phrase, and reason
    ``none``. Any other country returns empty rules, a null phrase, and
    reason ``unknown_country``.
    """
    try:
        country_text, kind_text = _normalize(country, placeName, kind)
        return _lookup(country_text, kind_text)
    except Exception:
        return _result("", "", (), None, None, None, UNKNOWN_COUNTRY)


def _normalize(country, placeName, kind):
    if isinstance(country, str) and placeName is None and kind is None:
        loaded = _json_object(country)
        if isinstance(loaded, dict):
            country = loaded
        else:
            return _text(country), ""
    if isinstance(country, dict) and placeName is None and kind is None:
        source = _unwrap(country)
        return _text(source.get("country")), _text(source.get("kind"))
    if isinstance(country, dict):
        country = _text(country.get("country"))
    return _text(country), _text(kind)


def _lookup(country_text: str, kind_text: str) -> dict:
    canonical = _COUNTRY_NAME.get(_ALIASES.get(_country_key(country_text), ""))
    kind = _kind(kind_text)
    if canonical is None:
        return _result(country_text, kind, (), None, None, None, UNKNOWN_COUNTRY)
    card = _CARDS.get((canonical, kind))
    if card is None:
        return _result(canonical, kind, (), None, None, None, REASON_NONE)
    rules, phrase, language, meaning = card
    return _result(canonical, kind, rules, phrase, language, meaning, REASON_NONE)


def _result(country, kind, rules, phrase, language, meaning, reason: str) -> dict:
    return {
        "country": country,
        "kind": kind,
        "rules": list(rules),
        "phrase": phrase,
        "phraseLanguage": language,
        "phraseMeaning": meaning,
        "reason": reason,
    }


def _unwrap(source: dict) -> dict:
    arguments = source.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = source.get("input")
    if isinstance(nested, dict) and not any(key in source for key in _ENVELOPE_KEYS):
        return nested
    return source


def _country_key(value: str) -> str:
    text = value.strip().casefold().replace(".", "")
    return " ".join(text.split())


def _kind(value: str) -> str:
    text = " ".join(value.strip().casefold().split())
    if text in _KINDS:
        return text
    return ""


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _json_object(value: str):
    stripped = value.strip()
    if not stripped.startswith("{"):
        return None
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None
