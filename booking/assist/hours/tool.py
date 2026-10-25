"""AgentCore tool spec for ``check_hours``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
after a replan moves a stop. This module does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the
runtime hands back a ``check_hours`` call, run ``handler``. ``handler`` calls
``check_hours``.
"""

from __future__ import annotations

from .hours import check_hours

TOOL_NAME = "check_hours"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "One stop after a replan, plus the hours to check it against. "
        "Missing fields return ok false and do not raise."
    ),
    "properties": {
        "segmentId": {
            "type": "string",
            "description": "Segment id of the stop that was moved.",
        },
        "start": {
            "type": "string",
            "description": (
                "ISO-8601 start of the stop. The weekday and clock are read from "
                "this timestamp as written. The offset is not converted."
            ),
        },
        "end": {
            "type": "string",
            "description": (
                "ISO-8601 end of the stop. The clock is read from this timestamp "
                "as written. Touching close is outside hours."
            ),
        },
        "open": {
            "type": "string",
            "description": "Opening time as HH:MM. The stop may start at this time.",
        },
        "close": {
            "type": "string",
            "description": "Closing time as HH:MM. Hours are half-open [open, close).",
        },
        "closedWeekdays": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Weekdays the place is closed. Monday=0 and Sunday=6.",
        },
    },
    "required": ["segmentId", "start", "end", "open", "close", "closedWeekdays"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "ok": {
            "type": "boolean",
            "description": (
                "True when the start weekday is open, the start clock is at or after "
                "open, and the end clock is before close."
            ),
        },
        "reason": {
            "type": "string",
            "description": "Why ok is false, or within opening hours when ok is true.",
        },
    },
    "required": ["segmentId", "ok", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Check a stop against opening hours after a replan moves it. The master "
        "agent calls this tool on the Amazon Bedrock AgentCore runtime. Sandbox "
        "only: no network and no AWS. Weekday Monday=0. The ISO timestamp's own "
        "clock is used, not the machine timezone. ok is false when the start "
        "weekday is closed, the start is before open, or the end is after close. "
        "Touching close is not ok because hours are half-open [open, close). "
        "Missing fields return ok false and do not raise."
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
    """AgentCore runtime entry for ``check_hours``. Calls ``check_hours``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "ok": False,
                "reason": "unsupported AgentCore tool; expected check_hours",
            }
        return check_hours(tool_input)
    except Exception:
        return {"segmentId": "", "ok": False, "reason": "missing fields"}


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
