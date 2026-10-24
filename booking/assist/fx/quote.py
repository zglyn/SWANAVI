"""Quote a vendor charge into the trip currency.

Sandbox rates are how many USD one unit of that currency buys: USD 1, EUR 1.08,
GBP 1.27, JPY 0.0067. A quote into another trip currency crosses those USD
rates. The quoted amount is rounded to 2 decimal places. The same currency
returns rate 1 and that amount. An unknown currency returns a null amount and
reason ``unknown_currency``. This module does not open the network, submit an
XRPL transaction, or call AWS. It never raises.
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

SOURCE = "sandbox"
REASON_QUOTED = "quoted"
REASON_SAME = "same_currency"
REASON_UNKNOWN = "unknown_currency"
REASON_INVALID = "invalid_amount"

_CALL_KEYS = ("amount", "fromCurrency", "toCurrency")
_CENTS = Decimal("0.01")


def quote_fx(amount=None, fromCurrency=None, toCurrency=None) -> dict:
    """Quote ``amount`` of ``fromCurrency`` into ``toCurrency``.

    A dict or JSON object may be passed as ``amount`` when the other arguments
    are omitted. The return value always has ``amount``, ``currency``, ``rate``,
    ``source`` (``sandbox``), and ``reason``. Never raises.
    """
    try:
        bare_payload = _is_payload(amount) and fromCurrency is None and toCurrency is None
        if bare_payload:
            data = _load(amount)
        else:
            data = {
                "amount": amount,
                "fromCurrency": fromCurrency,
                "toCurrency": toCurrency,
            }
        if not isinstance(data, dict):
            return _result(None, "", None, REASON_INVALID)
        return _quote(data)
    except Exception:
        return _result(None, "", None, REASON_INVALID)


def _quote(data: dict) -> dict:
    to_code = _code(data.get("toCurrency"))
    from_code = _code(data.get("fromCurrency"))
    parsed = _parse_amount(data.get("amount"))
    if parsed is None:
        return _result(None, to_code, None, REASON_INVALID)
    if not from_code or not to_code:
        return _result(None, to_code, None, REASON_UNKNOWN)
    if from_code == to_code:
        return _result(_money(parsed), to_code, 1, REASON_SAME)
    from_rate = RATES_INTO_USD.get(from_code)
    to_rate = RATES_INTO_USD.get(to_code)
    if from_rate is None or to_rate is None:
        return _result(None, to_code, None, REASON_UNKNOWN)
    rate = from_rate / to_rate
    return _result(_money(parsed * rate), to_code, _number(rate), REASON_QUOTED)


def _result(amount, currency: str, rate, reason: str) -> dict:
    return {
        "amount": amount,
        "currency": currency,
        "rate": rate,
        "source": SOURCE,
        "reason": reason,
    }


def _money(value: Decimal):
    quantized = value.quantize(_CENTS, rounding=ROUND_HALF_UP)
    return _number(quantized)


def _number(value: Decimal):
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _parse_amount(value):
    if isinstance(value, bool) or value is None:
        return None
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
        try:
            amount = Decimal(text)
        except InvalidOperation:
            return None
    else:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def _code(value) -> str:
    if isinstance(value, str):
        return value.strip().upper()
    return ""


def _is_payload(value) -> bool:
    return isinstance(value, (dict, str))


def _load(payload):
    if isinstance(payload, str):
        loaded = json.loads(payload)
        if not isinstance(loaded, dict):
            return None
        payload = loaded
    if not isinstance(payload, dict):
        return None
    return _unwrap(payload)


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _CALL_KEYS):
        return nested
    return payload
