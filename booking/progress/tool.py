"""AgentCore tool spec for ``trip_progress``.

The master agent calls this tool inside its loop on the Amazon Bedrock
AgentCore runtime. This module does not run that loop. Register ``TOOL_SPEC``
(or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime hands back a
``trip_progress`` call, run ``handler``. ``handler`` calls ``trip_progress``.
"""

from __future__ import annotations

from .progress import trip_progress

TOOL_NAME = "trip_progress"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip plan, per-segment booking results, and the caller-supplied instant. "
        "This tool does not read the wall clock."
    ),
    "properties": {
        "plan": {
            "type": "object",
            "description": "Trip plan. A partial plan is accepted and does not raise.",
            "properties": {
                "tripId": {"type": "string"},
                "dates": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "description": "YYYY-MM-DD."},
                        "end": {"type": "string", "description": "YYYY-MM-DD."},
                    },
                },
                "flights": {"type": "array", "items": {"type": "object"}},
                "hotels": {"type": "array", "items": {"type": "object"}},
                "attractions": {"type": "array", "items": {"type": "object"}},
            },
        },
        "results": {
            "type": "array",
            "description": "Booking result for each segment the caller has.",
            "items": {
                "type": "object",
                "properties": {
                    "segmentId": {"type": "string"},
                    "kind": {"type": "string", "description": "flight, hotel, or attraction."},
                    "status": {
                        "type": "string",
                        "description": "booked, failed, needs_user, or finished.",
                    },
                    "confirmationCode": {
                        "type": "string",
                        "description": "Sandbox codes start with SANDBOX-. Null when absent.",
                    },
                    "emailVerified": {"type": "boolean"},
                },
            },
        },
        "now": {
            "type": "string",
            "description": "ISO-8601 timestamp supplied by the caller. This tool does not read the wall clock.",
        },
        "signals": {
            "type": "array",
            "description": "Optional segment signals. Each one appends a replan update. Omit when there are none.",
            "items": {
                "type": "object",
                "properties": {
                    "segmentId": {"type": "string"},
                    "event": {
                        "type": "string",
                        "enum": ["cancelled", "ended_early", "ended_late"],
                    },
                    "deltaMinutes": {"type": "number"},
                },
                "required": ["segmentId", "event", "deltaMinutes"],
            },
        },
    },
    "required": ["plan", "results", "now"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "phase": {
            "type": "string",
            "enum": ["pre_trip", "in_progress", "done"],
        },
        "onTrack": {"type": "boolean"},
        "updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segmentId": {"type": "string"},
                    "kind": {"type": "string"},
                    "issue": {"type": "string"},
                    "event": {
                        "type": "string",
                        "enum": ["cancelled", "ended_early", "ended_late"],
                        "description": "Present on replan updates from signals.",
                    },
                    "deltaMinutes": {
                        "type": "number",
                        "description": "Present on replan updates from signals.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["none", "rebook", "verify_email", "replan"],
                    },
                },
                "required": ["segmentId", "kind", "issue", "action"],
            },
        },
    },
    "required": ["phase", "onTrack", "updates"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Report whether a booked trip is pre_trip, in_progress, or done, and which "
        "segments need rebook, verify_email, or replan. Optional signals append replan "
        "updates. The master agent calls this tool inside "
        "its loop on the Amazon Bedrock AgentCore runtime. This tool does not run that loop. "
        "Sandbox only: it compares segment times on the plan to the caller-supplied now "
        "and does not use the network or AWS."
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
    """AgentCore runtime entry for ``trip_progress``. Calls ``trip_progress``."""
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_NAME:
        return {"phase": "pre_trip", "onTrack": True, "updates": []}
    return trip_progress(tool_input)


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
