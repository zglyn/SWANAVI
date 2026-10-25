"""AgentCore tool spec for ``replan_early``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when a segment ends early. This module does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the
runtime hands back a ``replan_early`` call, run ``handler``. ``handler``
calls ``replan_early``.
"""

from __future__ import annotations

from .replan import idle_result, replan_early

TOOL_NAME = "replan_early"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip id, caller-supplied instant, trip plan, and the early-finish disruption. "
        "This tool does not read the wall clock."
    ),
    "properties": {
        "tripId": {"type": "string", "description": "Trip id. A missing id does not raise."},
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
            "description": "The segment that ended early.",
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {"type": "string", "description": "flight, hotel, or attraction."},
                "event": {"type": "string", "description": "ended_early", "enum": ["ended_early"]},
                "deltaMinutes": {
                    "type": "number",
                    "description": "How many minutes early the segment ended. Zero or less leaves the plan unchanged.",
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
        "event": {"type": "string", "enum": ["ended_early"]},
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
        "Replan the rest of a day when a segment ends early. The master agent calls this "
        "tool on the Amazon Bedrock AgentCore runtime when a segment ends early. This tool "
        "does not run the master loop, book segments, check email, or replan a cancellation "
        "or a late segment. Sandbox only: it keeps the finished segment and shifts later "
        "same-day segments earlier by deltaMinutes, not so they start before now, and does "
        "not use the network or AWS."
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
    """AgentCore runtime entry for ``replan_early``. Calls ``replan_early``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return idle_result(tool_input, "unsupported AgentCore tool; expected replan_early")
        return replan_early(tool_input)
    except Exception:
        return idle_result(None, "replan_early could not read its input")


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
