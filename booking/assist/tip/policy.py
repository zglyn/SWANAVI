"""Country tip ceiling for a sandbox charge.

The master agent calls ``tip_policy`` on the Amazon Bedrock AgentCore runtime
before ``authorize_spend``. ``authorizedAmount`` is the ceiling the spend
guard must use, so a vendor cannot add a tip past the country rule.

Sandbox only. This module does not charge a card, run the master loop, open
the network, or call AWS.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CALL_KEYS = ("country", "subtotal", "currency")
_CENTS = Decimal("0.01")

# Sandbox percents. Spellings are the country name plus the short forms of
# United States used by callers. Anything else is 10.
_PERCENTS = {
    "japan": 0,
    "united states": 20,
    "united states of america": 20,
    "us": 20,
    "usa": 20,
    "france": 0,
}
_DEFAULT_PERCENT = 10

REASON_COUNTRY = "country_rule"
REASON_MISSING = "missing_subtotal"
REASON_INVALID = "invalid_subtotal"


def tip_policy(country=None, subtotal=None, currency=None) -> dict:
    """Return the country tip ceiling. Never raises.

    Input is ``{country, subtotal, currency}``. ``maxTipPercent`` is the
    sandbox percent for that country. ``tipAmount`` is
    ``subtotal * maxTipPercent / 100``, rounded to 2 decimals.
    ``authorizedAmount`` is ``subtotal + tipAmount``, rounded to 2 decimals.
    A missing subtotal returns ``tipAmount`` null and ``reason``
    ``missing_subtotal``.
    """
    try:
        data = _payload(country, subtotal, currency)
        if not isinstance(data, dict):
            return _missing("", _DEFAULT_PERCENT)
        return _decide(data)
    except Exception:
        return _missing("", _DEFAULT_PERCENT)


def _payload(country, subtotal, currency):
    if isinstance(country, dict) and subtotal is None and currency is None:
        return _unwrap(country)
    if isinstance(country, str) and subtotal is None and currency is None:
        stripped = country.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return _load(stripped)
        return {"country": country, "subtotal": None, "currency": None}
    single_value = subtotal is None and currency is None
    if country is not None and single_value and not isinstance(country, (str, dict)):
        return None
    return {"country": country, "subtotal": subtotal, "currency": currency}


def _decide(data: dict) -> dict:
    country = _text(data.get("country"))
    currency = _text(data.get("currency"))
    percent = _percent(country)
    if "subtotal" not in data or _blank(data.get("subtotal")):
        return _missing(currency, percent)
    amount = _parse_subtotal(data.get("subtotal"))
    if amount is None:
        return _result(percent, None, None, currency, REASON_INVALID)
    tip = (amount * Decimal(percent) / Decimal(100)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    authorized = (amount + tip).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return _result(percent, _number(tip), _number(authorized), currency, REASON_COUNTRY)


def _missing(currency: str, percent: int) -> dict:
    return _result(percent, None, None, currency, REASON_MISSING)


def _result(percent: int, tip, authorized, currency: str, reason: str) -> dict:
    return {
        "maxTipPercent": percent,
        "tipAmount": tip,
        "authorizedAmount": authorized,
        "currency": currency,
        "reason": reason,
    }


def _percent(country: str) -> int:
    key = " ".join(country.casefold().replace(".", "").split())
    return _PERCENTS.get(key, _DEFAULT_PERCENT)


def _parse_subtotal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, Decimal):
            amount = value
        elif isinstance(value, int):
            amount = Decimal(value)
        elif isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                return None
            amount = Decimal(str(value))
        elif isinstance(value, str):
            amount = Decimal(value.strip())
        else:
            return None
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _load(payload: str):
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        return None
    return _unwrap(loaded)


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _CALL_KEYS):
        return nested
    return payload


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _number(amount: Decimal):
    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)
