"""AgentCore tool spec for ``check_budget``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
before accepting a booking or a replan that adds cost. This module does not
run that loop. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness
invoke). When the runtime hands back a ``check_budget`` call, run ``handler``.
``handler`` calls ``check_budget``.
"""

from __future__ import annotations

from .budget import REASON_FAILED, check_budget

TOOL_NAME = "check_budget"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Trip id and the amounts the master already has. This tool does not look up "
        "the trip. Amounts are decimal strings such as 100.00, or numbers."
    ),
    "properties": {
        "tripId": {
            "type": "string",
            "description": "Trip the master is about to charge. Recorded by the caller; not looked up.",
        },
        "currency": {
            "type": "string",
            "description": "Currency code supplied by the caller, such as USD. Echoed on the result.",
        },
        "budgetAmount": {
            "description": "Trip budget. Decimal string such as 500.00, or a number.",
            "anyOf": [{"type": "string"}, {"type": "number"}],
        },
        "spentAmount": {
            "description": "Amount already spent on the trip. Decimal string or a number.",
            "anyOf": [{"type": "string"}, {"type": "number"}],
        },
        "proposedAmount": {
            "description": "Charge the master would add by accepting this booking or replan. Decimal string or a number.",
            "anyOf": [{"type": "string"}, {"type": "number"}],
        },
    },
    "required": ["tripId", "currency", "budgetAmount", "spentAmount", "proposedAmount"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "allowed": {
            "type": "boolean",
            "description": "True only when spentAmount + proposedAmount is less than or equal to budgetAmount.",
        },
        "remaining": {
            "type": "string",
            "description": (
                "budgetAmount - spentAmount - proposedAmount as a decimal string. "
                "Negative when the charge is blocked. Null when an amount is missing or not a number."
            ),
        },
        "currency": {
            "type": "string",
            "description": "Currency from the input. Empty when the caller did not send one.",
        },
        "reason": {"type": "string"},
    },
    "required": ["allowed", "remaining", "currency", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Decide whether a proposed charge fits the trip budget. The master agent calls "
        "this tool on the Amazon Bedrock AgentCore runtime before accepting a booking or "
        "a replan that adds cost. This tool does not run that loop, does not book, and "
        "does not replan. allowed is true only when spentAmount + proposedAmount is less "
        "than or equal to budgetAmount. remaining is budgetAmount - spentAmount - "
        "proposedAmount and may be negative when the charge is blocked. A missing amount "
        "is not allowed. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``check_budget``. Calls ``check_budget``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "allowed": False,
                "remaining": None,
                "currency": "",
                "reason": "unsupported AgentCore tool; expected check_budget",
            }
        return check_budget(tool_input)
    except Exception:
        return {
            "allowed": False,
            "remaining": None,
            "currency": "",
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
