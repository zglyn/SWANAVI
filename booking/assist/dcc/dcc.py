"""Refuse a terminal dynamic currency conversion offer.

Tourist rule: pay the merchant's currency. When ``offeredCurrency`` differs
from ``merchantCurrency``, the offer is refused and the merchant amount is
what would be paid. ``offeredAmount`` is not converted and is not the amount
paid. JPY is rounded to 0 decimal places. Every other currency is rounded to
2 decimal places.

Sandbox only. This module does not charge a card, call a payment terminal,
open the network, or call AWS. It never raises.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

REASON_LOCAL = "local_currency"
REASON_REFUSED = "dcc_refused"
REASON_INVALID = "invalid_amount"

_CALL_KEYS = ("merchantAmount", "merchantCurrency", "offeredAmount", "offeredCurrency")
_CENTS = Decimal("0.01")
_WHOLE = Decimal("1")
_ZERO_DECIMAL = "JPY"


def refuse_dcc(
    merchantAmount=None,
    merchantCurrency=None,
    offeredAmount=None,
    offeredCurrency=None,
) -> dict:
    """Decide whether to refuse a terminal currency offer.

    A dict or JSON object may be passed as ``merchantAmount`` when the other
    arguments are omitted. The return value always has ``payAmount``,
    ``payCurrency``, ``refused``, and ``reason``.

    The same currency, compared without case, is ``local_currency`` and
    ``refused`` is false. A different currency is ``dcc_refused`` and
    ``refused`` is true. Both results pay ``merchantAmount`` in
    ``merchantCurrency``. A bad or negative amount pays ``0``, ``refused``
    is true, and ``reason`` is ``invalid_amount``. Never raises.
    """
    try:
        bare_payload = (
            _is_payload(merchantAmount)
            and merchantCurrency is None
            and offeredAmount is None
            and offeredCurrency is None
        )
        if bare_payload:
            data = _load(merchantAmount)
        else:
            data = {
                "merchantAmount": merchantAmount,
                "merchantCurrency": merchantCurrency,
                "offeredAmount": offeredAmount,
                "offeredCurrency": offeredCurrency,
            }
        if not isinstance(data, dict):
            return _invalid("")
        return _decide(data)
    except Exception:
        return _invalid("")


def _decide(data: dict) -> dict:
    pay_currency, merchant_code = _currency(data.get("merchantCurrency"))
    merchant = _parse_amount(data.get("merchantAmount"))
    # The offered amount must be a usable number. It is not converted and not paid.
    if merchant is None or _parse_amount(data.get("offeredAmount")) is None:
        return _invalid(pay_currency)
    pay_amount = _money(merchant, merchant_code)
    offered_code = _currency(data.get("offeredCurrency"))[1]
    if merchant_code == offered_code:
        return _result(pay_amount, pay_currency, False, REASON_LOCAL)
    return _result(pay_amount, pay_currency, True, REASON_REFUSED)


def _invalid(pay_currency: str) -> dict:
    return _result(0, pay_currency, True, REASON_INVALID)


def _result(pay_amount, pay_currency: str, refused: bool, reason: str) -> dict:
    return {
        "payAmount": pay_amount,
        "payCurrency": pay_currency,
        "refused": refused,
        "reason": reason,
    }


def _money(amount: Decimal, currency_code: str):
    quantum = _WHOLE if currency_code == _ZERO_DECIMAL else _CENTS
    quantized = amount.quantize(quantum, rounding=ROUND_HALF_UP)
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


def _currency(value) -> tuple[str, str]:
    if isinstance(value, str):
        display = value.strip()
        return display, display.upper()
    return "", ""


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
