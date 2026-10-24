"""Decide whether a proposed charge fits the trip budget.

Sandbox only: the caller supplies every amount. This module does not look up
the trip, open the network, or call AWS. It does not book and it does not
replan. The master agent calls ``check_budget`` before accepting a booking or
a replan that adds cost.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

_AMOUNT_FIELDS = ("budgetAmount", "spentAmount", "proposedAmount")
_ENVELOPE_KEYS = ("budgetAmount", "spentAmount", "proposedAmount", "currency", "tripId")

REASON_WITHIN = "spentAmount + proposedAmount is within budgetAmount"
REASON_EXCEEDS = "spentAmount + proposedAmount exceeds budgetAmount"
REASON_FAILED = "check_budget failed closed"


def check_budget(source=None) -> dict:
    """Return ``allowed``, ``remaining``, ``currency``, and ``reason``. Never raises.

    ``source`` is ``{tripId, currency, budgetAmount, spentAmount, proposedAmount}``
    or a JSON object with those fields. ``allowed`` is true only when
    ``spentAmount + proposedAmount <= budgetAmount``. ``remaining`` is
    ``budgetAmount - spentAmount - proposedAmount`` as a decimal string, and
    is negative when the charge is blocked. A missing or non-numeric amount
    is not allowed.
    """
    try:
        return _decide(_mapping(source))
    except Exception:
        return _result(False, None, "", REASON_FAILED)


def _mapping(source) -> dict:
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError:
            return {}
    if not isinstance(source, dict):
        return {}
    arguments = source.get("arguments")
    if isinstance(arguments, dict):
        source = arguments
    elif isinstance(source.get("input"), dict) and not _looks_like_budget(source):
        source = source["input"]
    if not isinstance(source, dict):
        return {}
    return source


def _looks_like_budget(value: dict) -> bool:
    return any(key in value for key in _ENVELOPE_KEYS)


def _decide(data: dict) -> dict:
    currency = _currency(data.get("currency"))
    missing = []
    invalid = []
    amounts = {}
    for key in _AMOUNT_FIELDS:
        if key not in data or _blank(data[key]):
            missing.append(key)
            continue
        parsed = _parse_amount(data[key])
        if parsed is None:
            invalid.append(key)
            continue
        amounts[key] = parsed
    if missing or invalid:
        return _result(False, None, currency, _amount_problem(missing, invalid))

    budget = amounts["budgetAmount"]
    spent = amounts["spentAmount"]
    proposed = amounts["proposedAmount"]
    remaining = budget - spent - proposed
    allowed = spent + proposed <= budget
    return _result(allowed, _format_money(remaining), currency, REASON_WITHIN if allowed else REASON_EXCEEDS)


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _amount_problem(missing: list[str], invalid: list[str]) -> str:
    parts = []
    if missing:
        parts.append("missing " + ", ".join(missing))
    if invalid:
        parts.append("invalid " + ", ".join(invalid))
    return "; ".join(parts)


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
        try:
            amount = Decimal(value.strip())
        except InvalidOperation:
            return None
    else:
        return None
    if not amount.is_finite():
        return None
    return amount


def _currency(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _format_money(value: Decimal) -> str:
    if value == 0:
        value = Decimal(0)
    text = format(value, "f")
    if "." not in text:
        return text + ".00"
    whole, frac = text.split(".", 1)
    if len(frac) < 2:
        frac = frac.ljust(2, "0")
    else:
        frac = frac.rstrip("0")
        if len(frac) < 2:
            frac = frac.ljust(2, "0")
    return f"{whole}.{frac}"


def _result(allowed: bool, remaining, currency: str, reason: str) -> dict:
    return {
        "allowed": allowed,
        "remaining": remaining,
        "currency": currency,
        "reason": reason,
    }
