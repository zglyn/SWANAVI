"""Quote a departure tax refund from eligible purchases.

Sandbox only. Japan and France use the rates fixed in this module. Other
countries return status ``none``. This module does not call a tax authority,
open the network, or call AWS. It does not read the wall clock: the caller
supplies ``now``. A partial input returns a result and does not raise.

This is a quote, not tax advice.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import NamedTuple

REASON_QUOTED = "quoted"
REASON_BELOW = "below_minimum"
REASON_DEPARTED = "departed"
REASON_UNSUPPORTED = "unsupported_country"
REASON_INVALID = "invalid_input"
REASON_TIME = "invalid_time"

_CALL_KEYS = ("country", "purchases", "departAt", "now")
_ZERO = Decimal(0)
_ONE = Decimal("1")
_CENTS = Decimal("0.01")


class _Rule(NamedTuple):
    currency: str
    rate: Decimal
    minimum: Decimal
    places: int


_JAPAN = _Rule("JPY", Decimal("0.10"), Decimal("5000"), 0)
_FRANCE = _Rule("EUR", Decimal("0.20"), Decimal("100"), 2)

# Country name plus the ISO code a booking payload is likely to send.
_RULES = {
    "japan": _JAPAN,
    "jp": _JAPAN,
    "france": _FRANCE,
    "fr": _FRANCE,
}


def tax_refund(country=None, purchases=None, departAt=None, now=None) -> dict:
    """Quote a tax refund. Never raises.

    Input is ``{country, purchases, departAt, now}``. ``purchases`` is a list
    of ``{amount, currency, eligible}``. ``departAt`` and ``now`` are ISO-8601
    timestamps. Only eligible lines in the country's refund currency are
    summed. Other currencies are ignored and not converted.

    Japan refunds 10% of eligible JPY spend when that spend is at least 5000
    JPY. France refunds 20% of eligible EUR spend when that spend is at least
    100 EUR. Spend under the minimum returns status ``too_small`` and
    ``refundAmount`` 0. When ``now`` is after ``departAt``, status is
    ``missed``, ``claimBefore`` is ``departAt``, and ``refundAmount`` is still
    the quoted amount. Otherwise status is ``eligible``. JPY is rounded to 0
    decimals and EUR to 2. Any other country returns status ``none`` and
    ``refundAmount`` 0.
    """
    try:
        data = _payload(country, purchases, departAt, now)
        if not isinstance(data, dict):
            return _none(REASON_INVALID)
        return _quote(data)
    except Exception:
        return _none(REASON_INVALID)


def _payload(country, purchases, departAt, now):
    bare = purchases is None and departAt is None and now is None
    if isinstance(country, dict) and bare:
        return _unwrap(country)
    if isinstance(country, str) and bare:
        stripped = country.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return _load(stripped)
        return {"country": country, "purchases": None, "departAt": None, "now": None}
    if country is not None and bare and not isinstance(country, (str, dict)):
        return None
    return {"country": country, "purchases": purchases, "departAt": departAt, "now": now}


def _quote(data: dict) -> dict:
    rule = _rule(data.get("country"))
    if rule is None:
        return _none(REASON_UNSUPPORTED)
    total = _eligible_sum(data.get("purchases"), rule.currency)
    if total is None:
        return _none(REASON_INVALID)
    spend = _quantize(total, rule.places)
    shown = _number(spend)
    if spend < rule.minimum:
        return _result("too_small", 0, rule.currency, shown, None, REASON_BELOW)
    depart_at = _instant(data.get("departAt"))
    clock = _instant(data.get("now"))
    if depart_at is None or clock is None:
        return _result("none", 0, rule.currency, shown, None, REASON_TIME)
    refund = _number(_quantize(spend * rule.rate, rule.places))
    claim_before = _format(depart_at)
    if clock > depart_at:
        return _result("missed", refund, rule.currency, shown, claim_before, REASON_DEPARTED)
    return _result("eligible", refund, rule.currency, shown, claim_before, REASON_QUOTED)


def _eligible_sum(purchases, currency: str):
    if purchases is None:
        return _ZERO
    if not isinstance(purchases, list):
        return None
    total = _ZERO
    for line in purchases:
        amount = _line_amount(line, currency)
        if amount is not None:
            total += amount
    return total


def _line_amount(line, currency: str):
    if not isinstance(line, dict):
        return None
    if line.get("eligible") is not True:
        return None
    if _code(line.get("currency")) != currency:
        return None
    return _parse_amount(line.get("amount"))


def _rule(country) -> _Rule | None:
    if not isinstance(country, str):
        return None
    key = " ".join(country.casefold().replace(".", "").split())
    return _RULES.get(key)


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
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def _quantize(amount: Decimal, places: int) -> Decimal:
    unit = _ONE if places == 0 else _CENTS
    return amount.quantize(unit, rounding=ROUND_HALF_UP)


def _number(value: Decimal):
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _code(value) -> str:
    if isinstance(value, str):
        return value.strip().upper()
    return ""


def _instant(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "T" not in text:
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


def _format(value: datetime) -> str:
    utc = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _none(reason: str) -> dict:
    return _result("none", 0, "", 0, None, reason)


def _result(status: str, refund_amount, refund_currency: str, eligible_spend, claim_before, reason: str) -> dict:
    return {
        "status": status,
        "refundAmount": refund_amount,
        "refundCurrency": refund_currency,
        "eligibleSpend": eligible_spend,
        "claimBefore": claim_before,
        "reason": reason,
    }


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _CALL_KEYS):
        return nested
    return payload


def _load(text: str):
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return _unwrap(loaded)
