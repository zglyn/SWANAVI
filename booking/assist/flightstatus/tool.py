"""AgentCore tool spec for ``flight_status``.

The master agent calls this tool for a flight segment on a tick, before it
replans. This module does not run that loop and does not change the segment.
A later integrator wires the call into the master loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the
runtime hands back a ``flight_status`` call, run ``handler``. ``handler``
calls ``flight_status``.
"""

from __future__ import annotations

from .status import ERROR_INVALID, flight_status

TOOL_NAME = "flight_status"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip id, the caller-supplied instant, one segment, and an optional sandbox feed. "
        "A partial payload is accepted and does not raise. This tool does not change the segment."
    ),
    "properties": {
        "tripId": {
            "type": "string",
            "description": "Trip the segment belongs to.",
        },
        "now": {
            "type": "string",
            "description": "ISO-8601 timestamp supplied by the caller. This tool does not read the wall clock.",
        },
        "segment": {
            "type": "object",
            "description": (
                "One segment. A flight needs segmentId, kind, from, to, and departAt or departDate. "
                "confirmationCode may be a string or null. Any other kind is not a flight."
            ),
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {"type": "string", "description": "flight, or another kind this tool ignores."},
                "from": {"type": "string"},
                "to": {"type": "string"},
                "departAt": {
                    "type": "string",
                    "description": "ISO-8601 departure. departDate is used when departAt is absent.",
                },
                "departDate": {"type": "string"},
                "confirmationCode": {"type": ["string", "null"]},
            },
            "required": ["segmentId", "kind", "from", "to"],
        },
        "feed": {
            "type": "object",
            "description": (
                "Optional sandbox status. Omit the feed for event on_time and delayMinutes 0. "
                "This tool does not fetch a feed."
            ),
            "properties": {
                "event": {
                    "type": "string",
                    "enum": ["on_time", "delayed", "cancelled"],
                },
                "delayMinutes": {
                    "type": "number",
                    "description": "Required to be greater than 0 when event is delayed. Ignored for a cancellation.",
                },
            },
        },
    },
    "required": ["tripId", "now", "segment"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "event": {
            "type": "string",
            "enum": ["on_time", "delayed", "cancelled", "not_a_flight", ""],
            "description": "Empty when the segment is invalid.",
        },
        "delayMinutes": {
            "type": "number",
            "description": "Minutes late. 0 when the feed is omitted, the flight is on time, or it is cancelled.",
        },
        "action": {
            "type": "string",
            "enum": ["none", "replan"],
            "description": "replan when the flight is delayed or cancelled. none otherwise.",
        },
        "departAt": {
            "type": "string",
            "description": "Scheduled departure from the segment. This tool does not add the delay to it.",
        },
        "error": {
            "type": "string",
            "description": "invalid_segment when a required field is missing. Absent on a usable segment.",
        },
    },
    "required": ["segmentId", "event", "delayMinutes", "action", "departAt"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Report whether one flight is on time, delayed, or cancelled. The master agent "
        "calls this tool for a flight segment on a tick, before it replans. delayed and "
        "cancelled set action to replan. on_time sets action to none. An omitted feed is "
        "on_time with delayMinutes 0. A delay that is not greater than 0 is reported as "
        "on_time. cancelled uses delayMinutes 0. A segment that is not a flight returns "
        "event not_a_flight and action none. departAt is the scheduled departure and is "
        "not shifted. A missing field returns error invalid_segment and action none, and "
        "does not raise. This tool does not run the master loop and does not change the "
        "segment. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``flight_status``. Calls ``flight_status``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "event": "",
                "delayMinutes": 0,
                "action": "none",
                "departAt": "",
                "error": ERROR_INVALID,
            }
        return flight_status(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "event": "",
            "delayMinutes": 0,
            "action": "none",
            "departAt": "",
            "error": ERROR_INVALID,
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
