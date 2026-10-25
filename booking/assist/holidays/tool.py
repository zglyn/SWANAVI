"""AgentCore tool spec for ``holiday_closure``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when it wants to know whether a segment falls on a sandbox public holiday.
This module does not run that loop and does not move segments. A shift is
a signal for the master, the same idea as a weather hold. A later integrator
wires the master. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on
harness invoke). When the runtime hands back a ``holiday_closure`` call,
run ``handler``. ``handler`` calls ``holiday_closure``.
"""

from __future__ import annotations

from .holidays import holiday_closure

TOOL_NAME = "holiday_closure"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "One segment: segmentId, kind, name, city, country, and date. "
        "A partial segment returns error invalid_segment and does not raise."
    ),
    "properties": {
        "segmentId": {"type": "string", "description": "Segment to check."},
        "kind": {
            "type": "string",
            "description": "attraction, flight, hotel, or restaurant.",
        },
        "name": {
            "type": "string",
            "description": "Place name. Accepted and not used to choose the holiday.",
        },
        "city": {
            "type": "string",
            "description": "City. Accepted and not used to choose the holiday.",
        },
        "country": {
            "type": "string",
            "description": (
                "Japan or JP, France or FR, United States or US or USA. "
                "Matching ignores case."
            ),
        },
        "date": {"type": "string", "description": "Calendar date as YYYY-MM-DD."},
    },
    "required": ["segmentId", "kind", "name", "city", "country", "date"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "closed": {
            "type": "boolean",
            "description": "True only for an attraction on a sandbox holiday.",
        },
        "holiday": {
            "type": ["string", "null"],
            "description": (
                "Sandbox holiday name when country and date match the table, "
                "including when a flight, hotel, or restaurant stays open. "
                "Null on any other date."
            ),
        },
        "action": {
            "type": "string",
            "enum": ["none", "shift"],
            "description": (
                "shift is a signal for the master, the same idea as a weather hold. "
                "This tool does not move the segment."
            ),
        },
        "error": {
            "type": "string",
            "description": "invalid_segment when the segment cannot be read. Omitted otherwise.",
        },
    },
    "required": ["segmentId", "closed", "holiday", "action"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Decide whether a segment is closed for a sandbox public holiday. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime. "
        "Attractions on a listed holiday return closed true and action shift. "
        "Flights, hotels, and restaurants stay open on that same holiday. "
        "shift is a signal for the master, the same idea as a weather hold. "
        "This tool does not move the segment. A bad segment returns error "
        "invalid_segment and action none. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``holiday_closure``. Calls ``holiday_closure``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            parsed = holiday_closure(tool_input)
            return {
                "segmentId": parsed.get("segmentId", ""),
                "closed": False,
                "holiday": None,
                "action": "none",
                "error": "unsupported AgentCore tool; expected holiday_closure",
            }
        return holiday_closure(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "closed": False,
            "holiday": None,
            "action": "none",
            "error": "invalid_segment",
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
