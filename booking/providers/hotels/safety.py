"""Guards shared by the sandbox and the optional live adapter.

The default sandbox never calls these network checks. The live adapter uses
them so a mis-set environment cannot reach a production hotel host or send
card data.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .errors import HotelProviderError

# Normalized key (lowercase, alphanumeric only) -> payment instrument.
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

# Real hotel / GDS hosts. Matched on the registrable suffix, including
# sandbox subdomains of those brands (sandbox.booking.com is still production).
_PRODUCTION_SUFFIXES = (
    "booking.com",
    "expedia.com",
    "expedia.co.uk",
    "hotels.com",
    "priceline.com",
    "agoda.com",
    "kayak.com",
    "amadeus.com",
    "amadeus.net",
    "hotelbeds.com",
    "tripadvisor.com",
    "airbnb.com",
    "vrbo.com",
    "hotelscombined.com",
)

_SANDBOX_LABELS = {
    "sandbox",
    "sandboxes",
    "test",
    "testing",
    "stub",
    "mock",
    "fake",
    "local",
    "localhost",
}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


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


def assert_safe_hotel_url(url: str) -> str:
    """Return ``url`` when it is a sandbox/test hotel endpoint.

    Raises ``HotelProviderError`` for production hosts, credentialed URLs,
    and any host that is not clearly a sandbox, test, or local endpoint.
    """
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"https", "http"} or not host:
        raise HotelProviderError("hotel API URL is invalid")
    if parsed.username or parsed.password:
        raise HotelProviderError("hotel API URL must not include credentials")
    if parsed.scheme != "https" and host not in _LOCAL_HOSTS:
        raise HotelProviderError("live hotel API must use https")
    if _is_production_host(host):
        raise HotelProviderError("refusing production hotel host")
    if not _is_sandbox_host(host):
        raise HotelProviderError("live hotel host must be a sandbox or test endpoint")
    return url.strip()


def _is_instrument(key: str, item: object) -> bool:
    normalized = "".join(char for char in key.lower() if char.isalnum())
    if normalized in _INSTRUMENT_KEYS:
        return True
    if normalized == "payment" and isinstance(item, (dict, list)):
        return True
    return False


def _is_production_host(host: str) -> bool:
    labels = host.split(".")
    if any(label in {"prod", "production"} for label in labels):
        return True
    return any(_matches_suffix(host, suffix) for suffix in _PRODUCTION_SUFFIXES)


def _is_sandbox_host(host: str) -> bool:
    if host in _LOCAL_HOSTS:
        return True
    labels = host.split(".")
    return any(
        label in _SANDBOX_LABELS or label.startswith("sandbox") or label.startswith("test")
        for label in labels
    )


def _matches_suffix(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)
