"""Import capability packages owned by other agents.

Missing packages are reported by the caller. This module does not implement
booking, email parsing, trip progress, or replanning.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

BookFn = Callable[[dict[str, Any], list[Any], str], Any]
SampleEmailFn = Callable[[dict[str, Any], str, list[Any], str], Any]
VerifyFn = Callable[[dict[str, Any], dict[str, Any], str, list[Any]], Any]
ProgressFn = Callable[[dict[str, Any], list[dict[str, Any]], dict[str, Any]], Any]
ReplanFn = Callable[[str, str, dict[str, Any], dict[str, Any]], Any]

PROVIDER_NOT_INSTALLED = "provider_not_installed"
VERIFIER_NOT_INSTALLED = "verifier_not_installed"
PROGRESS_NOT_INSTALLED = "progress_not_installed"
REPLAN_NOT_INSTALLED = "replan_not_installed"

PROVIDER_MODULES = {
    "flight": "booking.providers.flights",
    "hotel": "booking.providers.hotels",
    "attraction": "booking.providers.attractions",
}

# Named tool on the provider package when that package exports one.
# Otherwise the master calls book(segment, travelers, trip_id).
BOOK_TOOL_EXPORTS = {
    "flight": "book_flight",
    "hotel": "book_hotel",
    "attraction": "book_attraction",
}

VERIFY_MODULES = {
    "flight": "booking.verify.flights",
    "hotel": "booking.verify.hotels",
    "attraction": "booking.verify.attractions",
}

PROGRESS_MODULE = "booking.progress"
PROGRESS_EXPORT = "trip_progress"

# One package per disruption event. The master calls that event's tool and
# does not shift the day itself.
REPLAN_MODULES = {
    "cancelled": "booking.replan.cancel",
    "ended_early": "booking.replan.early",
    "ended_late": "booking.replan.late",
}

REPLAN_EXPORTS = {
    "cancelled": "replan_cancel",
    "ended_early": "replan_early",
    "ended_late": "replan_late",
}


class ProgressNotInstalled(Exception):
    """booking.progress.trip_progress is not importable."""


def load_book(kind: str) -> BookFn | None:
    """Return the provider tool, or None when that package is not importable."""

    module = _import(PROVIDER_MODULES[kind])
    if module is None:
        return None
    named = getattr(module, BOOK_TOOL_EXPORTS[kind], None)
    if _callable_same_shape(named):
        return named
    book = getattr(module, "book", None)
    if callable(book):
        return book
    tool = _import(f"{PROVIDER_MODULES[kind]}.tool")
    if tool is None:
        return None
    named = getattr(tool, BOOK_TOOL_EXPORTS[kind], None)
    if _callable_same_shape(named):
        return named
    handler = getattr(tool, "handler", None)
    if kind == "attraction" or not callable(handler):
        return None
    return _handler_as_book(handler)


def load_verifier(kind: str) -> tuple[SampleEmailFn, VerifyFn] | None:
    """Return (sample_email, verify), or None when that verifier is not importable."""

    module = _import(VERIFY_MODULES[kind])
    if module is None:
        return None
    sample_email = getattr(module, "sample_email", None)
    verify = getattr(module, "verify", None)
    if not callable(sample_email) or not callable(verify):
        return None
    return sample_email, verify


def load_trip_progress() -> ProgressFn | None:
    """Return trip_progress, or None when booking.progress is not importable."""

    module = _import(PROGRESS_MODULE)
    if module is None:
        return None
    progress = getattr(module, PROGRESS_EXPORT, None)
    if not callable(progress):
        return None
    return progress


def load_replan(event: str) -> ReplanFn | None:
    """Return that event's replan tool, or None when its package is not importable."""

    module_name = REPLAN_MODULES.get(event)
    export = REPLAN_EXPORTS.get(event)
    if module_name is None or export is None:
        return None
    module = _import(module_name)
    if module is None:
        return None
    replan = getattr(module, export, None)
    if not callable(replan):
        return None
    return replan


def _import(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


def _callable_same_shape(fn: object) -> bool:
    """True for book(segment, travelers, trip_id). Handler-style tools are wrapped elsewhere."""

    return callable(fn)


def _handler_as_book(handler: Callable[..., Any]) -> BookFn:
    def book(segment: dict[str, Any], travelers: list[Any], trip_id: str) -> Any:
        return handler({"segment": segment, "travelers": travelers, "trip_id": trip_id})

    return book
