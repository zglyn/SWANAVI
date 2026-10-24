"""AgentCore tool spec for `book_flight`.

The only supported invoke path is the Amazon Bedrock AgentCore runtime.
Register `TOOL_SPEC` (or pass `AGENTCORE_TOOL` on harness invoke). When the
runtime hands back a `book_flight` call, run `handler`. `handler` calls `book`.
"""

from __future__ import annotations

import json

from .book import book
from .result import booking_result

TOOL_NAME = "book_flight"

INPUT_SCHEMA = {
    "type": "object",
    "description": "Flight segment from the trip plan, the travelers on it, and the trip id.",
    "properties": {
        "segment": {
            "type": "object",
            "description": "One flight segment.",
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {"type": "string", "description": "Must be flight."},
                "from": {"type": "string", "description": "Origin IATA code."},
                "to": {"type": "string", "description": "Destination IATA code."},
                "departDate": {"type": "string", "description": "Departure date, YYYY-MM-DD."},
                "returnDate": {
                    "type": "string",
                    "description": "Return date YYYY-MM-DD. Omit for a one-way flight.",
                },
                "cabin": {
                    "type": "string",
                    "description": "economy, premium_economy, business, or first.",
                },
                "travelerIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ids of travelers on this segment.",
                },
            },
            "required": ["segmentId", "kind", "from", "to", "departDate", "cabin", "travelerIds"],
        },
        "travelers": {
            "type": "array",
            "description": "Traveler profiles. Live Amadeus booking also needs dateOfBirth, gender, email, countryCallingCode, and phoneNumber.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "givenName": {"type": "string"},
                    "familyName": {"type": "string"},
                    "name": {"type": "string"},
                    "dateOfBirth": {"type": "string", "description": "YYYY-MM-DD."},
                    "gender": {"type": "string", "description": "MALE, FEMALE, UNSPECIFIED, or UNDISCLOSED."},
                    "email": {"type": "string"},
                    "countryCallingCode": {"type": "string"},
                    "phoneNumber": {"type": "string"},
                },
                "required": ["id"],
            },
        },
        "trip_id": {"type": "string", "description": "Id of the finished trip plan."},
    },
    "required": ["segment", "travelers", "trip_id"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Flight booking result. confirmationCode and price are absent in value when status is not booked.",
    "properties": {
        "segmentId": {"type": "string"},
        "kind": {"type": "string", "description": "flight"},
        "status": {"type": "string", "description": "booked, failed, or needs_user."},
        "confirmationCode": {
            "type": "string",
            "description": "Sandbox codes start with SANDBOX-. Null when not booked.",
        },
        "price": {
            "type": "object",
            "properties": {
                "amount": {"type": "string", "description": "Decimal string such as 248.00."},
                "currency": {"type": "string"},
            },
        },
        "error": {"type": "string", "description": "Null when booked."},
    },
    "required": ["segmentId", "kind", "status"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Book one flight segment for a trip. Pass segment, travelers, and trip_id. "
        "The only supported invoke path is the Amazon Bedrock AgentCore runtime."
    ),
    "inputSchema": INPUT_SCHEMA,
    "outputSchema": OUTPUT_SCHEMA,
}

# Inline function the orchestrator can pass to the AgentCore harness.
AGENTCORE_TOOL = {
    "type": "inline_function",
    "name": TOOL_NAME,
    "config": {
        "inlineFunction": {
            "description": TOOL_SPEC["description"],
            "inputSchema": INPUT_SCHEMA,
        }
    },
}


def handler(tool_input: dict | str, context: object = None) -> dict:
    """AgentCore runtime entry for `book_flight`. Calls `book`."""
    del context
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            return booking_result(None, "failed", error="book_flight input was not valid JSON")
    if not isinstance(tool_input, dict):
        return booking_result(None, "failed", error="book_flight input must be an object")
    return book(tool_input.get("segment"), tool_input.get("travelers"), tool_input.get("trip_id"))
