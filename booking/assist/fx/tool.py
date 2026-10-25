"""AgentCore tool spec for ``quote_fx``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
before ``authorize_spend`` when the vendor currency is not the trip currency.
This module does not run that loop and does not authorize a charge. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime
hands back a ``quote_fx`` call, run ``handler``. ``handler`` calls ``quote_fx``.
"""

from __future__ import annotations

from .quote import quote_fx

TOOL_NAME = "quote_fx"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Vendor amount and the two currency codes. Quote amount of fromCurrency "
        "into toCurrency. A partial payload is accepted and does not raise."
    ),
    "properties": {
        "amount": {
            "type": ["number", "string"],
            "description": "Vendor charge. A number or a decimal string. Zero or more.",
        },
        "fromCurrency": {
            "type": "string",
            "description": "Currency the vendor charged, such as JPY.",
        },
        "toCurrency": {
            "type": "string",
            "description": "Trip currency to quote into, such as USD.",
        },
    },
    "required": ["amount", "fromCurrency", "toCurrency"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "amount": {
            "type": ["number", "null"],
            "description": (
                "Quoted amount in toCurrency, rounded to 2 decimal places. "
                "Null when the currency is unknown or the amount is not usable."
            ),
        },
        "currency": {
            "type": "string",
            "description": "Trip currency the amount is quoted in. Empty when it was missing.",
        },
        "rate": {
            "type": ["number", "null"],
            "description": (
                "Units of toCurrency for one unit of fromCurrency. "
                "1 when the currencies match. Null when the quote cannot be made."
            ),
        },
        "source": {
            "type": "string",
            "enum": ["sandbox"],
            "description": "Always sandbox. This tool does not fetch a live rate.",
        },
        "reason": {"type": "string"},
    },
    "required": ["amount", "currency", "rate", "source", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Quote a vendor charge into the trip currency. The master agent calls "
        "quote_fx on the Amazon Bedrock AgentCore runtime before authorize_spend "
        "when the vendor currency is not the trip currency. Sandbox rates into USD "
        "are USD 1, EUR 1.08, GBP 1.27, and JPY 0.0067. The quoted amount is rounded "
        "to 2 decimal places. The same currency returns rate 1 and the same amount. "
        "An unknown currency returns amount null and reason unknown_currency. "
        "Sandbox only: no network, no XRPL, and no AWS."
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
    """AgentCore runtime entry for ``quote_fx``. Calls ``quote_fx``."""
    try:
        tool_name = _tool_name(context)
        parsed = quote_fx(tool_input)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "amount": None,
                "currency": parsed.get("currency") or "",
                "rate": None,
                "source": "sandbox",
                "reason": "unsupported AgentCore tool; expected quote_fx",
            }
        return parsed
    except Exception:
        return {
            "amount": None,
            "currency": "",
            "rate": None,
            "source": "sandbox",
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
