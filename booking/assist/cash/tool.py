"""AgentCore tool spec for ``cash_needed``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when a merchant may not take a card. This module does not run that loop and
does not contact an ATM. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL``
on harness invoke). When the runtime hands back a ``cash_needed`` call, run
``handler``. ``handler`` calls ``cash_needed``.
"""

from __future__ import annotations

from .cash import cash_needed

TOOL_NAME = "cash_needed"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Merchant charge and the trip currency. tripCurrency defaults to USD. "
        "A partial payload is accepted and does not raise."
    ),
    "properties": {
        "merchant": {
            "type": "object",
            "description": "Merchant that may or may not take a card.",
            "properties": {
                "name": {"type": "string", "description": "Merchant name."},
                "acceptsCard": {
                    "type": "boolean",
                    "description": "True when the merchant takes a card. False when the traveler needs cash.",
                },
                "amount": {
                    "type": ["number", "string"],
                    "description": "Merchant charge. A number or a decimal string. Zero or more.",
                },
                "currency": {
                    "type": "string",
                    "description": "Currency the merchant charged, such as JPY.",
                },
            },
            "required": ["name", "acceptsCard", "amount", "currency"],
        },
        "tripCurrency": {
            "type": "string",
            "description": "Trip currency to quote the cash into. Defaults to USD.",
            "default": "USD",
        },
    },
    "required": ["merchant"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "merchant": {
            "type": "string",
            "description": "Merchant name. Empty when the input has no name.",
        },
        "action": {
            "type": "string",
            "description": (
                "pay_card when the merchant accepts a card. "
                "withdraw_cash when the traveler needs cash. "
                "Empty when the amount is not usable."
            ),
        },
        "cashAmount": {
            "type": "number",
            "description": (
                "Cash to withdraw in the merchant currency. 0 when the merchant "
                "takes a card or the amount is not usable. USD, EUR, and GBP round "
                "to 2 decimals. JPY rounds to 0."
            ),
        },
        "cashCurrency": {
            "type": "string",
            "description": "Merchant currency. Empty when it was missing.",
        },
        "tripAmount": {
            "type": ["number", "null"],
            "description": (
                "cashAmount quoted into tripCurrency. 0 when the merchant takes a card. "
                "Null when the currency is unknown or the amount is not usable. "
                "USD, EUR, and GBP round to 2 decimals. JPY rounds to 0."
            ),
        },
        "tripCurrency": {
            "type": "string",
            "description": "Trip currency. USD when the caller did not send one.",
        },
        "reason": {"type": "string"},
    },
    "required": [
        "merchant",
        "action",
        "cashAmount",
        "cashCurrency",
        "tripAmount",
        "tripCurrency",
        "reason",
    ],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Decide whether a merchant needs cash, and quote that cash into the trip "
        "currency. The master agent calls cash_needed on the Amazon Bedrock "
        "AgentCore runtime when a merchant may not take a card. A later integrator "
        "wires this tool into the master. Sandbox rates into USD are USD 1, "
        "EUR 1.08, GBP 1.27, and JPY 0.0067. When acceptsCard is true the action "
        "is pay_card and cashAmount and tripAmount are 0. When acceptsCard is "
        "false the action is withdraw_cash, cashAmount is the merchant amount, "
        "and tripAmount is that cash quoted into tripCurrency (1000 JPY is 6.70 USD). "
        "USD, EUR, and GBP round to 2 decimals. JPY rounds to 0. An unknown "
        "currency returns action withdraw_cash, tripAmount null, and reason "
        "unknown_currency. A negative amount returns reason invalid_amount and "
        "cashAmount 0. tripCurrency defaults to USD. Sandbox only: no network "
        "and no ATM API."
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
    """AgentCore runtime entry for ``cash_needed``. Calls ``cash_needed``."""
    try:
        tool_name = _tool_name(context)
        result = cash_needed(tool_input)
        if tool_name is not None and tool_name != TOOL_NAME:
            result["action"] = ""
            result["cashAmount"] = 0
            result["tripAmount"] = None
            result["reason"] = "unsupported AgentCore tool; expected cash_needed"
        return result
    except Exception:
        return {
            "merchant": "",
            "action": "",
            "cashAmount": 0,
            "cashCurrency": "",
            "tripAmount": None,
            "tripCurrency": "USD",
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
