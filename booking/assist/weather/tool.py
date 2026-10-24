"""AgentCore tool spec for ``check_weather``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when a forecast signal arrives. This module does not run that loop and does
not move segments. A shift is handed to the late and early replan agents.
Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke).
When the runtime hands back a ``check_weather`` call, run ``handler``.
``handler`` calls ``check_weather``.
"""

from __future__ import annotations

from .weather import check_weather

TOOL_NAME = "check_weather"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Segment id, whether the segment is outdoors, and the forecast condition "
        "the caller already has. A partial payload is accepted and does not raise."
    ),
    "properties": {
        "segmentId": {"type": "string", "description": "Segment the forecast is about."},
        "outdoor": {
            "type": "boolean",
            "description": "True when the segment is outdoors. False skips the forecast.",
        },
        "condition": {
            "type": "string",
            "description": "Forecast word: rain, storm, snow, clear, or cloudy.",
        },
    },
    "required": ["segmentId", "outdoor", "condition"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "ok": {"type": "boolean"},
        "action": {
            "type": "string",
            "enum": ["none", "shift", "swap_indoor"],
            "description": (
                "none leaves the segment. shift is handed to the late and early "
                "replan agents. This tool does not select swap_indoor and does not move the segment."
            ),
        },
        "reason": {"type": "string"},
    },
    "required": ["segmentId", "ok", "action", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Hold an outdoor segment when a forecast signal arrives. The master agent "
        "calls this tool on the Amazon Bedrock AgentCore runtime. Indoor segments "
        "are ok. Outdoor rain, storm, or snow returns action shift for the late and "
        "early replan agents. Outdoor clear or cloudy is ok. This tool does not move "
        "segments. Sandbox only: no weather API, no network, and no AWS."
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
    """AgentCore runtime entry for ``check_weather``. Calls ``check_weather``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            parsed = check_weather(tool_input)
            return {
                "segmentId": parsed.get("segmentId", ""),
                "ok": False,
                "action": "none",
                "reason": "unsupported AgentCore tool; expected check_weather",
            }
        return check_weather(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "ok": False,
            "action": "none",
            "reason": "invalid_input",
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
