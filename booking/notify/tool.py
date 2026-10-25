"""AgentCore tool spec for ``trip_notice``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
after a replan or a refused overcharge so the traveler gets one message.
This module does not run that loop and does not deliver the message.
Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When
the runtime hands back a ``trip_notice`` call, run ``handler``. ``handler``
calls ``trip_notice``.
"""

from __future__ import annotations

from .notice import trip_notice

TOOL_NAME = "trip_notice"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip id, the event that happened, notes to include in the one traveler "
        "message, and the segment id when the event is about one segment."
    ),
    "properties": {
        "tripId": {"type": "string"},
        "event": {
            "type": "string",
            "enum": [
                "cancelled",
                "ended_early",
                "ended_late",
                "booked",
                "over_capture_rejected",
            ],
            "description": (
                "cancelled, ended_early, or ended_late after a replan. "
                "booked after a booking. over_capture_rejected when a charge "
                "above the authorized amount was refused."
            ),
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each note is included in the subject and the body. An empty list is allowed.",
        },
        "segmentId": {
            "type": "string",
            "description": "Segment this notice is about. Empty when the event is not about one segment.",
        },
    },
    "required": ["tripId", "event", "notes", "segmentId"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": "One traveler message. Nothing is delivered.",
    "properties": {
        "tripId": {"type": "string"},
        "subject": {"type": "string", "description": "Names the event and includes each note."},
        "body": {"type": "string", "description": "Names the event and includes each note."},
    },
    "required": ["tripId", "subject", "body"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Build one traveler message after a replan or a refused overcharge. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime "
        "so the traveler gets one message. This tool does not run that loop and "
        "does not deliver the message. The subject and body name the event and "
        "include each note. Empty notes still return a subject and a body. "
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
    """AgentCore runtime entry for ``trip_notice``. Calls ``trip_notice``."""
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_NAME:
        return {
            "tripId": "",
            "subject": "Ignored a different tool",
            "body": "This call was not trip_notice, so no traveler message was built.",
        }
    return trip_notice(tool_input)


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
