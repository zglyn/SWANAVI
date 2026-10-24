"""Import capability packages owned by other agents.

Missing packages are reported by the caller. This module does not implement
booking, email parsing, trip progress, replanning, or the guard tools.
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
BudgetFn = Callable[[str, dict[str, Any], dict[str, Any] | None], Any]
SpendFn = Callable[[int, int, str], Any]
RefundFn = Callable[[str, str | None, str | None], Any]
ConflictsFn = Callable[[str, dict[str, Any]], Any]
NoticeFn = Callable[[str, dict[str, Any]], Any]

PROVIDER_NOT_INSTALLED = "provider_not_installed"
VERIFIER_NOT_INSTALLED = "verifier_not_installed"
PROGRESS_NOT_INSTALLED = "progress_not_installed"
REPLAN_NOT_INSTALLED = "replan_not_installed"
CHECK_BUDGET_NOT_INSTALLED = "check_budget_not_installed"
AUTHORIZE_SPEND_NOT_INSTALLED = "authorize_spend_not_installed"
REFUND_BOOKING_NOT_INSTALLED = "refund_booking_not_installed"
CHECK_CONFLICTS_NOT_INSTALLED = "check_conflicts_not_installed"
TRIP_NOTICE_NOT_INSTALLED = "trip_notice_not_installed"

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

# Guard tools live in their own packages. The master only calls them.
BUDGET_MODULE = "booking.guard.budget"
BUDGET_EXPORT = "check_budget"
SPEND_MODULE = "booking.guard.spend"
SPEND_EXPORT = "authorize_spend"
CONFLICTS_MODULE = "booking.guard.conflicts"
CONFLICTS_EXPORT = "check_conflicts"
REFUND_MODULE = "booking.refund"
REFUND_EXPORT = "refund_booking"
NOTIFY_MODULE = "booking.notify"
NOTIFY_EXPORT = "trip_notice"


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


def load_check_budget() -> BudgetFn | None:
    """Return check_budget, or None when booking.guard.budget is not importable."""

    return _load_callable(BUDGET_MODULE, BUDGET_EXPORT)


def load_authorize_spend() -> SpendFn | None:
    """Return authorize_spend, or None when booking.guard.spend is not importable."""

    return _load_callable(SPEND_MODULE, SPEND_EXPORT)


def load_refund_booking() -> RefundFn | None:
    """Return refund_booking, or None when booking.refund is not importable."""

    return _load_callable(REFUND_MODULE, REFUND_EXPORT)


def load_check_conflicts() -> ConflictsFn | None:
    """Return check_conflicts, or None when booking.guard.conflicts is not importable."""

    return _load_callable(CONFLICTS_MODULE, CONFLICTS_EXPORT)


def load_trip_notice() -> NoticeFn | None:
    """Return trip_notice, or None when booking.notify is not importable."""

    return _load_callable(NOTIFY_MODULE, NOTIFY_EXPORT)


def _load_callable(module_name: str, export: str) -> Any | None:
    module = _import(module_name)
    if module is None:
        return None
    fn = getattr(module, export, None)
    if not callable(fn):
        return None
    return fn


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
