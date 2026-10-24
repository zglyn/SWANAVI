"""AgentCore tool spec for ``authorize_spend``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
before a charge. This module does not run that loop and does not charge a
card. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke).
When the runtime hands back an ``authorize_spend`` call, run ``handler``.
``handler`` calls ``authorize_spend``.
"""

from __future__ import annotations

from .spend import authorize_spend

TOOL_NAME = "authorize_spend"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Segment id, currency, the amount the traveler authorized, and the amount "
        "the merchant requested. A partial payload is accepted and does not raise."
    ),
    "properties": {
        "segmentId": {"type": "string", "description": "Segment the charge would pay for."},
        "currency": {"type": "string", "description": "Currency code, passed through unchanged."},
        "authorizedAmount": {
            "type": ["number", "string"],
            "description": "Mastercard Agent Pay style limit the traveler already approved. Zero or more.",
        },
        "requestedAmount": {
            "type": ["number", "string"],
            "description": "Amount the merchant asked to capture. Zero or more.",
        },
        "reason": {
            "type": "string",
            "description": "Caller reason. Replaced with over_capture_rejected when the request exceeds the limit.",
        },
    },
    "required": ["segmentId", "currency", "authorizedAmount", "requestedAmount", "reason"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "decision": {"type": "string", "enum": ["pay", "reject"]},
        "payAmount": {
            "type": ["number", "string"],
            "description": "Amount that may be captured. 0 when decision is reject.",
        },
        "currency": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["segmentId", "decision", "payAmount", "currency", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Mastercard Agent Pay style spend limit. The master agent calls this tool "
        "on the Amazon Bedrock AgentCore runtime before a charge. Pay the requested "
        "amount when it is within the authorized amount. When the request is higher, "
        "pay only the authorized amount and set reason to over_capture_rejected. "
        "The traveler is not asked to dispute the extra. A negative or missing amount "
        "rejects with payAmount 0. Sandbox only: no card charge, no ledger network call, and no AWS."
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
    """AgentCore runtime entry for ``authorize_spend``. Calls ``authorize_spend``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            parsed = authorize_spend(tool_input)
            return {
                "segmentId": parsed.get("segmentId", ""),
                "decision": "reject",
                "payAmount": 0,
                "currency": parsed.get("currency", ""),
                "reason": "unsupported AgentCore tool; expected authorize_spend",
            }
        return authorize_spend(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "decision": "reject",
            "payAmount": 0,
            "currency": "",
            "reason": "invalid_amount",
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
