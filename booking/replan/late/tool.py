"""AgentCore tool spec for ``replan_late``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when a segment ends late. This module does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime
hands back a ``replan_late`` call, run ``handler``. ``handler`` calls
``replan_late``.
"""

from __future__ import annotations

from .replan import replan_late

TOOL_NAME = "replan_late"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip id, caller-supplied instant, trip plan, and the late-finish disruption. "
        "A partial plan is accepted and does not raise."
    ),
    "properties": {
        "tripId": {"type": "string", "description": "Id of the trip being replanned."},
        "now": {
            "type": "string",
            "description": "ISO-8601 timestamp supplied by the caller. This tool does not read the wall clock.",
        },
        "plan": {
            "type": "object",
            "description": "Trip plan. A partial plan is accepted and does not raise.",
            "properties": {
                "tripId": {"type": "string"},
                "flights": {"type": "array", "items": {"type": "object"}},
                "hotels": {"type": "array", "items": {"type": "object"}},
                "attractions": {"type": "array", "items": {"type": "object"}},
            },
        },
        "disruption": {
            "type": "object",
            "description": "The segment that ended late, and by how many minutes.",
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {"type": "string", "description": "flight, hotel, or attraction."},
                "event": {"type": "string", "enum": ["ended_late"]},
                "deltaMinutes": {
                    "type": "number",
                    "description": "Minutes the segment finished after its scheduled end. Zero or less leaves the plan unchanged.",
                },
            },
            "required": ["segmentId", "kind", "event", "deltaMinutes"],
        },
    },
    "required": ["tripId", "now", "plan", "disruption"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "event": {"type": "string", "enum": ["ended_late"]},
        "changed": {"type": "boolean"},
        "plan": {
            "type": "object",
            "properties": {
                "flights": {"type": "array", "items": {"type": "object"}},
                "hotels": {"type": "array", "items": {"type": "object"}},
                "attractions": {"type": "array", "items": {"type": "object"}},
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["segmentId", "event", "changed", "plan", "notes"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Shift later same-day segments when a segment ends late. The master agent "
        "calls this tool on the Amazon Bedrock AgentCore runtime when a segment ends late. "
        "Sandbox only: the caller supplies now, and the tool does not use the network or AWS. "
        "The finished segment stays in place. deltaMinutes of zero or less leaves the plan unchanged."
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
    """AgentCore runtime entry for ``replan_late``. Calls ``replan_late``."""
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_NAME:
        return {
            "segmentId": "",
            "event": "ended_late",
            "changed": False,
            "plan": {"flights": [], "hotels": [], "attractions": []},
            "notes": ["unsupported AgentCore tool; expected replan_late"],
        }
    return replan_late(tool_input)


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
