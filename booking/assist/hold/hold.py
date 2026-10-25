"""Explain a hotel incidental authorization.

The hold is not a charge. ``releaseAmount`` is the part of ``authorizedHold``
that was not captured. ``releaseBy`` is ``checkoutAt`` plus 7 days. This
module does not capture, charge, or contact a card network. It does not read
the wall clock, open the network, or call AWS. A later integrator wires the
master. This module does not.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

RELEASE_DAYS = 7

REASON_HELD = "held"
REASON_OVER = "over_capture"
REASON_FULL = "captured_in_full"
REASON_INVALID = "invalid_amount"

_CALL_KEYS = ("authorizedHold", "capturedAmount", "currency", "checkoutAt")
_CENTS = Decimal("0.01")
_YEN = Decimal("1")
_RELEASE = timedelta(days=RELEASE_DAYS)


def incidental_hold(
    authorizedHold=None,
    capturedAmount=None,
    currency=None,
    checkoutAt=None,
) -> dict:
    """Explain how much of a hotel incidental hold is still uncaptured.

    Input is ``authorizedHold``, ``capturedAmount``, ``currency``, and
    ``checkoutAt`` (ISO-8601, Z). The hold is not a charge. When the capture
    is within the hold, ``releaseAmount`` is ``authorizedHold - capturedAmount``
    and ``reason`` is ``held``, except when the two amounts are equal:
    ``releaseAmount`` is 0 and ``reason`` is ``captured_in_full``. When the
    capture is above the hold, the extra is not accepted: ``releaseAmount``
    is 0, ``payAmount`` is ``authorizedHold``, and ``reason`` is
    ``over_capture``. ``payAmount`` is ``min(captured, authorized)`` when both
    numbers are usable. A negative number returns ``reason`` ``invalid_amount``
    and ``releaseAmount`` 0. Amounts round half up to 2 decimals, and JPY
    rounds to 0. ``releaseBy`` is ``checkoutAt`` plus 7 days when the amounts
    are usable and ``checkoutAt`` is an ISO timestamp. Never raises.
    """
    try:
        data = _payload(authorizedHold, capturedAmount, currency, checkoutAt)
        if not isinstance(data, dict):
            return _invalid()
        return _decide(data)
    except Exception:
        return _invalid()


def _payload(authorizedHold, capturedAmount, currency, checkoutAt):
    bare = (
        _is_payload(authorizedHold)
        and capturedAmount is None
        and currency is None
        and checkoutAt is None
    )
    if bare:
        return _load(authorizedHold)
    return {
        "authorizedHold": authorizedHold,
        "capturedAmount": capturedAmount,
        "currency": currency,
        "checkoutAt": checkoutAt,
    }


def _decide(data: dict) -> dict:
    currency = _text(data.get("currency"))
    scale = _scale(currency)
    authorized = _parse_amount(data.get("authorizedHold"))
    captured = _parse_amount(data.get("capturedAmount"))
    if authorized is None or captured is None or authorized < 0 or captured < 0:
        return _result(
            _echo(authorized, scale),
            _echo(captured, scale),
            0,
            currency,
            None,
            0,
            REASON_INVALID,
        )

    authorized_q = _quantize(authorized, scale)
    captured_q = _quantize(captured, scale)
    release_by = _release_by(data.get("checkoutAt"))
    authorized_n = _number(authorized_q)
    captured_n = _number(captured_q)
    if captured_q > authorized_q:
        return _result(
            authorized_n,
            captured_n,
            0,
            currency,
            release_by,
            authorized_n,
            REASON_OVER,
        )
    if captured_q == authorized_q:
        return _result(
            authorized_n,
            captured_n,
            0,
            currency,
            release_by,
            authorized_n,
            REASON_FULL,
        )
    release = authorized_q - captured_q
    return _result(
        authorized_n,
        captured_n,
        _number(release),
        currency,
        release_by,
        captured_n,
        REASON_HELD,
    )


def _invalid() -> dict:
    return _result(0, 0, 0, "", None, 0, REASON_INVALID)


def _result(authorized, captured, release, currency: str, release_by, pay, reason: str) -> dict:
    return {
        "authorizedHold": authorized,
        "capturedAmount": captured,
        "releaseAmount": release,
        "currency": currency,
        "releaseBy": release_by,
        "payAmount": pay,
        "reason": reason,
    }


def _scale(currency: str) -> Decimal:
    if currency.upper() == "JPY":
        return _YEN
    return _CENTS


def _echo(amount: Decimal | None, scale: Decimal):
    if amount is None:
        return 0
    return _number(_quantize(amount, scale))


def _quantize(amount: Decimal, scale: Decimal) -> Decimal:
    return amount.quantize(scale, rounding=ROUND_HALF_UP)


def _number(amount: Decimal):
    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)


def _parse_amount(value) -> Decimal | None:
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


def _release_by(value) -> str | None:
    instant = _instant(value)
    if instant is None:
        return None
    return _format_z(instant + _RELEASE)


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "T" not in text.upper():
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_z(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    stamp = value.strftime("%Y-%m-%dT%H:%M:%S")
    if value.microsecond:
        fraction = f"{value.microsecond:06d}".rstrip("0")
        return stamp + "." + fraction + "Z"
    return stamp + "Z"


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
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
