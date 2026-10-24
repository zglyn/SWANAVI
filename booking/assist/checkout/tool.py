"""AgentCore tool spec for ``late_checkout``.

The master calls this tool on Amazon Bedrock AgentCore on departure morning
so the room is held when the flight is late in the day. This module does not
run that loop. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness
invoke). When the runtime hands back a ``late_checkout`` call, run ``handler``.
``handler`` calls ``late_checkout``.
"""

from __future__ import annotations

from .checkout import REASON_UNREADABLE, late_checkout

TOOL_NAME = "late_checkout"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Hotel segment, scheduled checkout, flight departure, and the traveler. "
        "The master calls this on departure morning. Times are ISO-8601."
    ),
    "properties": {
        "hotelSegmentId": {
            "type": "string",
            "description": "Hotel segment whose room may be held past checkout.",
        },
        "checkoutAt": {
            "type": "string",
            "description": "Scheduled hotel checkout, ISO-8601.",
        },
        "departAt": {
            "type": "string",
            "description": "Flight departure, ISO-8601.",
        },
        "travelerName": {
            "type": "string",
            "description": "Traveler named in the reason when a late checkout is requested.",
        },
    },
    "required": ["hotelSegmentId", "checkoutAt", "departAt", "travelerName"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "hotelSegmentId": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["requested", "not_needed", "failed"],
        },
        "until": {
            "type": ["string", "null"],
            "description": (
                "ISO-8601 time the room is held until when status is requested: "
                "checkoutAt plus 2 hours. Null otherwise."
            ),
        },
        "reason": {
            "type": "string",
            "description": "Names the traveler when status is requested.",
        },
    },
    "required": ["hotelSegmentId", "status", "until", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Request a two-hour late hotel checkout when the flight leaves more than "
        "2 hours after checkout. The master calls this tool on Amazon Bedrock "
        "AgentCore on departure morning so the room is held when the flight is "
        "late in the day. This tool does not run that loop and does not contact "
        "the hotel. If departAt is more than 2 hours after checkoutAt, status is "
        "requested and until is checkoutAt plus 2 hours. The reason names the "
        "traveler. If departAt is within 2 hours after checkout or before it, "
        "status is not_needed. Missing times return status failed. Never raises. "
        "Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``late_checkout``. Calls ``late_checkout``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "hotelSegmentId": "",
                "status": "failed",
                "until": None,
                "reason": "ignored tool call for a different tool",
            }
        return late_checkout(tool_input)
    except Exception:
        return {
            "hotelSegmentId": "",
            "status": "failed",
            "until": None,
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
