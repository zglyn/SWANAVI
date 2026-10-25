"""Record a sandbox refund after a booking is cancelled.

Sandbox only: no network, no card charge, and no AWS. This module does not
run the master loop and does not replan the day. The master calls
``refund_booking`` after ``replan_cancel``. A partial input returns a result
and does not raise.
"""

from __future__ import annotations

import hashlib
import json
import math

REASON_BAD_EVENT = "event is not cancelled"
REASON_NO_CODE = "confirmation code is missing"
REASON_NOT_SANDBOX = "confirmation code is not a sandbox code"
REASON_NO_AMOUNT = "amount is missing"
REASON_BAD_AMOUNT = "amount is not a refundable amount"
REASON_UNREADABLE = "refund_booking could not read the input"

_ENVELOPE_KEYS = ("segmentId", "segment_id", "confirmationCode", "confirmation_code", "amount", "currency", "event")


def refund_booking(
    segmentId=None,
    confirmationCode=None,
    amount=None,
    currency=None,
    event=None,
) -> dict:
    """Refund one cancelled sandbox booking, or return a failed result.

    ``segmentId`` may be the id, or one object with ``segmentId``,
    ``confirmationCode``, ``amount``, ``currency``, and ``event``. Never raises.
    """
    try:
        segment_id, confirmation_code, amount, currency, event = _normalize(
            segmentId, confirmationCode, amount, currency, event
        )
        return _refund(segment_id, confirmation_code, amount, currency, event)
    except Exception:
        return _result("", "failed", None, None, None, REASON_UNREADABLE)


def _normalize(segmentId, confirmationCode, amount, currency, event):
    if (
        isinstance(segmentId, str)
        and confirmationCode is None
        and amount is None
        and currency is None
        and event is None
    ):
        try:
            loaded = json.loads(segmentId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            segmentId = loaded
    if (
        isinstance(segmentId, dict)
        and confirmationCode is None
        and amount is None
        and currency is None
        and event is None
    ):
        source = segmentId
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        if isinstance(source, dict):
            return (
                source.get("segmentId", source.get("segment_id")),
                source.get("confirmationCode", source.get("confirmation_code")),
                source.get("amount"),
                source.get("currency"),
                source.get("event"),
            )
    return segmentId, confirmationCode, amount, currency, event


def _refund(segment_id, confirmation_code, amount, currency, event) -> dict:
    echoed_id = segment_id.strip() if isinstance(segment_id, str) else ""
    echoed_amount = _echo_amount(amount)
    echoed_currency = _echo_currency(currency)

    if not isinstance(event, str) or event.strip() != "cancelled":
        return _result(echoed_id, "failed", None, echoed_amount, echoed_currency, REASON_BAD_EVENT)

    code = confirmation_code.strip() if isinstance(confirmation_code, str) else ""
    if not code:
        return _result(echoed_id, "failed", None, echoed_amount, echoed_currency, REASON_NO_CODE)
    if not code.startswith("SANDBOX-"):
        return _result(echoed_id, "failed", None, echoed_amount, echoed_currency, REASON_NOT_SANDBOX)

    if _amount_missing(amount):
        return _result(echoed_id, "failed", None, echoed_amount, echoed_currency, REASON_NO_AMOUNT)
    if not _amount_ok(amount):
        return _result(echoed_id, "failed", None, echoed_amount, echoed_currency, REASON_BAD_AMOUNT)

    return _result(
        echoed_id,
        "refunded",
        _refund_code(echoed_id, code, echoed_amount, echoed_currency),
        echoed_amount,
        echoed_currency,
        None,
    )


def _echo_amount(amount):
    if isinstance(amount, bool):
        return None
    if isinstance(amount, (int, float)):
        return amount
    if isinstance(amount, str):
        text = amount.strip()
        return text if text else None
    return None


def _echo_currency(currency):
    if isinstance(currency, str):
        text = currency.strip()
        return text if text else None
    return None


def _amount_missing(amount) -> bool:
    if amount is None or isinstance(amount, bool):
        return True
    if isinstance(amount, str) and not amount.strip():
        return True
    return False


def _amount_ok(amount) -> bool:
    if isinstance(amount, bool):
        return False
    if isinstance(amount, float):
        return math.isfinite(amount) and amount >= 0
    if isinstance(amount, int):
        return amount >= 0
    if not isinstance(amount, str):
        return False
    text = amount.strip()
    if not text or text.startswith("-"):
        return False
    whole, dot, fraction = text.partition(".")
    if not whole.isdigit():
        return False
    if dot and not fraction.isdigit():
        return False
    return True


def _refund_code(segment_id: str, confirmation_code: str, amount, currency) -> str:
    amount_key = str(amount)
    currency_key = "" if currency is None else currency
    raw = "|".join([segment_id, confirmation_code, amount_key, currency_key])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-REF-{digest}"


def _result(segment_id, status, refund_code, amount, currency, reason) -> dict:
    return {
        "segmentId": segment_id,
        "status": status,
        "refundCode": refund_code,
        "amount": amount,
        "currency": currency,
        "reason": reason,
    }
