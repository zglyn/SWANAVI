"""Authorize a capture up to the amount the traveler already approved.

Sandbox only. This is a limit check the master agent calls before a charge.
It does not charge a card, submit a ledger transaction, or call AWS.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

_CALL_KEYS = ("segmentId", "currency", "authorizedAmount", "requestedAmount", "reason")


def authorize_spend(
    segmentId=None,
    currency=None,
    authorizedAmount=None,
    requestedAmount=None,
    reason=None,
) -> dict:
    """Pay the requested amount when it is within the authorization.

    When ``requestedAmount`` is greater than ``authorizedAmount``, pay only
    ``authorizedAmount`` and set ``reason`` to ``over_capture_rejected``.
    The traveler is not asked to dispute the extra. A negative or missing
    amount rejects with ``payAmount`` 0. Never raises.
    """
    try:
        bare_payload = (
            _is_payload(segmentId)
            and currency is None
            and authorizedAmount is None
            and requestedAmount is None
            and reason is None
        )
        if bare_payload:
            data = _load(segmentId)
        else:
            data = {
                "segmentId": segmentId,
                "currency": currency,
                "authorizedAmount": authorizedAmount,
                "requestedAmount": requestedAmount,
                "reason": reason,
            }
        if not isinstance(data, dict):
            return _reject("", "", "invalid_amount")
        return _decide(data)
    except Exception:
        return _reject("", "", "invalid_amount")


def _decide(data: dict) -> dict:
    segment_id = _text(data.get("segmentId"))
    currency = _text(data.get("currency"))
    authorized = _amount(data.get("authorizedAmount"))
    requested = _amount(data.get("requestedAmount"))
    if authorized is None or requested is None:
        return _reject(segment_id, currency, "invalid_amount")
    if requested.number > authorized.number:
        return _result(segment_id, "pay", authorized.value, currency, "over_capture_rejected")
    return _result(segment_id, "pay", requested.value, currency, _text(data.get("reason")))


def _reject(segment_id: str, currency: str, reason: str) -> dict:
    return _result(segment_id, "reject", 0, currency, reason)


def _result(segment_id: str, decision: str, pay_amount, currency: str, reason: str) -> dict:
    return {
        "segmentId": segment_id,
        "decision": decision,
        "payAmount": pay_amount,
        "currency": currency,
        "reason": reason,
    }


class _Parsed:
    def __init__(self, number: Decimal, value) -> None:
        self.number = number
        self.value = value


def _amount(value) -> _Parsed | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        number = Decimal(value)
        parsed: int | float | str = value
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        number = Decimal(str(value))
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = Decimal(text)
        except InvalidOperation:
            return None
        parsed = text
    else:
        return None
    if not number.is_finite() or number < 0:
        return None
    return _Parsed(number, parsed)


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


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
