"""AgentCore tool spec for ``replan_cancel``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when a segment is cancelled. This module does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the
runtime hands back a ``replan_cancel`` call, run ``handler``. ``handler``
calls ``replan_cancel``.
"""

from __future__ import annotations

from .cancel import replan_cancel

TOOL_NAME = "replan_cancel"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip id, caller-supplied instant, trip plan, and the cancelled segment. "
        "This tool does not read the wall clock."
    ),
    "properties": {
        "tripId": {"type": "string"},
        "now": {
            "type": "string",
            "description": "ISO-8601 timestamp supplied by the caller. This tool does not read the wall clock.",
        },
        "plan": {
            "type": "object",
            "description": "Trip plan. A partial plan is accepted and does not raise.",
            "properties": {
                "flights": {"type": "array", "items": {"type": "object"}},
                "hotels": {"type": "array", "items": {"type": "object"}},
                "attractions": {"type": "array", "items": {"type": "object"}},
            },
        },
        "disruption": {
            "type": "object",
            "description": "The segment the master is cancelling.",
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {
                    "type": "string",
                    "description": "flight, hotel, or attraction.",
                },
                "event": {
                    "type": "string",
                    "enum": ["cancelled"],
                },
                "deltaMinutes": {
                    "description": "Integer minutes, or null. Accepted and ignored. The shift is the cancelled segment's duration.",
                },
            },
            "required": ["segmentId", "kind", "event"],
        },
    },
    "required": ["tripId", "now", "plan", "disruption"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "event": {"type": "string", "enum": ["cancelled"]},
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
        "Replan the rest of a day after one segment is cancelled. The master agent "
        "calls this tool on the Amazon Bedrock AgentCore runtime when a segment is "
        "cancelled. This tool does not run that loop. The cancelled segment is marked "
        "removed. Later same-day segments move earlier by that segment's duration. "
        "A segment that already started before now stays in place. Sandbox only: "
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
    """AgentCore runtime entry for ``replan_cancel``. Calls ``replan_cancel``."""
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_NAME:
        return {
            "segmentId": "",
            "event": "cancelled",
            "changed": False,
            "plan": {},
            "notes": ["ignored tool call for a different tool"],
        }
    return replan_cancel(tool_input)


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
