"""AgentCore tool spec for ``luggage_drop``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when a flight lands before hotel check-in. This module does not run that
loop. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke).
When the runtime hands back a ``luggage_drop`` call, run ``handler``.
``handler`` calls ``luggage_drop``.
"""

from __future__ import annotations

from .drop import REASON_UNREADABLE, luggage_drop

TOOL_NAME = "luggage_drop"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Hotel segment, traveler, flight arrival, and hotel check-in. "
        "The master calls this when a flight lands before hotel check-in. "
        "This tool does not book the hotel and does not call the desk."
    ),
    "properties": {
        "hotelSegmentId": {"type": "string"},
        "travelerName": {
            "type": "string",
            "description": "Name the desk note uses when a bag hold is requested.",
        },
        "arriveAt": {
            "type": "string",
            "description": "ISO-8601 arrival time. This tool does not read the wall clock.",
        },
        "checkInAt": {
            "type": "string",
            "description": "ISO-8601 hotel check-in time.",
        },
    },
    "required": ["hotelSegmentId", "travelerName", "arriveAt", "checkInAt"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "hotelSegmentId": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["drop_requested", "not_needed", "failed"],
        },
        "deskNote": {
            "type": "string",
            "description": (
                "Asks the desk to hold bags for the traveler until checkInAt "
                "when status is drop_requested. Empty otherwise."
            ),
        },
        "reason": {
            "type": ["string", "null"],
            "description": "Why the drop failed. Null when status is drop_requested or not_needed.",
        },
    },
    "required": ["hotelSegmentId", "status", "deskNote", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Ask a hotel desk to hold bags when a flight lands before check-in. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime "
        "when a flight lands before hotel check-in. This tool does not run that loop "
        "and does not book the hotel. An arriveAt before checkInAt returns status "
        "drop_requested and a desk note that names the traveler and asks the desk to "
        "hold bags until checkInAt. An arriveAt at or after checkInAt returns status "
        "not_needed. A missing time returns status failed and a reason. Sandbox only: "
        "no network and no AWS."
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
    """AgentCore runtime entry for ``luggage_drop``. Calls ``luggage_drop``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "hotelSegmentId": "",
                "status": "failed",
                "deskNote": "",
                "reason": "ignored tool call for a different tool",
            }
        return luggage_drop(tool_input)
    except Exception:
        return {
            "hotelSegmentId": "",
            "status": "failed",
            "deskNote": "",
            "reason": REASON_UNREADABLE,
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
