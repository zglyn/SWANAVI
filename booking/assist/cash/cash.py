"""Decide whether a merchant needs cash, and quote that cash into the trip currency.

Sandbox rates are how many USD one unit of that currency buys: USD 1, EUR 1.08,
GBP 1.27, JPY 0.0067. The numbers match the fx quote table. This module copies
them and does not import that package. A quote into another trip currency
crosses those USD rates. USD, EUR, and GBP amounts round half up to 2 decimal
places. JPY amounts round half up to 0 decimal places.

A merchant that accepts a card needs no cash. A merchant that does not is a
cash withdrawal in the merchant currency, quoted into the trip currency. An
unknown currency returns a null trip amount and reason ``unknown_currency``.
A negative amount returns reason ``invalid_amount`` and cash amount 0.

This module does not open the network, call an ATM, or call AWS. It never raises.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RATES_INTO_USD = {
    "USD": Decimal("1"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "JPY": Decimal("0.0067"),
}

ACTION_CARD = "pay_card"
ACTION_CASH = "withdraw_cash"
REASON_CARD = "card_accepted"
REASON_QUOTED = "quoted"
REASON_UNKNOWN = "unknown_currency"
REASON_INVALID = "invalid_amount"
DEFAULT_TRIP_CURRENCY = "USD"

_ENVELOPE_KEYS = ("merchant", "tripCurrency", "trip_currency")
_CENTS = Decimal("0.01")
_YEN = Decimal("1")


def cash_needed(merchant=None, tripCurrency=None) -> dict:
    """Return the cash decision for one merchant. Never raises.

    ``merchant`` is ``{name, acceptsCard, amount, currency}``, or one object
    that holds ``merchant`` and ``tripCurrency``. ``tripCurrency`` defaults
    to USD. When ``acceptsCard`` is true the action is ``pay_card`` and both
    amounts are 0. Otherwise the action is ``withdraw_cash``: ``cashAmount``
    is the merchant amount in the merchant currency, and ``tripAmount`` is
    that cash quoted into ``tripCurrency``.
    """
    try:
        data = _bind(merchant, tripCurrency)
        if not isinstance(data, dict):
            return _result("", "", 0, "", None, DEFAULT_TRIP_CURRENCY, REASON_INVALID)
        return _decide(data)
    except Exception:
        return _result("", "", 0, "", None, DEFAULT_TRIP_CURRENCY, REASON_INVALID)


def _bind(merchant, tripCurrency):
    if isinstance(merchant, str):
        merchant = _load_json(merchant)
    if not isinstance(merchant, dict):
        return None
    source = _unwrap(merchant)
    nested = source.get("merchant")
    if isinstance(nested, dict):
        trip = tripCurrency
        if trip is None:
            trip = _field(source, "tripCurrency", "trip_currency")
        if trip is None:
            trip = DEFAULT_TRIP_CURRENCY
        return {"merchant": nested, "tripCurrency": trip}
    trip = DEFAULT_TRIP_CURRENCY if tripCurrency is None else tripCurrency
    return {"merchant": source, "tripCurrency": trip}


def _decide(data: dict) -> dict:
    merchant = data.get("merchant")
    if not isinstance(merchant, dict):
        merchant = {}
    name = _name(merchant.get("name"))
    cash_currency = _code(merchant.get("currency"))
    trip_currency = _code(_field(data, "tripCurrency", "trip_currency")) or DEFAULT_TRIP_CURRENCY
    parsed = _parse_amount(merchant.get("amount")) if "amount" in merchant else None
    if parsed is None or parsed < 0:
        return _result(name, "", 0, cash_currency, None, trip_currency, REASON_INVALID)
    if _accepts_card(merchant.get("acceptsCard")):
        return _result(name, ACTION_CARD, 0, cash_currency, 0, trip_currency, REASON_CARD)
    if cash_currency not in RATES_INTO_USD or trip_currency not in RATES_INTO_USD:
        cash_amount = (
            _money(parsed, cash_currency)
            if cash_currency in RATES_INTO_USD
            else _number(parsed)
        )
        return _result(name, ACTION_CASH, cash_amount, cash_currency, None, trip_currency, REASON_UNKNOWN)
    cash_quantized = _quantize(parsed, cash_currency)
    trip_value = cash_quantized * RATES_INTO_USD[cash_currency] / RATES_INTO_USD[trip_currency]
    return _result(
        name,
        ACTION_CASH,
        _number(cash_quantized),
        cash_currency,
        _money(trip_value, trip_currency),
        trip_currency,
        REASON_QUOTED,
    )


def _result(merchant, action, cash_amount, cash_currency, trip_amount, trip_currency, reason) -> dict:
    return {
        "merchant": merchant,
        "action": action,
        "cashAmount": cash_amount,
        "cashCurrency": cash_currency,
        "tripAmount": trip_amount,
        "tripCurrency": trip_currency,
        "reason": reason,
    }


def _quantize(value: Decimal, currency: str) -> Decimal:
    unit = _YEN if currency == "JPY" else _CENTS
    return value.quantize(unit, rounding=ROUND_HALF_UP)


def _money(value: Decimal, currency: str):
    return _number(_quantize(value, currency))


def _number(value: Decimal):
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _parse_amount(value):
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
            text = value.strip()
            if not text:
                return None
            amount = Decimal(text)
        else:
            return None
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount


def _accepts_card(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() == "true"
    return False


def _code(value) -> str:
    if isinstance(value, str):
        return value.strip().upper()
    return ""


def _name(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _field(data: dict, *keys):
    for key in keys:
        if key in data:
            return data[key]
    return None


def _load_json(payload: str):
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        return None
    return _unwrap(loaded)


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _ENVELOPE_KEYS):
        return nested
    return payload
