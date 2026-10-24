"""AgentCore tool spec for ``check_transfer``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
between consecutive stops. This module does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime
hands back a ``check_transfer`` call, run ``handler``. ``handler`` calls
``check_transfer``.
"""

from __future__ import annotations

from .transfer import check_transfer

TOOL_NAME = "check_transfer"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "The stop just ending, the next stop, and how long the ride between them takes. "
        "Clocks are supplied by the caller. A partial input does not raise."
    ),
    "properties": {
        "fromSegmentId": {
            "type": "string",
            "description": "segmentId of the stop that is ending.",
        },
        "toSegmentId": {
            "type": "string",
            "description": "segmentId of the next stop.",
        },
        "fromEnd": {
            "type": "string",
            "description": "ISO-8601 instant when the first stop ends. This tool does not read the wall clock.",
        },
        "toStart": {
            "type": "string",
            "description": "ISO-8601 instant when the next stop starts.",
        },
        "travelMinutes": {
            "type": "integer",
            "description": "Ride length between the stops, in minutes. Supplied by the caller. No maps lookup.",
        },
    },
    "required": ["fromSegmentId", "toSegmentId", "fromEnd", "toStart", "travelMinutes"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {
            "type": "boolean",
            "description": "True when toStart - fromEnd is at least travelMinutes. False on a shortfall or an overlap.",
        },
        "leaveBy": {
            "type": ["string", "null"],
            "description": "fromEnd when ok is true, otherwise null.",
        },
        "shortfallMinutes": {
            "type": "integer",
            "description": "max(0, travelMinutes - gap) for a whole-minute gap. Zero when the ride fits.",
        },
        "reason": {
            "type": "string",
            "description": "enough_time, shortfall, overlap, invalid_input, or ignored_tool.",
        },
    },
    "required": ["ok", "leaveBy", "shortfallMinutes", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Check that the gap between two consecutive stops covers the ride. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime "
        "between consecutive stops. Sandbox only: the caller supplies fromEnd, toStart, "
        "and travelMinutes. The tool does not call a maps API, open the network, or call AWS. "
        "ok is true when the gap is at least the ride. leaveBy is fromEnd when the ride fits, "
        "otherwise null. A negative gap is an overlap and is not ok. A partial input does not raise."
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
    """AgentCore runtime entry for ``check_transfer``. Calls ``check_transfer``."""
    tool_name = _tool_name(context)
    if tool_name is not None and tool_name != TOOL_NAME:
        return {
            "ok": False,
            "leaveBy": None,
            "shortfallMinutes": 0,
            "reason": "ignored_tool",
        }
    return check_transfer(tool_input)


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
