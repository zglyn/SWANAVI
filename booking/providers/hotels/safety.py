"""Payment-instrument detection for hotel booking.

The sandbox and the Amadeus client both refuse card data. Nothing in this
package charges a card.
"""

from __future__ import annotations

_INSTRUMENT_KEYS = {
    "card",
    "cardnumber",
    "creditcard",
    "pan",
    "cvv",
    "cvc",
    "paymentmethod",
    "paymentinstrument",
    "primaryaccountnumber",
}


def contains_payment_instrument(value: object) -> bool:
    """True when ``value`` carries a card or other payment instrument."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _is_instrument(key, item):
                return True
            if contains_payment_instrument(item):
                return True
        return False
    if isinstance(value, list):
        return any(contains_payment_instrument(item) for item in value)
    return False


def _is_instrument(key: str, item: object) -> bool:
    normalized = "".join(char for char in key.lower() if char.isalnum())
    if normalized in _INSTRUMENT_KEYS:
        return True
    if normalized == "payment" and isinstance(item, (dict, list)):
        return True
    return False
