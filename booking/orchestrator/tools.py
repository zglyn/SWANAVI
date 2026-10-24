"""Tools registered on the Bedrock AgentCore runtime.

The runtime entrypoint is the only caller. Each tool calls a sibling provider
when that package imports, and never calls Amadeus itself. Browser, code
interpreter, and payment tools are not registered.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from booking.contract import Price, SegmentResult
from booking.orchestrator.providers import NOT_INSTALLED, load_book

# Amadeus Python SDK hostname. Unset means sandbox. Only the test host is allowed.
SANDBOX_HOSTNAME = "test"
PRODUCTION_REFUSED = "production_booking_refused"

ToolFn = Callable[[dict[str, Any], list[dict[str, Any]], str], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str
    description: str
    fn: ToolFn


def _segment_result(
    segment_id: str,
    kind: str,
    status: str,
    *,
    confirmation_code: str | None = None,
    price: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    parsed_price = None
    if price is not None:
        parsed_price = Price.model_validate(price).model_dump()
    return SegmentResult(
        segmentId=segment_id,
        kind=kind,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        confirmationCode=confirmation_code,
        price=parsed_price,
        error=error,
    ).model_dump()


def _not_installed(segment_id: str, kind: str) -> dict[str, Any]:
    return _segment_result(segment_id, kind, "failed", error=NOT_INSTALLED)


def _failed(segment_id: str, kind: str, error: str) -> dict[str, Any]:
    return _segment_result(segment_id, kind, "failed", error=error)


def _price_or_none(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    return Price.model_validate(raw).model_dump()


def normalize_provider_result(raw: object, segment_id: str, kind: str) -> dict[str, Any]:
    """Force the sibling payload onto the booking-result contract.

    Sandbox confirmation codes must start with ``SANDBOX-``. Any other code is
    dropped. A ``booked`` result that is not sandbox becomes ``failed`` so a
    live ticket number can never be returned from this agent.
    """

    if not isinstance(raw, dict):
        return _failed(segment_id, kind, "invalid_provider_result")
    status = raw.get("status")
    if status not in ("booked", "failed", "needs_user"):
        return _failed(segment_id, kind, "invalid_provider_result")

    code = raw.get("confirmationCode")
    if code is not None and not isinstance(code, str):
        code = None
    sandbox = isinstance(code, str) and code.startswith("SANDBOX-")
    if code is not None and not sandbox:
        code = None

    error = raw.get("error")
    if error is not None and not isinstance(error, str):
        error = "invalid_provider_result"

    if status != "booked":
        if status == "failed" and not error:
            error = "provider_error"
        return _segment_result(
            segment_id,
            kind,
            status,
            confirmation_code=code,
            price=None,
            error=error,
        )

    if not sandbox:
        return _failed(segment_id, kind, "non_sandbox_confirmation")
    try:
        price = _price_or_none(raw.get("price"))
    except (TypeError, ValueError):
        return _failed(segment_id, kind, "invalid_price")
    return _segment_result(
        segment_id,
        kind,
        "booked",
        confirmation_code=code,
        price=price,
        error=None,
    )


def supplier_hostname() -> str:
    """Amadeus host the providers may use. Empty means the sandbox default."""

    return os.environ.get("AMADEUS_HOSTNAME", "").strip().lower()


def supplier_calls_allowed() -> bool:
    """Sandbox is the default. A production hostname is never called."""

    host = supplier_hostname()
    return host in ("", SANDBOX_HOSTNAME)


def _call(kind: str, segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    segment_id = str(segment.get("segmentId") or "")
    if not supplier_calls_allowed():
        return _failed(segment_id, kind, PRODUCTION_REFUSED)
    book = load_book(kind)
    if book is None:
        return _not_installed(segment_id, kind)
    try:
        raw = book(segment, travelers, trip_id)
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        return _failed(segment_id, kind, message)
    return normalize_provider_result(raw, segment_id, kind)


def book_flight(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    """Book one flight. Provider: Amadeus Flight Offers Search and Flight Create Orders."""

    return _call("flight", segment, travelers, trip_id)


def book_hotel(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    """Book one stay. Provider: Amadeus Hotel Search and Hotel Booking."""

    return _call("hotel", segment, travelers, trip_id)


def book_attraction(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    """Book one attraction. Provider: Amadeus Tours and Activities."""

    return _call("attraction", segment, travelers, trip_id)


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="book_flight",
        kind="flight",
        description=(
            "Book one flight segment. Calls booking.providers.flights.book, which uses "
            "Amadeus Flight Offers Search and Flight Create Orders on the test host."
        ),
        fn=book_flight,
    ),
    Tool(
        name="book_hotel",
        kind="hotel",
        description=(
            "Book one hotel segment. Calls booking.providers.hotels.book, which uses "
            "Amadeus Hotel Search and Hotel Booking on the test host."
        ),
        fn=book_hotel,
    ),
    Tool(
        name="book_attraction",
        kind="attraction",
        description=(
            "Book one attraction segment. Calls booking.providers.attractions.book, which uses "
            "Amadeus Tours and Activities on the test host."
        ),
        fn=book_attraction,
    ),
)

TOOLS_BY_KIND: dict[str, Tool] = {tool.kind: tool for tool in TOOLS}


def invoke_tool(kind: str, segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    """Run the registered tool for this segment kind."""

    return TOOLS_BY_KIND[kind].fn(segment, travelers, trip_id)


def register_booking_tools(app: Any) -> dict[str, Tool]:
    """Register book_flight, book_hotel, and book_attraction on the runtime."""

    registered = {tool.name: tool for tool in TOOLS}
    app.booking_tools = registered
    return registered
