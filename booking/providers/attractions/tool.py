"""Amazon Bedrock AgentCore tool for attraction tickets.

The only supported invoke path is the AgentCore runtime. It passes the
attraction segment, travelers, and trip_id to ``book_attraction``, which calls
``book()``.
"""

from __future__ import annotations

from .book import book

BOOK_ATTRACTION_TOOL = {
    "name": "book_attraction",
    "description": (
        "Book one attraction segment from a finished trip plan. "
        "The only supported invoke path is the Amazon Bedrock AgentCore runtime. "
        "Input is the attraction segment plus travelers and trip_id. "
        "The handler calls book(). Sandbox confirmation codes start with SANDBOX-. "
        "Set ROAM_ATTRACTION_PROVIDER=live to use Amadeus Tours and Activities "
        "on the Amadeus test host. That client does not hit production and does not charge a card."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "segment": {
                "type": "object",
                "description": "Attraction segment from the trip plan.",
                "properties": {
                    "segmentId": {"type": "string"},
                    "kind": {"type": "string", "description": 'Must be "attraction".'},
                    "name": {"type": "string"},
                    "city": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "partySize": {"type": "integer"},
                    "time": {"type": "string", "description": "HH:MM, or omit when unknown."},
                },
                "required": ["segmentId", "kind", "name", "city", "date", "partySize"],
            },
            "travelers": {
                "type": "array",
                "description": "Travelers on the trip. Card and payment fields are refused.",
                "items": {"type": "object"},
            },
            "trip_id": {"type": "string"},
        },
        "required": ["segment", "travelers", "trip_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "segmentId": {"type": "string"},
            "kind": {"type": "string"},
            "status": {"type": "string", "description": "booked, failed, or needs_user"},
            "confirmationCode": {
                "type": "string",
                "description": "Present when booked. Sandbox codes start with SANDBOX-.",
            },
            "price": {
                "type": "object",
                "properties": {
                    "amount": {"type": "string"},
                    "currency": {"type": "string"},
                },
            },
            "error": {"type": "string"},
        },
        "required": ["segmentId", "kind", "status"],
    },
}


def book_attraction(segment: dict, travelers: list, trip_id: str) -> dict:
    """AgentCore handler for ``book_attraction``. Calls ``book()``.

    Invoke this only from the Amazon Bedrock AgentCore runtime.
    """
    return book(segment, travelers, trip_id)
