"""Booking tools invoked by the AgentCore runtime entrypoint.

These are ordinary Python tools. Browser, code interpreter, and payment tools
are not registered: a booking step does not need them, and this agent never
charges a card.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from booking.contract import Price, SegmentResult
from booking.orchestrator.providers import NOT_INSTALLED, load_book

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


def _call(kind: str, segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    segment_id = str(segment.get("segmentId") or "")
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
    """Book one flight segment via booking.providers.flights.book."""

    return _call("flight", segment, travelers, trip_id)


def book_hotel(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    """Book one hotel segment via booking.providers.hotels.book."""

    return _call("hotel", segment, travelers, trip_id)


def book_attraction(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    """Book one attraction segment via booking.providers.attractions.book."""

    return _call("attraction", segment, travelers, trip_id)


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="book_flight",
        kind="flight",
        description="Book one flight segment from the finished trip plan. Sandbox providers only.",
        fn=book_flight,
    ),
    Tool(
        name="book_hotel",
        kind="hotel",
        description="Book one hotel segment from the finished trip plan. Sandbox providers only.",
        fn=book_hotel,
    ),
    Tool(
        name="book_attraction",
        kind="attraction",
        description="Book one attraction segment from the finished trip plan. Sandbox providers only.",
        fn=book_attraction,
    ),
)

TOOLS_BY_KIND: dict[str, Tool] = {tool.kind: tool for tool in TOOLS}


def invoke_tool(kind: str, segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    """Run the tool for this segment kind. Provider exceptions stay inside the tool."""

    return TOOLS_BY_KIND[kind].fn(segment, travelers, trip_id)
