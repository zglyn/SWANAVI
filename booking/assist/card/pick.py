"""Pick a sandbox Mastercard for a merchant charge.

Cards in the input are fake fixtures. This module does not read a real card,
charge a card, open the network, or call AWS. It does not run the master
loop. A later integrator wires ``pick_card`` into the master.

Prefer a Mastercard whose ``noFxCountries`` includes the merchant country.
That pick returns ``fxFeePercent`` 0, ``feeAmount`` 0, and reason
``no_fx_fee``. Otherwise pick the Mastercard with the lowest
``fxFeePercent`` and reason ``lowest_fee``. ``feeAmount`` is
``amount * fxFeePercent / 100``. ``payAmount`` is ``amount + feeAmount``.
Money is rounded half up to 2 decimal places, and to 0 decimal places when
the currency is JPY.

Japan and JP are the same country, as are France and FR, and US with itself.
Visa and Amex are never selected. When no Mastercard is present the result
is needs_user: ``status`` is ``needs_user``, ``cardId`` is null, and
``reason`` is ``no_mastercard``. A negative amount returns reason
``invalid_amount`` and ``feeAmount`` 0. Never raises.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CALL_KEYS = (
    "merchantCountry",
    "merchant_country",
    "amount",
    "currency",
    "cards",
)
_CENTS = Decimal("0.01")
_YEN = Decimal("1")

# ISO-ish names and codes the sandbox accepts. Japan/JP, France/FR, and US
# each collapse to one key so either spelling matches noFxCountries.
_COUNTRIES = {
    "japan": "jp",
    "jp": "jp",
    "jpn": "jp",
    "france": "fr",
    "fr": "fr",
    "fra": "fr",
    "us": "us",
    "usa": "us",
    "united states": "us",
    "united states of america": "us",
}

REASON_NO_FX = "no_fx_fee"
REASON_LOWEST = "lowest_fee"
REASON_NO_MC = "no_mastercard"
REASON_INVALID = "invalid_amount"
STATUS_NEEDS_USER = "needs_user"
NETWORK_MASTERCARD = "mastercard"


def pick_card(merchantCountry=None, amount=None, currency=None, cards=None) -> dict:
    """Pick a fixture Mastercard. Never raises.

    Input is ``{merchantCountry, amount, currency, cards}``. Each card is
    ``{id, network, fxFeePercent, noFxCountries}``. A partial payload, bad
    JSON, and any other input return a result and do not raise.
    """
    try:
        data = _payload(merchantCountry, amount, currency, cards)
        if not isinstance(data, dict):
            return _invalid("")
        return _decide(data)
    except Exception:
        return _invalid("")


def _payload(merchantCountry, amount, currency, cards):
    if isinstance(merchantCountry, dict) and amount is None and currency is None and cards is None:
        return _unwrap(merchantCountry)
    if isinstance(merchantCountry, str) and amount is None and currency is None and cards is None:
        stripped = merchantCountry.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return _load(stripped)
        return {
            "merchantCountry": merchantCountry,
            "amount": None,
            "currency": None,
            "cards": None,
        }
    single_value = amount is None and currency is None and cards is None
    if merchantCountry is not None and single_value and not isinstance(merchantCountry, (str, dict)):
        return None
    return {
        "merchantCountry": merchantCountry,
        "amount": amount,
        "currency": currency,
        "cards": cards,
    }


def _decide(data: dict) -> dict:
    currency = _text(_first(data, "currency"))
    if "amount" not in data or _blank(data.get("amount")):
        return _invalid(currency)
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return _invalid(currency)
    country = _country(_first(data, "merchantCountry", "merchant_country"))
    chosen, percent, reason = _choose(_card_list(data.get("cards")), country)
    if chosen is None:
        _fee, pay = _charges(amount, Decimal(0), currency)
        result = _result(None, None, 0, pay, currency, REASON_NO_MC)
        result["status"] = STATUS_NEEDS_USER
        return result
    fee, pay = _charges(amount, percent, currency)
    return _result(_card_id(chosen), _number(percent), fee, pay, currency, reason)


def _choose(cards: list, country: str):
    mastercards = [card for card in cards if _is_mastercard(card) and _card_id(card) is not None]
    if country:
        for card in mastercards:
            if _covers(card, country):
                return card, Decimal(0), REASON_NO_FX
    best = None
    best_percent = None
    for card in mastercards:
        percent = _parse_percent(_first(card, "fxFeePercent", "fx_fee_percent"))
        if percent is None:
            continue
        if best_percent is None or percent < best_percent:
            best = card
            best_percent = percent
    if best is None:
        return None, None, REASON_NO_MC
    return best, best_percent, REASON_LOWEST


def _covers(card: dict, country: str) -> bool:
    raw = _first(card, "noFxCountries", "no_fx_countries")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return False
    for item in raw:
        if _country(item) == country:
            return True
    return False


def _is_mastercard(card: dict) -> bool:
    network = card.get("network")
    if not isinstance(network, str):
        return False
    compact = "".join(ch for ch in network.casefold() if ch.isalnum())
    return compact == NETWORK_MASTERCARD


def _card_list(value) -> list:
    if isinstance(value, (list, tuple)) and not isinstance(value, str):
        return [item for item in value if isinstance(item, dict)]
    return []


def _card_id(card: dict):
    value = card.get("id")
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _charges(amount: Decimal, percent: Decimal, currency: str):
    quantum = _YEN if currency.strip().upper() == "JPY" else _CENTS
    fee = (amount * percent / Decimal(100)).quantize(quantum, rounding=ROUND_HALF_UP)
    pay = (amount + fee).quantize(quantum, rounding=ROUND_HALF_UP)
    return _number(fee), _number(pay)


def _result(card_id, percent, fee, pay, currency: str, reason: str) -> dict:
    return {
        "cardId": card_id,
        "fxFeePercent": percent,
        "feeAmount": fee,
        "payAmount": pay,
        "currency": currency,
        "reason": reason,
    }


def _invalid(currency: str) -> dict:
    return _result(None, None, 0, 0, currency, REASON_INVALID)


def _parse_amount(value):
    number = _decimal(value)
    if number is None or number < 0:
        return None
    return number


def _parse_percent(value):
    number = _decimal(value)
    if number is None or number < 0:
        return None
    return number


def _decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, Decimal):
            number = value
        elif isinstance(value, int):
            number = Decimal(value)
        elif isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                return None
            number = Decimal(str(value))
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            number = Decimal(text)
        else:
            return None
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def _country(value) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().casefold().replace(".", "").split())
    if not text:
        return ""
    return _COUNTRIES.get(text, text)


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


def _first(data: dict, *keys):
    for key in keys:
        if key in data:
            return data[key]
    return None


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _number(amount: Decimal):
    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)
