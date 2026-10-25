"""AgentCore tool spec for ``landing_data``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
before a ride is requested, so the phone has data on landing. This module
does not run that loop. A later integrator wires the master. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime
hands back a ``landing_data`` call, run ``handler``. ``handler`` calls
``landing_data``.
"""

from __future__ import annotations

from .landing import ACTION_NONE, STATUS_NEEDS_USER, landing_data

TOOL_NAME = "landing_data"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Destination country and the landing clock. arriveAt and now are ISO-8601 "
        "timestamps. The caller supplies now. This tool does not read the wall clock, "
        "buy a plan, or call a carrier."
    ),
    "properties": {
        "country": {
            "type": "string",
            "description": "Destination country supplied by the caller. Empty or unknown asks the traveler.",
        },
        "arriveAt": {
            "type": "string",
            "description": "ISO-8601 arrival time, UTC, with a Z suffix.",
        },
        "now": {
            "type": "string",
            "description": "ISO-8601 time the caller is asking, UTC, with a Z suffix.",
        },
        "hasData": {
            "type": "boolean",
            "description": "True when the phone already has data for this arrival.",
        },
    },
    "required": ["country", "arriveAt", "now", "hasData"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "country": {
            "type": "string",
            "description": "Country from the input. Empty when it was not a string.",
        },
        "status": {
            "type": "string",
            "enum": ["ready", "remind", "install", "needs_user"],
            "description": (
                "ready when hasData is true. remind when it is too early to install. "
                "install inside the 2-hour window or after arrival. needs_user when "
                "the country is empty or unknown."
            ),
        },
        "action": {
            "type": "string",
            "enum": ["none", "remind", "install_esim"],
            "description": "none, remind, or install_esim. install_esim does not buy a plan.",
        },
        "planCode": {
            "type": ["string", "null"],
            "description": "Sandbox label starting with SANDBOX-ESIM- when status is install. Null otherwise.",
        },
        "remindAt": {
            "type": ["string", "null"],
            "description": "ISO-8601 UTC time, arriveAt minus 2 hours, when status is remind. Null otherwise.",
        },
    },
    "required": ["country", "status", "action", "planCode", "remindAt"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Label a sandbox eSIM so the phone has data before a ride is requested. "
        "The master agent calls landing_data on the Amazon Bedrock AgentCore runtime "
        "before a ride is requested. This tool does not run that loop. A later "
        "integrator wires the master. When hasData is true, status is ready, "
        "planCode is null, and action is none. When hasData is false and now is "
        "earlier than arriveAt minus 2 hours, status is remind, action is remind, "
        "and remindAt is arriveAt minus 2 hours. Inside that 2-hour window, or "
        "after arrival, status is install, action is install_esim, and planCode "
        "starts with SANDBOX-ESIM-. An empty or unknown country is needs_user. "
        "Sandbox only: the plan code is a label. No carrier API, no purchase, "
        "and no real eSIM seller."
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
    """AgentCore runtime entry for ``landing_data``. Calls ``landing_data``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "country": "",
                "status": STATUS_NEEDS_USER,
                "action": ACTION_NONE,
                "planCode": None,
                "remindAt": None,
            }
        return landing_data(tool_input)
    except Exception:
        return {
            "country": "",
            "status": STATUS_NEEDS_USER,
            "action": ACTION_NONE,
            "planCode": None,
            "remindAt": None,
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
