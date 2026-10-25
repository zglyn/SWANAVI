"""AgentCore tool spec for ``check_in_flight``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when a flight segment can be checked in. This module does not run that loop.
A later integrator wires the master loop. Register ``TOOL_SPEC`` (or pass
``AGENTCORE_TOOL`` on harness invoke). When the runtime hands back a
``check_in_flight`` call, run ``handler``. ``handler`` calls ``check_in_flight``.
"""

from __future__ import annotations

from .checkin import ERROR_INVALID, check_in_flight

TOOL_NAME = "check_in_flight"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "The caller's clock, one segment, and the travelers on that segment. "
        "The check-in window opens 24 hours before departure. "
        "This tool does not call an airline."
    ),
    "properties": {
        "now": {
            "type": "string",
            "description": "ISO-8601 timestamp from the caller, in UTC. This tool does not read the wall clock.",
        },
        "segment": {
            "type": "object",
            "description": "The segment to check in. Only kind flight can be checked in.",
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {
                    "type": "string",
                    "description": "flight, or another segment kind. Anything other than flight is not_a_flight.",
                },
                "departAt": {
                    "type": "string",
                    "description": "ISO-8601 departure. Used when it is present.",
                },
                "departDate": {
                    "type": "string",
                    "description": "YYYY-MM-DD departure date. A date only is that date at 09:00 UTC.",
                },
                "confirmationCode": {
                    "type": ["string", "null"],
                    "description": "Booking confirmation. Null means the traveler still has to supply one.",
                },
            },
            "required": ["segmentId", "kind"],
        },
        "travelers": {
            "type": "array",
            "description": "Travelers on the segment. Each item has id and name.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["id", "name"],
            },
        },
    },
    "required": ["now", "segment", "travelers"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Sandbox check-in for one segment. boardingPass is a sandbox code, not a barcode. "
        "error is invalid_segment when the input cannot be read."
    ),
    "properties": {
        "segmentId": {"type": "string"},
        "status": {
            "type": ["string", "null"],
            "enum": ["waiting", "checked_in", "missed", "needs_user", "not_a_flight", None],
            "description": (
                "waiting before the 24 hour window, checked_in inside it, "
                "missed after departure, needs_user without a confirmation code, "
                "not_a_flight for any other kind. Null when error is invalid_segment."
            ),
        },
        "boardingPass": {
            "type": ["string", "null"],
            "description": "Sandbox code starting with SANDBOX-BP- when status is checked_in. Null otherwise. Not a barcode.",
        },
        "opensAt": {
            "type": ["string", "null"],
            "description": "ISO-8601 UTC time when the window opens: departure minus 24 hours. Null when it cannot be computed.",
        },
        "error": {
            "type": ["string", "null"],
            "description": "invalid_segment when the input cannot be read. Null otherwise.",
        },
    },
    "required": ["segmentId", "status", "boardingPass", "opensAt", "error"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Check in one flight inside the 24 hour window before departure. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime. "
        "This tool does not run that loop; a later integrator wires it. "
        "Before the window, status is waiting and opensAt is departure minus 24 hours. "
        "Inside the window, a confirmation code returns status checked_in and a "
        "sandbox boarding pass that starts with SANDBOX-BP-. That pass is a sandbox "
        "code, not a real barcode. After departure, status is missed. "
        "No confirmation code returns needs_user. A segment that is not a flight "
        "returns not_a_flight. Bad input returns error invalid_segment and does not raise. "
        "A date-only departDate is that date at 09:00 UTC. "
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
    """AgentCore runtime entry for ``check_in_flight``. Calls ``check_in_flight``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "status": None,
                "boardingPass": None,
                "opensAt": None,
                "error": ERROR_INVALID,
            }
        return check_in_flight(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "status": None,
            "boardingPass": None,
            "opensAt": None,
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
