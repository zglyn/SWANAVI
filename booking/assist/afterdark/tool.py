"""AgentCore tool spec for ``after_dark``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime.
When the action is ``request_ride``, the master calls the ride agent. This
module does not request a ride and does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the
runtime hands back an ``after_dark`` call, run ``handler``. ``handler`` calls
``after_dark``.
"""

from __future__ import annotations

from .afterdark import REASON_FAILED, after_dark

TOOL_NAME = "after_dark"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Segment id, walk or ride, and the caller-supplied now and sunset instants. "
        "This tool does not read the wall clock and does not look up the segment."
    ),
    "properties": {
        "segmentId": {
            "type": "string",
            "description": "Segment the master is checking. Echoed on the result. Not looked up.",
        },
        "mode": {
            "type": "string",
            "enum": ["walk", "ride"],
            "description": "walk or ride. A ride is already fine. A walk is compared with sunset.",
        },
        "now": {
            "type": "string",
            "description": "ISO-8601 instant supplied by the caller. This tool does not read the wall clock.",
        },
        "sunset": {
            "type": "string",
            "description": "ISO-8601 sunset instant supplied by the caller.",
        },
    },
    "required": ["segmentId", "mode", "now", "sunset"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {
            "type": "string",
            "description": "Segment id from the input. Empty when the caller did not send one.",
        },
        "ok": {
            "type": "boolean",
            "description": (
                "True when the segment can stay as it is. False when a walk is at or after "
                "sunset, or when the check cannot be made."
            ),
        },
        "action": {
            "type": "string",
            "enum": ["none", "request_ride"],
            "description": (
                "request_ride tells the master to call the ride agent. This tool does not call it. "
                "none leaves the segment alone."
            ),
        },
        "reason": {"type": "string"},
    },
    "required": ["segmentId", "ok", "action", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Decide whether a night walk should become a ride. The master agent calls "
        "this tool on the Amazon Bedrock AgentCore runtime. On action request_ride, "
        "the master calls the ride agent. This tool does not request a ride and does "
        "not run that loop. mode ride is ok with action none. mode walk is ok with "
        "action none when now is before sunset, and is not ok with action request_ride "
        "when now is at or after sunset. A missing now or sunset on a walk is not ok "
        "and the action stays none. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``after_dark``. Calls ``after_dark``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "ok": False,
                "action": "none",
                "reason": "unsupported AgentCore tool; expected after_dark",
            }
        return after_dark(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "ok": False,
            "action": "none",
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
