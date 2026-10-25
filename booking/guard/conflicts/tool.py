"""AgentCore tool spec for ``check_conflicts``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
after a replan. This module does not run that loop. Register ``TOOL_SPEC``
(or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime hands back
a ``check_conflicts`` call, run ``handler``. ``handler`` calls
``check_conflicts``.
"""

from __future__ import annotations

from .conflicts import check_conflicts

TOOL_NAME = "check_conflicts"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Caller-supplied instant and the trip plan to check. "
        "A partial plan is accepted and does not raise."
    ),
    "properties": {
        "now": {
            "type": "string",
            "description": (
                "ISO-8601 timestamp supplied by the caller. This tool does not read the wall clock "
                "and does not drop segments because of this instant."
            ),
        },
        "plan": {
            "type": "object",
            "description": (
                "Trip plan. flights, hotels, and attractions carry start and end ISO datetimes. "
                "A partial plan is accepted and does not raise."
            ),
            "properties": {
                "tripId": {"type": "string"},
                "flights": {"type": "array", "items": {"type": "object"}},
                "hotels": {"type": "array", "items": {"type": "object"}},
                "attractions": {"type": "array", "items": {"type": "object"}},
            },
        },
    },
    "required": ["now", "plan"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segmentA": {
                        "type": "string",
                        "description": "segmentId of the earlier segment in plan order (flights, then hotels, then attractions).",
                    },
                    "segmentB": {
                        "type": "string",
                        "description": "segmentId of the later segment in plan order.",
                    },
                    "overlapMinutes": {
                        "type": "number",
                        "description": "Length of the [start, end) intersection in minutes. Touching endpoints are not an overlap.",
                    },
                },
                "required": ["segmentA", "segmentB", "overlapMinutes"],
            },
        },
    },
    "required": ["conflicts"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Report schedule conflicts on a trip plan. The master agent calls this tool "
        "on the Amazon Bedrock AgentCore runtime after a replan. Sandbox only: the caller "
        "supplies now, and the tool does not use the network or AWS. Two segments conflict "
        "when their [start, end) windows overlap. Touching endpoints do not conflict. "
        "A segment with removed true is ignored. A partial plan does not raise."
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
    """AgentCore runtime entry for ``check_conflicts``. Calls ``check_conflicts``."""
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_NAME:
        return {"conflicts": []}
    return check_conflicts(tool_input)


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
