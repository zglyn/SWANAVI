"""AgentCore tool spec for ``rebook_segment``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
after one segment is cancelled. This module does not run that loop and does
not call the planner. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on
harness invoke). When the runtime hands back a ``rebook_segment`` call, run
``handler``. ``handler`` calls ``rebook_segment``.
"""

from __future__ import annotations

from .rebook import REASON_UNREADABLE, rebook_segment

TOOL_NAME = "rebook_segment"

_PRICE = {
    "type": ["object", "null"],
    "description": "Copied from the segment when it has amount and currency. Otherwise null.",
    "properties": {
        "amount": {"type": "string", "description": "Decimal string such as 248.00."},
        "currency": {"type": "string"},
    },
}

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "One flight, hotel, or attraction to replace on the same day when it is cancelled. "
        "The caller supplies now. This tool does not look up the segment and does not call the planner."
    ),
    "properties": {
        "tripId": {"type": "string", "description": "Trip the segment belongs to."},
        "now": {
            "type": "string",
            "description": "ISO-8601 instant from the caller, in UTC (Z). A numeric offset is the same instant.",
        },
        "segment": {
            "type": "object",
            "description": (
                "Flight fields are segmentId, kind, from, to, and departDate. "
                "Hotel fields are segmentId, kind, city, checkIn, and checkOut. "
                "Attraction fields are segmentId, kind, name, city, date, and time."
            ),
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {"type": "string", "enum": ["flight", "hotel", "attraction"]},
                "from": {"type": "string", "description": "Flight origin. Kept as given."},
                "to": {"type": "string", "description": "Flight destination. Kept as given."},
                "departDate": {"type": "string", "description": "Flight departure date, YYYY-MM-DD."},
                "returnDate": {"type": "string", "description": "Return date YYYY-MM-DD. Omit for a one-way flight."},
                "cabin": {"type": "string"},
                "travelerIds": {"type": "array", "items": {"type": "string"}},
                "city": {"type": "string", "description": "Hotel or attraction city. Kept as given."},
                "checkIn": {"type": "string", "description": "Hotel check-in date, YYYY-MM-DD."},
                "checkOut": {"type": "string", "description": "Hotel check-out date, YYYY-MM-DD."},
                "rooms": {"type": "integer"},
                "guests": {"type": "integer"},
                "name": {"type": "string", "description": "Attraction name. Kept as given."},
                "date": {"type": "string", "description": "Attraction date, YYYY-MM-DD."},
                "time": {"type": "string", "description": "Attraction time, HH:MM."},
                "partySize": {"type": "integer"},
                "price": _PRICE,
            },
            "required": ["segmentId", "kind"],
        },
        "travelers": {
            "type": "array",
            "description": "Party on the segment. Kept. Card and payment fields are not read.",
            "items": {"type": "object"},
        },
        "cancelled": {
            "type": "boolean",
            "description": "True when this segment was cancelled and should be replaced.",
        },
    },
    "required": ["tripId", "now", "segment", "travelers", "cancelled"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "changed": {
            "type": "boolean",
            "description": "True only when cancelled is true and a replacement was booked.",
        },
        "reason": {
            "type": "string",
            "enum": ["not_cancelled", "rebooked", "unreadable"],
        },
        "replacement": {
            "type": ["object", "null"],
            "description": "Null when the segment is not cancelled. Otherwise the same segment, booked again.",
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {"type": "string", "enum": ["flight", "hotel", "attraction"]},
                "status": {"type": "string", "description": "booked"},
                "confirmationCode": {
                    "type": "string",
                    "description": "Sandbox codes start with SANDBOX-RB-.",
                },
                "price": _PRICE,
                "error": {"type": "null"},
            },
            "required": ["segmentId", "kind", "status", "confirmationCode", "price", "error"],
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["segmentId", "changed", "reason", "replacement", "notes"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Replace one cancelled segment with the same kind on the same day. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime. "
        "Sandbox only: no network and no airline or hotel API. "
        "Keep the same segmentId, kind, cities, and party. "
        "A future start stays. A past start becomes now plus 30 minutes, written on "
        "departDate, checkIn, or attraction date and time. "
        "confirmation codes start with SANDBOX-RB-. status is booked. "
        "This tool does not build a new itinerary, change city, or add stops, and it does not call the planner. "
        "A later integrator wires the master."
    ),
    "inputSchema": INPUT_SCHEMA,
    "outputSchema": OUTPUT_SCHEMA,
}

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


def handler(tool_input: dict | str | None = None, context: object = None) -> dict:
    """AgentCore runtime entry for ``rebook_segment``. Calls ``rebook_segment``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "changed": False,
                "reason": REASON_UNREADABLE,
                "replacement": None,
                "notes": ["ignored tool call for a different tool"],
            }
        return rebook_segment(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "changed": False,
            "reason": REASON_UNREADABLE,
            "replacement": None,
            "notes": ["rebook_segment could not read the input"],
        }


def _tool_name(context: object) -> str | None:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None)
    if not isinstance(custom, dict):
        return None
    raw = custom.get("bedrockAgentCoreToolName")
    if not isinstance(raw, str) or not raw.strip():
        return None
    if "___" in raw:
        return raw.split("___", 1)[1]
    return raw.strip()
