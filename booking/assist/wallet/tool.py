"""AgentCore tool spec for ``trip_wallet``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
at the end of a tick so the traveler has one list of booking, refund, and
ride codes. This module does not run that loop. Register ``TOOL_SPEC`` (or
pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime hands back a
``trip_wallet`` call, run ``handler``. ``handler`` calls ``trip_wallet``.
"""

from __future__ import annotations

from .wallet import trip_wallet

TOOL_NAME = "trip_wallet"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip id and the booking, refund, and ride items to list. "
        "The master calls this at the end of a tick. "
        "This tool does not book, refund, or request a ride."
    ),
    "properties": {
        "tripId": {"type": "string"},
        "items": {
            "type": "array",
            "description": (
                "Codes already on the trip. An empty list returns count 0. "
                "An item with no code is left off the list."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": ["string", "null"],
                        "description": "booking, refund, or ride. Null is left off the line.",
                    },
                    "segmentId": {
                        "type": ["string", "null"],
                        "description": "Segment this code belongs to. Null is left off the line.",
                    },
                    "code": {
                        "type": ["string", "null"],
                        "description": "Booking, refund, or ride code. Missing codes are omitted.",
                    },
                    "amount": {
                        "description": "Decimal string or number. Null is left off the line.",
                    },
                    "currency": {
                        "type": ["string", "null"],
                        "description": "Currency code. Null is left off the line.",
                    },
                },
            },
        },
    },
    "required": ["tripId", "items"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": "One list of codes for the traveler. Nothing is booked or sent.",
    "properties": {
        "tripId": {"type": "string"},
        "lines": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each line is kind, segmentId, code, amount, and currency, skipping nulls.",
        },
        "count": {
            "type": "integer",
            "description": "Number of items that have a code. Same as the number of lines.",
        },
    },
    "required": ["tripId", "lines", "count"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "List booking, refund, and ride codes for one trip. The master agent "
        "calls this tool on the Amazon Bedrock AgentCore runtime at the end of "
        "a tick so the traveler has one list of booking, refund, and ride codes. "
        "This tool does not run that loop. Each line is kind, segment id, code, "
        "amount, and currency, skipping nulls. An item with no code is left off "
        "the list and out of the count. Empty items return count 0 and an empty "
        "list. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``trip_wallet``. Calls ``trip_wallet``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {"tripId": "", "lines": [], "count": 0}
        return trip_wallet(tool_input)
    except Exception:
        return {"tripId": "", "lines": [], "count": 0}


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
