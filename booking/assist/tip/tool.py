"""AgentCore tool spec for ``tip_policy``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
before ``authorize_spend``, so a vendor cannot add a tip past the country
rule. This module does not run that loop and does not charge a card.
Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke).
When the runtime hands back a ``tip_policy`` call, run ``handler``.
``handler`` calls ``tip_policy``.
"""

from __future__ import annotations

from .policy import tip_policy

TOOL_NAME = "tip_policy"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Country, charge subtotal, and currency. A partial payload is accepted "
        "and does not raise. The subtotal is the amount before the tip."
    ),
    "properties": {
        "country": {
            "type": "string",
            "description": (
                "Country the sandbox tip rule uses. Japan is 0, United States is 20, "
                "France is 0, and anything else is 10."
            ),
        },
        "subtotal": {
            "description": "Charge before the tip. A number or a decimal string such as 10.00.",
            "anyOf": [{"type": "number"}, {"type": "string"}],
        },
        "currency": {
            "type": "string",
            "description": "Currency code, passed through unchanged.",
        },
    },
    "required": ["country", "subtotal", "currency"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "maxTipPercent": {
            "type": "integer",
            "description": "Sandbox tip percent for the country. Japan 0, United States 20, France 0, otherwise 10.",
        },
        "tipAmount": {
            "type": ["number", "null"],
            "description": (
                "subtotal * maxTipPercent / 100, rounded to 2 decimals. "
                "Null when the subtotal is missing or not a usable amount."
            ),
        },
        "authorizedAmount": {
            "type": ["number", "null"],
            "description": (
                "subtotal + tipAmount, rounded to 2 decimals. This is the ceiling "
                "the spend guard must use for authorize_spend. Null when tipAmount is null."
            ),
        },
        "currency": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["maxTipPercent", "tipAmount", "authorizedAmount", "currency", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Country tip ceiling for a sandbox charge. The master agent calls this tool "
        "on the Amazon Bedrock AgentCore runtime before authorize_spend so a vendor "
        "cannot add a tip past the country rule. authorizedAmount is subtotal plus "
        "the country tip and is the ceiling the spend guard must use. Sandbox percents: "
        "Japan 0, United States 20, France 0, anything else 10. tipAmount is "
        "subtotal * percent / 100, rounded to 2 decimals. A missing subtotal returns "
        "tipAmount null and reason missing_subtotal. This tool does not run the master "
        "loop and does not charge a card. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``tip_policy``. Calls ``tip_policy``."""
    try:
        tool_name = _tool_name(context)
        result = tip_policy(tool_input)
        if tool_name is not None and tool_name != TOOL_NAME:
            result["tipAmount"] = None
            result["authorizedAmount"] = None
            result["reason"] = "unsupported AgentCore tool; expected tip_policy"
        return result
    except Exception:
        return {
            "maxTipPercent": 10,
            "tipAmount": None,
            "authorizedAmount": None,
            "currency": "",
            "reason": "missing_subtotal",
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
