"""AgentCore tool spec for ``request_ride``.

The master calls this tool on the Amazon Bedrock AgentCore runtime when an
attraction is about to end so the car is there for the next stop. This module
does not run that loop. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on
harness invoke). When the runtime hands back a ``request_ride`` call, run
``handler``. ``handler`` calls ``request_ride``.
"""

from __future__ import annotations

from .ride import REASON_UNREADABLE, request_ride

TOOL_NAME = "request_ride"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Ride from the attraction that is about to end to the next stop. "
        "pickupAt is the ISO time when the attraction ends."
    ),
    "properties": {
        "fromSegmentId": {
            "type": "string",
            "description": "Segment id of the attraction that is about to end.",
        },
        "toSegmentId": {
            "type": "string",
            "description": "Segment id of the next stop.",
        },
        "pickupAt": {
            "type": "string",
            "description": "ISO-8601 time when the attraction ends. The car is requested for this time.",
        },
        "pickupName": {
            "type": "string",
            "description": "Pickup place name, the attraction that is ending.",
        },
        "dropoffName": {
            "type": "string",
            "description": "Dropoff place name, the next stop.",
        },
        "partySize": {
            "type": "integer",
            "description": "People in the car.",
        },
    },
    "required": ["fromSegmentId", "toSegmentId", "pickupAt", "pickupName", "dropoffName", "partySize"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["requested", "failed"]},
        "rideCode": {
            "type": ["string", "null"],
            "description": "Starts with SANDBOX-RIDE- in the sandbox. Null when failed.",
        },
        "pickupAt": {
            "type": ["string", "null"],
            "description": "Echoed from the input when it can be read.",
        },
        "dropoffName": {
            "type": ["string", "null"],
            "description": "Echoed from the input when it can be read.",
        },
        "partySize": {
            "type": ["integer", "null"],
            "description": "Echoed from the input when it is a positive integer.",
        },
        "reason": {
            "type": ["string", "null"],
            "description": "Why the ride was not requested. Null when status is requested.",
        },
    },
    "required": ["status", "rideCode", "pickupAt", "dropoffName", "partySize", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Request a ride from the attraction that is ending to the next stop. "
        "The master calls request_ride on Bedrock AgentCore when an attraction "
        "is about to end so the car is there for the next stop. This tool does "
        "not run that loop. Sandbox is the default: status requested and a ride "
        "code that starts with SANDBOX-RIDE-. A missing pickupAt or dropoffName "
        "returns status failed, a null ride code, and a reason, and does not raise. "
        "The live Uber Rides API adapter is off unless ROAM_RIDE_PROVIDER=live and "
        "UBER_ACCESS_TOKEN is set. It estimates the trip, then creates it on the "
        "Uber sandbox host. It does not hit production."
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
    """AgentCore runtime entry for ``request_ride``. Calls ``request_ride``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "status": "failed",
                "rideCode": None,
                "pickupAt": None,
                "dropoffName": None,
                "partySize": None,
                "reason": "ignored tool call for a different tool",
            }
        return request_ride(tool_input)
    except Exception:
        return {
            "status": "failed",
            "rideCode": None,
            "pickupAt": None,
            "dropoffName": None,
            "partySize": None,
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
