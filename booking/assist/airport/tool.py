"""AgentCore tool spec for ``airport_leave``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
the morning of a flight. This module does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime
hands back an ``airport_leave`` call, run ``handler``. ``handler`` calls
``airport_leave``.
"""

from __future__ import annotations

from .leave import REASON_UNREADABLE, airport_leave

TOOL_NAME = "airport_leave"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "One flight the traveler must leave for, and the hotel checkout when there is one. "
        "The caller supplies the departure time. This tool does not look up a flight."
    ),
    "properties": {
        "flightSegmentId": {
            "type": "string",
            "description": "Flight segment the traveler is leaving for.",
        },
        "departAt": {
            "type": "string",
            "description": "ISO-8601 departure time supplied by the caller.",
        },
        "international": {
            "type": "boolean",
            "description": "True for an international flight (3 hour buffer). False for domestic (2 hour buffer).",
        },
        "hotelCheckoutAt": {
            "type": ["string", "null"],
            "description": "ISO-8601 hotel checkout. Null when there is no checkout to compare.",
        },
    },
    "required": ["flightSegmentId", "departAt", "international"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "flightSegmentId": {"type": "string"},
        "leaveBy": {
            "type": "string",
            "description": "ISO-8601 time to leave. Empty when departAt cannot be read.",
        },
        "ok": {
            "type": "boolean",
            "description": "False when departAt is missing or hotel checkout is after leaveBy.",
        },
        "reason": {"type": "string"},
    },
    "required": ["flightSegmentId", "leaveBy", "ok", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Say when to leave a hotel for a flight. The master agent calls this tool "
        "on the Amazon Bedrock AgentCore runtime the morning of a flight. "
        "An international flight needs 3 hours. A domestic flight needs 2 hours. "
        "leaveBy is departAt minus that buffer. ok is false when hotel checkout is "
        "after leaveBy, because the traveler would still be at the hotel. "
        "Sandbox only: no airline API, no network, and no AWS."
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
    """AgentCore runtime entry for ``airport_leave``. Calls ``airport_leave``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "flightSegmentId": "",
                "leaveBy": "",
                "ok": False,
                "reason": "unsupported AgentCore tool; expected airport_leave",
            }
        return airport_leave(tool_input)
    except Exception:
        return {
            "flightSegmentId": "",
            "leaveBy": "",
            "ok": False,
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
