"""AgentCore tool spec for ``check_layover``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
between an inbound flight and the outbound flight. This module does not run
that loop and does not change a plan. A later integrator wires the master.
Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When
the runtime hands back a ``check_layover`` call, run ``handler``. ``handler``
calls ``check_layover``.
"""

from __future__ import annotations

from .layover import ACTION_NONE, REASON_INVALID, check_layover

TOOL_NAME = "check_layover"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "The inbound flight, the outbound flight, and whether the connection is international. "
        "Clocks and airports are supplied by the caller. A partial input does not raise. "
        "This tool does not change a plan."
    ),
    "properties": {
        "inbound": {
            "type": "object",
            "description": "Flight that arrives. segmentId, arriveAt, and airport.",
            "properties": {
                "segmentId": {
                    "type": "string",
                    "description": "segmentId of the arriving flight.",
                },
                "arriveAt": {
                    "type": "string",
                    "description": "ISO-8601 arrival instant. A Z suffix is UTC. The caller supplies this clock.",
                },
                "airport": {
                    "type": "string",
                    "description": "Arrival airport. Compared with the outbound airport. No airline lookup.",
                },
            },
            "required": ["segmentId", "arriveAt", "airport"],
        },
        "outbound": {
            "type": "object",
            "description": "Flight that departs. segmentId, departAt, and airport.",
            "properties": {
                "segmentId": {
                    "type": "string",
                    "description": "segmentId of the departing flight.",
                },
                "departAt": {
                    "type": "string",
                    "description": "ISO-8601 departure instant. A Z suffix is UTC. The caller supplies this clock.",
                },
                "airport": {
                    "type": "string",
                    "description": "Departure airport. Compared with the inbound airport. No airline lookup.",
                },
            },
            "required": ["segmentId", "departAt", "airport"],
        },
        "international": {
            "type": "boolean",
            "description": "True uses a 90 minute minimum connection. False uses 45 minutes.",
        },
    },
    "required": ["inbound", "outbound", "international"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {
            "type": "boolean",
            "description": "True only when the airports match and the gap is at least the minimum.",
        },
        "gapMinutes": {
            "type": "integer",
            "description": "departAt minus arriveAt, in whole minutes. A partial minute does not count. Negative when the outbound leaves first.",
        },
        "minimumMinutes": {
            "type": "integer",
            "description": "90 when international is true. 45 when international is false. 0 when the input cannot be read.",
        },
        "shortfallMinutes": {
            "type": "integer",
            "description": "minimumMinutes minus gapMinutes when the gap is shorter than the minimum, otherwise 0.",
        },
        "action": {
            "type": "string",
            "enum": ["none", "replan", "needs_user"],
            "description": "none when the connection fits. replan when it is short or inverted. needs_user when the airports differ.",
        },
        "reason": {
            "type": "string",
            "description": "enough, short, inverted, airport_change, or invalid_input.",
        },
    },
    "required": ["ok", "gapMinutes", "minimumMinutes", "shortfallMinutes", "action", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Check the connection between an inbound flight and an outbound flight. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime "
        "between those flights. Sandbox only: the caller supplies both clocks and both "
        "airports. The tool does not call an airline API, open the network, or call AWS. "
        "It does not change a plan. An international connection needs 90 minutes. A domestic "
        "connection needs 45. gapMinutes is departAt minus arriveAt in whole minutes. "
        "Same airport and a long enough gap is ok, action none, shortfallMinutes 0. "
        "Same airport and a shorter gap is not ok, action replan, shortfallMinutes is "
        "the minimum minus the gap. A departure before arrival is inverted and asks for "
        "a replan. Different airports are not ok, action needs_user, reason airport_change, "
        "and the gap is still reported. A partial input does not raise."
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
    """AgentCore runtime entry for ``check_layover``. Calls ``check_layover``.

    Never raises. Does not change a plan.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "ok": False,
                "gapMinutes": 0,
                "minimumMinutes": 0,
                "shortfallMinutes": 0,
                "action": ACTION_NONE,
                "reason": "ignored_tool",
            }
        return check_layover(tool_input)
    except Exception:
        return {
            "ok": False,
            "gapMinutes": 0,
            "minimumMinutes": 0,
            "shortfallMinutes": 0,
            "action": ACTION_NONE,
            "reason": REASON_INVALID,
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
