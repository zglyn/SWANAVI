"""Return sandbox emergency and embassy phone numbers for one country.

The master agent calls this when the traveler asks for help. The result is
phone numbers only. This module does not give medical advice, doses, or
treatment steps, and it does not run the master loop.

Sandbox only: a fixed directory for Japan, France, and the United States.
No network and no AWS.
"""

from __future__ import annotations

import json

UNKNOWN_COUNTRY = "unknown_country"
FALLBACK_EMERGENCY_NUMBER = "112"

# Sandbox directory. These are the only numbers this tool returns.
DIRECTORY = {
    "japan": {
        "country": "Japan",
        "emergencyNumber": "110",
        "embassyPhone": "+81-3-3224-5000",
    },
    "france": {
        "country": "France",
        "emergencyNumber": "112",
        "embassyPhone": "+33-1-4312-2222",
    },
    "united states": {
        "country": "United States",
        "emergencyNumber": "911",
        "embassyPhone": "+1-202-555-0100",
    },
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

_ENVELOPE_KEYS = ("country", "travelerName", "traveler_name")


def emergency_card(country=None, travelerName=None) -> dict:
    """Return country, emergencyNumber, embassyPhone, and note. Never raises.

    ``country`` may be the country, or one object with ``country`` and
    ``travelerName``. A country outside the sandbox directory returns
    emergency number 112, a null embassy phone, and a note that includes
    ``unknown_country``. The note includes ``travelerName`` when one was sent.
    Phone numbers only.
    """
    try:
        country_text, traveler_name = _normalize(country, travelerName)
        return _lookup(country_text, traveler_name)
    except Exception:
        return _unknown("", "")


def _normalize(country, travelerName):
    if isinstance(country, str) and travelerName is None:
        loaded = _json_object(country)
        if isinstance(loaded, dict):
            country = loaded
        else:
            return _text(country), ""
    if isinstance(country, dict) and travelerName is None:
        source = country
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        return (
            _text(source.get("country")),
            _text(source.get("travelerName", source.get("traveler_name"))),
        )
    return _text(country), _text(travelerName)


def _lookup(country_text: str, traveler_name: str) -> dict:
    entry = DIRECTORY.get(_ALIASES.get(_country_key(country_text), ""))
    if entry is None:
        return _unknown(country_text, traveler_name)
    return {
        "country": entry["country"],
        "emergencyNumber": entry["emergencyNumber"],
        "embassyPhone": entry["embassyPhone"],
        "note": _note(traveler_name, known=True),
    }


def _unknown(country_text: str, traveler_name: str) -> dict:
    return {
        "country": country_text,
        "emergencyNumber": FALLBACK_EMERGENCY_NUMBER,
        "embassyPhone": None,
        "note": _note(traveler_name, known=False),
    }


def _note(traveler_name: str, known: bool) -> str:
    if known:
        if traveler_name:
            return f"Emergency and embassy phone numbers for {traveler_name}. Phone numbers only."
        return "Emergency and embassy phone numbers. Phone numbers only."
    if traveler_name:
        return f"{UNKNOWN_COUNTRY} for {traveler_name}. Phone numbers only."
    return UNKNOWN_COUNTRY


def _country_key(value: str) -> str:
    text = value.strip().casefold().replace(".", "")
    return " ".join(text.split())


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
