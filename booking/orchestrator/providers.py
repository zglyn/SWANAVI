"""Load sibling booking providers. This package does not implement them."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

ProviderBook = Callable[[dict[str, Any], list[dict[str, Any]], str], dict[str, Any]]

# Other agents own these packages. Each must export book(segment, travelers, trip_id).
PROVIDER_MODULES: dict[str, str] = {
    "flight": "booking.providers.flights",
    "hotel": "booking.providers.hotels",
    "attraction": "booking.providers.attractions",
}

NOT_INSTALLED = "provider_not_installed"


def load_book(kind: str) -> ProviderBook | None:
    """Return the sibling book function, or None when that provider is not importable."""

    module_name = PROVIDER_MODULES[kind]
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    book = getattr(module, "book", None)
    if not callable(book):
        return None
    return book
