"""AgentCore tool spec for ``tax_refund``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime.
This module does not run that loop and does not register itself on the master.
Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When
the runtime hands back a ``tax_refund`` call, run ``handler``. ``handler``
calls ``tax_refund``.
"""

from __future__ import annotations

from .refund import REASON_INVALID, tax_refund

TOOL_NAME = "tax_refund"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Country, eligible purchases, departure time, and the instant of the quote. "
        "A partial payload is accepted and does not raise. This is a quote, not tax advice."
    ),
    "properties": {
        "country": {
            "type": "string",
            "description": (
                "Japan (JP) refunds 10% of eligible JPY spend of at least 5000 JPY. "
                "France (FR) refunds 20% of eligible EUR spend of at least 100 EUR. "
                "Any other country returns status none."
            ),
        },
        "purchases": {
            "type": "array",
            "description": (
                "Purchase lines. Only lines with eligible true and a currency equal to "
                "the refund currency are summed. Other currencies are ignored and not converted."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "amount": {
                        "description": "Line amount. A number or a decimal string. Zero or more.",
                        "anyOf": [{"type": "number"}, {"type": "string"}],
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency of this line, such as JPY or EUR.",
                    },
                    "eligible": {
                        "type": "boolean",
                        "description": "True when this line counts toward the refund.",
                    },
                },
                "required": ["amount", "currency", "eligible"],
            },
        },
        "departAt": {
            "type": "string",
            "description": "ISO-8601 departure time, such as 2026-11-06T16:00:00Z. The claim deadline.",
        },
        "now": {
            "type": "string",
            "description": "ISO-8601 instant of the quote, supplied by the caller. The tool does not read the clock.",
        },
    },
    "required": ["country", "purchases", "departAt", "now"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["eligible", "too_small", "missed", "none"],
            "description": (
                "eligible when the spend meets the minimum and now is not after departAt. "
                "too_small when the eligible spend is under the minimum. "
                "missed when now is after departAt. "
                "none when the country is not Japan or France, or the input cannot be quoted."
            ),
        },
        "refundAmount": {
            "type": "number",
            "description": (
                "Rate times eligible spend. 0 when status is too_small or none. "
                "Still the quoted amount when status is missed. "
                "JPY is rounded half up to 0 decimals. EUR is rounded half up to 2 decimals."
            ),
        },
        "refundCurrency": {
            "type": "string",
            "description": "JPY for Japan, EUR for France. Empty when the country is not supported.",
        },
        "eligibleSpend": {
            "type": "number",
            "description": (
                "Sum of eligible lines in the refund currency, rounded like the refund. "
                "0 when the country is not supported."
            ),
        },
        "claimBefore": {
            "type": ["string", "null"],
            "description": (
                "departAt written in UTC as YYYY-MM-DDTHH:MM:SSZ when status is eligible or missed. "
                "Null otherwise."
            ),
        },
        "reason": {"type": "string"},
    },
    "required": ["status", "refundAmount", "refundCurrency", "eligibleSpend", "claimBefore", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Quote a departure tax refund from eligible purchases. The master agent calls "
        "tax_refund on the Amazon Bedrock AgentCore runtime. This package does not run "
        "that loop. Japan refunds 10% of eligible JPY spend when that spend is at least "
        "5000 JPY. France refunds 20% of eligible EUR spend when that spend is at least "
        "100 EUR. Other countries return status none and refundAmount 0. Only eligible "
        "lines in the refund currency are summed; other currencies are ignored and not "
        "converted. Spend under the minimum returns status too_small and refundAmount 0. "
        "When now is after departAt, status is missed, claimBefore is departAt, and "
        "refundAmount is still the quoted amount. Otherwise status is eligible, "
        "claimBefore is departAt, and refundAmount is the rate times the eligible spend. "
        "JPY amounts are rounded to 0 decimals and EUR amounts to 2. This is a quote, "
        "not tax advice. Sandbox only: no tax-authority API, no network, and no AWS."
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
    """AgentCore runtime entry for ``tax_refund``. Calls ``tax_refund``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return _none("unsupported AgentCore tool; expected tax_refund")
        return tax_refund(tool_input)
    except Exception:
        return _none(REASON_INVALID)


def _none(reason: str) -> dict:
    return {
        "status": "none",
        "refundAmount": 0,
        "refundCurrency": "",
        "eligibleSpend": 0,
        "claimBefore": None,
        "reason": reason,
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
