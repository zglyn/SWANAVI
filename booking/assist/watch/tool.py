"""AgentCore tool spec for ``watch_trip``.

The master agent calls this tool first on every tick on the Amazon Bedrock
AgentCore runtime and acts immediately. This module does not run that loop.
Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When
the runtime hands back a ``watch_trip`` call, run ``handler``. ``handler``
calls ``watch_trip``.
"""

from __future__ import annotations

from .watch import watch_trip

TOOL_NAME = "watch_trip"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Caller-supplied instant, the trip plan, ride rows, and signals. "
        "This tool does not read the wall clock, move the plan, or request a ride."
    ),
    "properties": {
        "now": {
            "type": "string",
            "description": "ISO-8601 timestamp supplied by the caller. This tool does not read the wall clock.",
        },
        "plan": {
            "type": "object",
            "description": (
                "Trip plan. flights, hotels, and attractions carry start and end ISO datetimes. "
                "An outdoor stop sets outdoor true (indoor false is the same fact). "
                "A partial plan is accepted and does not raise."
            ),
            "properties": {
                "tripId": {"type": "string"},
                "flights": {"type": "array", "items": {"type": "object"}},
                "hotels": {"type": "array", "items": {"type": "object"}},
                "attractions": {"type": "array", "items": {"type": "object"}},
            },
        },
        "rides": {
            "type": "array",
            "description": "Rides the master already knows about. This tool does not add one.",
            "items": {
                "type": "object",
                "properties": {
                    "fromSegmentId": {"type": "string"},
                    "status": {
                        "type": "string",
                        "description": "requested when the master has already asked for this ride.",
                    },
                },
            },
        },
        "signals": {
            "type": "array",
            "description": "Disruption and weather signals for this tick.",
            "items": {
                "type": "object",
                "properties": {
                    "segmentId": {"type": "string"},
                    "event": {
                        "type": "string",
                        "description": "cancelled, ended_early, and ended_late need a replan.",
                    },
                    "condition": {
                        "type": "string",
                        "description": "rain, storm, or snow on an outdoor segment that has not started.",
                    },
                    "deltaMinutes": {
                        "type": "number",
                        "description": "Minutes the caller attached. This tool does not apply that shift.",
                    },
                },
            },
        },
    },
    "required": ["now", "plan", "rides", "signals"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {
            "type": "boolean",
            "description": "False when any warning has severity act. True when warnings is empty.",
        },
        "warnings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segmentId": {"type": "string"},
                    "issue": {"type": "string"},
                    "severity": {"type": "string", "enum": ["watch", "act"]},
                    "action": {
                        "type": "string",
                        "enum": ["replan", "shift", "request_ride", "check_transfer"],
                    },
                },
                "required": ["segmentId", "issue", "severity", "action"],
            },
        },
    },
    "required": ["ok", "warnings"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Report early warnings for a trip in progress. The master agent calls this tool "
        "first on every tick on the Amazon Bedrock AgentCore runtime and acts immediately. "
        "This tool does not run that loop, does not move the plan, and does not request a ride. "
        "Sandbox only: the caller supplies now, and the tool does not use the network or AWS. "
        "A partial plan does not raise. ok is false when any warning has severity act."
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
    """AgentCore runtime entry for ``watch_trip``. Calls ``watch_trip``."""
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_NAME:
        return {"ok": True, "warnings": []}
    return watch_trip(tool_input)


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
