"""Import capability packages owned by other agents.

Missing packages are reported by the caller. This module does not implement
booking, email parsing, trip progress, replanning, the guard tools, or the
assist tools.
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
CHECK_ENTRY_NOT_INSTALLED = "check_entry_not_installed"
CHECK_HOURS_NOT_INSTALLED = "check_hours_not_installed"
CHECK_TRANSFER_NOT_INSTALLED = "check_transfer_not_installed"
QUOTE_FX_NOT_INSTALLED = "quote_fx_not_installed"
CHECK_WEATHER_NOT_INSTALLED = "check_weather_not_installed"
EMERGENCY_CARD_NOT_INSTALLED = "emergency_card_not_installed"
REQUEST_RIDE_NOT_INSTALLED = "request_ride_not_installed"
HOLD_TABLE_NOT_INSTALLED = "hold_table_not_installed"
LUGGAGE_DROP_NOT_INSTALLED = "luggage_drop_not_installed"
WATCH_NOT_INSTALLED = "watch_not_installed"
AIRPORT_LEAVE_NOT_INSTALLED = "airport_leave_not_installed"
AFTER_DARK_NOT_INSTALLED = "after_dark_not_installed"
LATE_CHECKOUT_NOT_INSTALLED = "late_checkout_not_installed"
TIP_POLICY_NOT_INSTALLED = "tip_policy_not_installed"
PHRASE_CARD_NOT_INSTALLED = "phrase_card_not_installed"
TRIP_WALLET_NOT_INSTALLED = "trip_wallet_not_installed"
FLIGHT_STATUS_NOT_INSTALLED = "flight_status_not_installed"
CHECK_IN_FLIGHT_NOT_INSTALLED = "check_in_flight_not_installed"
REFUSE_DCC_NOT_INSTALLED = "refuse_dcc_not_installed"
PICK_CARD_NOT_INSTALLED = "pick_card_not_installed"
CASH_NEEDED_NOT_INSTALLED = "cash_needed_not_installed"
HOLIDAY_CLOSURE_NOT_INSTALLED = "holiday_closure_not_installed"
CHECK_LAYOVER_NOT_INSTALLED = "check_layover_not_installed"
ETIQUETTE_CARD_NOT_INSTALLED = "etiquette_card_not_installed"
TAX_REFUND_NOT_INSTALLED = "tax_refund_not_installed"
REBOOK_SEGMENT_NOT_INSTALLED = "rebook_segment_not_installed"
INCIDENTAL_HOLD_NOT_INSTALLED = "incidental_hold_not_installed"
LANDING_DATA_NOT_INSTALLED = "landing_data_not_installed"

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

# Assist tools live in their own packages. The master only calls them.
ENTRY_MODULE = "booking.assist.entry"
ENTRY_EXPORT = "check_entry"
HOURS_MODULE = "booking.assist.hours"
HOURS_EXPORT = "check_hours"
TRANSFERS_MODULE = "booking.assist.transfers"
TRANSFERS_EXPORT = "check_transfer"
FX_MODULE = "booking.assist.fx"
FX_EXPORT = "quote_fx"
WEATHER_MODULE = "booking.assist.weather"
WEATHER_EXPORT = "check_weather"
EMERGENCY_MODULE = "booking.assist.emergency"
EMERGENCY_EXPORT = "emergency_card"
RIDE_MODULE = "booking.assist.ride"
RIDE_EXPORT = "request_ride"
TABLE_MODULE = "booking.assist.table"
TABLE_EXPORT = "hold_table"
LUGGAGE_MODULE = "booking.assist.luggage"
LUGGAGE_EXPORT = "luggage_drop"
WATCH_MODULE = "booking.assist.watch"
WATCH_EXPORT = "watch_trip"
AIRPORT_MODULE = "booking.assist.airport"
AIRPORT_EXPORT = "airport_leave"
AFTER_DARK_MODULE = "booking.assist.afterdark"
AFTER_DARK_EXPORT = "after_dark"
CHECKOUT_MODULE = "booking.assist.checkout"
CHECKOUT_EXPORT = "late_checkout"
TIP_MODULE = "booking.assist.tip"
TIP_EXPORT = "tip_policy"
PHRASE_MODULE = "booking.assist.phrase"
PHRASE_EXPORT = "phrase_card"
WALLET_MODULE = "booking.assist.wallet"
WALLET_EXPORT = "trip_wallet"
FLIGHT_STATUS_MODULE = "booking.assist.flightstatus"
FLIGHT_STATUS_EXPORT = "flight_status"
CHECK_IN_MODULE = "booking.assist.checkin"
CHECK_IN_EXPORT = "check_in_flight"
DCC_MODULE = "booking.assist.dcc"
DCC_EXPORT = "refuse_dcc"
CARD_MODULE = "booking.assist.card"
CARD_EXPORT = "pick_card"
CASH_MODULE = "booking.assist.cash"
CASH_EXPORT = "cash_needed"
HOLIDAY_MODULE = "booking.assist.holidays"
HOLIDAY_EXPORT = "holiday_closure"
LAYOVER_MODULE = "booking.assist.layover"
LAYOVER_EXPORT = "check_layover"
ETIQUETTE_MODULE = "booking.assist.etiquette"
ETIQUETTE_EXPORT = "etiquette_card"
TAX_REFUND_MODULE = "booking.assist.taxrefund"
TAX_REFUND_EXPORT = "tax_refund"
REBOOK_SEGMENT_MODULE = "booking.assist.rebook"
REBOOK_SEGMENT_EXPORT = "rebook_segment"
INCIDENTAL_HOLD_MODULE = "booking.assist.hold"
INCIDENTAL_HOLD_EXPORT = "incidental_hold"
LANDING_MODULE = "booking.assist.connectivity"
LANDING_EXPORT = "landing_data"


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


def load_check_entry() -> Any | None:
    """Return check_entry, or None when booking.assist.entry is not importable."""

    return _load_callable(ENTRY_MODULE, ENTRY_EXPORT)


def load_check_hours() -> Any | None:
    """Return check_hours, or None when booking.assist.hours is not importable."""

    return _load_callable(HOURS_MODULE, HOURS_EXPORT)


def load_check_transfer() -> Any | None:
    """Return check_transfer, or None when booking.assist.transfers is not importable."""

    return _load_callable(TRANSFERS_MODULE, TRANSFERS_EXPORT)


def load_quote_fx() -> Any | None:
    """Return quote_fx, or None when booking.assist.fx is not importable."""

    return _load_callable(FX_MODULE, FX_EXPORT)


def load_check_weather() -> Any | None:
    """Return check_weather, or None when booking.assist.weather is not importable."""

    return _load_callable(WEATHER_MODULE, WEATHER_EXPORT)


def load_emergency_card() -> Any | None:
    """Return emergency_card, or None when booking.assist.emergency is not importable."""

    return _load_callable(EMERGENCY_MODULE, EMERGENCY_EXPORT)


def load_request_ride() -> Any | None:
    """Return request_ride, or None when booking.assist.ride is not importable."""

    return _load_callable(RIDE_MODULE, RIDE_EXPORT)


def load_hold_table() -> Any | None:
    """Return hold_table, or None when booking.assist.table is not importable."""

    return _load_callable(TABLE_MODULE, TABLE_EXPORT)


def load_luggage_drop() -> Any | None:
    """Return luggage_drop, or None when booking.assist.luggage is not importable."""

    return _load_callable(LUGGAGE_MODULE, LUGGAGE_EXPORT)


def load_watch_trip() -> Any | None:
    """Return watch_trip, or None when booking.assist.watch is not importable."""

    return _load_callable(WATCH_MODULE, WATCH_EXPORT)


def load_airport_leave() -> Any | None:
    """Return airport_leave, or None when booking.assist.airport is not importable."""

    return _load_callable(AIRPORT_MODULE, AIRPORT_EXPORT)


def load_after_dark() -> Any | None:
    """Return after_dark, or None when booking.assist.afterdark is not importable."""

    return _load_callable(AFTER_DARK_MODULE, AFTER_DARK_EXPORT)


def load_late_checkout() -> Any | None:
    """Return late_checkout, or None when booking.assist.checkout is not importable."""

    return _load_callable(CHECKOUT_MODULE, CHECKOUT_EXPORT)


def load_tip_policy() -> Any | None:
    """Return tip_policy, or None when booking.assist.tip is not importable."""

    return _load_callable(TIP_MODULE, TIP_EXPORT)


def load_phrase_card() -> Any | None:
    """Return phrase_card, or None when booking.assist.phrase is not importable."""

    return _load_callable(PHRASE_MODULE, PHRASE_EXPORT)


def load_trip_wallet() -> Any | None:
    """Return trip_wallet, or None when booking.assist.wallet is not importable."""

    return _load_callable(WALLET_MODULE, WALLET_EXPORT)


def load_flight_status() -> Any | None:
    """Return flight_status, or None when booking.assist.flightstatus is not importable."""

    return _load_callable(FLIGHT_STATUS_MODULE, FLIGHT_STATUS_EXPORT)


def load_check_in_flight() -> Any | None:
    """Return check_in_flight, or None when booking.assist.checkin is not importable."""

    return _load_callable(CHECK_IN_MODULE, CHECK_IN_EXPORT)


def load_refuse_dcc() -> Any | None:
    """Return refuse_dcc, or None when booking.assist.dcc is not importable."""

    return _load_callable(DCC_MODULE, DCC_EXPORT)


def load_pick_card() -> Any | None:
    """Return pick_card, or None when booking.assist.card is not importable."""

    return _load_callable(CARD_MODULE, CARD_EXPORT)


def load_cash_needed() -> Any | None:
    """Return cash_needed, or None when booking.assist.cash is not importable."""

    return _load_callable(CASH_MODULE, CASH_EXPORT)


def load_holiday_closure() -> Any | None:
    """Return holiday_closure, or None when booking.assist.holidays is not importable."""

    return _load_callable(HOLIDAY_MODULE, HOLIDAY_EXPORT)


def load_check_layover() -> Any | None:
    """Return check_layover, or None when booking.assist.layover is not importable."""

    return _load_callable(LAYOVER_MODULE, LAYOVER_EXPORT)


def load_etiquette_card() -> Any | None:
    """Return etiquette_card, or None when booking.assist.etiquette is not importable."""

    return _load_callable(ETIQUETTE_MODULE, ETIQUETTE_EXPORT)


def load_tax_refund() -> Any | None:
    """Return tax_refund, or None when booking.assist.taxrefund is not importable."""

    return _load_callable(TAX_REFUND_MODULE, TAX_REFUND_EXPORT)


def load_rebook_segment() -> Any | None:
    """Return rebook_segment, or None when booking.assist.rebook is not importable."""

    return _load_callable(REBOOK_SEGMENT_MODULE, REBOOK_SEGMENT_EXPORT)


def load_incidental_hold() -> Any | None:
    """Return incidental_hold, or None when booking.assist.hold is not importable."""

    return _load_callable(INCIDENTAL_HOLD_MODULE, INCIDENTAL_HOLD_EXPORT)


def load_landing_data() -> Any | None:
    """Return landing_data, or None when booking.assist.connectivity is not importable."""

    return _load_callable(LANDING_MODULE, LANDING_EXPORT)


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
