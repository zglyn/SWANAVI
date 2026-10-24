"""Amazon Bedrock AgentCore tool for hotel booking.

The only supported invoke path is the AgentCore runtime. The runtime calls
``handler`` with the tool input. ``handler`` calls ``book``.
"""

from __future__ import annotations

from .book import book

TOOL_SPEC = {
    "name": "book_hotel",
    "description": (
        "Book one hotel segment for a trip. The only supported invoke path "
        "is the Amazon Bedrock AgentCore runtime. Input is the hotel segment, "
        "the travelers, and trip_id."
    ),
    "inputSchema": {
        "type": "object",
        "description": "Hotel segment plus the travelers and trip id.",
        "properties": {
            "segment": {
                "type": "object",
                "description": "Hotel segment from the trip plan.",
                "properties": {
                    "segmentId": {"type": "string"},
                    "kind": {"type": "string", "description": 'Must be "hotel".'},
                    "city": {"type": "string"},
                    "checkIn": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                    "checkOut": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                    "rooms": {"type": "integer"},
                    "guests": {"type": "integer"},
                    "cityCode": {
                        "type": "string",
                        "description": "Optional IATA city code for Amadeus Hotel Search.",
                    },
                    "hotelId": {
                        "type": "string",
                        "description": "Optional Amadeus hotel id for Hotel Search.",
                    },
                },
                "required": ["segmentId", "kind", "city", "checkIn", "checkOut", "rooms", "guests"],
            },
            "travelers": {
                "type": "array",
                "description": "Travelers on the trip. Each item is a name or an object with a name.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                },
            },
            "trip_id": {"type": "string", "description": "Trip id."},
        },
        "required": ["segment", "travelers", "trip_id"],
    },
    "outputSchema": {
        "type": "object",
        "description": "Hotel booking result. Sandbox confirmation codes start with SANDBOX-.",
        "properties": {
            "segmentId": {"type": "string"},
            "kind": {"type": "string"},
            "status": {"type": "string", "description": "booked, failed, or needs_user."},
            "confirmationCode": {"type": "string"},
            "price": {
                "type": "object",
                "properties": {
                    "amount": {"type": "string"},
                    "currency": {"type": "string"},
                },
            },
            "error": {"type": "string"},
        },
        "required": ["segmentId", "kind", "status", "confirmationCode", "price", "error"],
    },
}


def handler(event, context=None):
    """AgentCore runtime entry. Calls ``book`` with the tool input.

    AgentCore Gateway passes ``inputSchema`` properties as ``event``.
    A tool name on the context must be ``book_hotel`` when AgentCore sets one.
    """
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_SPEC["name"]:
        return {
            "segmentId": None,
            "kind": "hotel",
            "status": "failed",
            "confirmationCode": None,
            "price": None,
            "error": "unsupported AgentCore tool; expected book_hotel",
        }
    segment, travelers, trip_id = _tool_input(event)
    return book(segment, travelers, trip_id)


def _tool_input(event: object) -> tuple[dict, list, str]:
    payload = event
    if isinstance(event, dict) and isinstance(event.get("arguments"), dict):
        payload = event["arguments"]
    if not isinstance(payload, dict):
        return {}, [], ""
    segment = payload.get("segment")
    travelers = payload.get("travelers")
    trip_id = payload.get("trip_id", payload.get("tripId"))
    return (
        segment if isinstance(segment, dict) else {},
        travelers if isinstance(travelers, list) else [],
        trip_id if isinstance(trip_id, str) else "",
    )


def _tool_name(context: object) -> str | None:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None)
    if not isinstance(custom, dict):
        return None
    raw = custom.get("bedrockAgentCoreToolName")
    if not isinstance(raw, str) or not raw.strip():
        return None
    # Gateway tool names are "{target}___{tool}".
    if "___" in raw:
        return raw.split("___", 1)[1]
    return raw.strip()
