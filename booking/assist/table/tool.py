"""AgentCore tool spec for ``hold_table``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when the traveler is late to a meal so the table is held. This module does
not run that loop. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on
harness invoke). When the runtime hands back a ``hold_table`` call, run
``handler``. ``handler`` calls ``hold_table``. Sandbox only: no OpenTable
call, no network, and no AWS.
"""

from __future__ import annotations

from .hold import REASON_FAILED, STATUS_FAILED, hold_table

TOOL_NAME = "hold_table"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Meal segment, venue, reservation time, expected arrival, and party size. "
        "Times are ISO-8601. A missing time does not raise."
    ),
    "properties": {
        "segmentId": {
            "type": "string",
            "description": "Meal segment. Copied onto the result.",
        },
        "venue": {
            "type": "string",
            "description": "Restaurant. Accepted and not used to choose the hold.",
        },
        "reservationAt": {
            "type": "string",
            "description": "ISO-8601 reservation time supplied by the caller.",
        },
        "arriveAt": {
            "type": "string",
            "description": "ISO-8601 arrival time supplied by the caller. This tool does not read the wall clock.",
        },
        "partySize": {
            "type": "integer",
            "description": "Party size. Accepted and not used to choose the hold.",
        },
    },
    "required": ["segmentId", "venue", "reservationAt", "arriveAt", "partySize"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["on_time", "held", "failed"],
            "description": (
                "on_time when arriveAt is at or before reservationAt. "
                "held when arriveAt is later. failed when a time is missing."
            ),
        },
        "heldUntil": {
            "type": "string",
            "description": (
                "reservationAt when status is on_time. arriveAt plus 15 minutes, "
                "as UTC YYYY-MM-DDTHH:MM:SSZ, when status is held. Null when status is failed."
            ),
        },
        "reason": {"type": "string"},
    },
    "required": ["segmentId", "status", "heldUntil", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Hold a dinner table when the traveler arrives after the reservation. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime "
        "when the traveler is late to a meal so the table is held. This tool does "
        "not run that loop. If arriveAt is at or before reservationAt, status is "
        "on_time and heldUntil is reservationAt. If arriveAt is later, status is "
        "held and heldUntil is arriveAt plus 15 minutes. A missing reservationAt "
        "or arriveAt returns status failed and does not raise. Sandbox only: no "
        "OpenTable call, no network, and no AWS."
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
    """AgentCore runtime entry for ``hold_table``. Calls ``hold_table``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "status": STATUS_FAILED,
                "heldUntil": None,
                "reason": "unsupported AgentCore tool; expected hold_table",
            }
        return hold_table(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "status": STATUS_FAILED,
            "heldUntil": None,
            "reason": REASON_FAILED,
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
