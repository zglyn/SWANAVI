"""AgentCore tool spec for ``refuse_dcc``.

A later integrator wires this tool into the master. This module does not run
that loop, does not call a payment terminal, and does not charge a card.
Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When
the runtime hands back a ``refuse_dcc`` call, run ``handler``. ``handler``
calls ``refuse_dcc``.
"""

from __future__ import annotations

from .dcc import refuse_dcc

TOOL_NAME = "refuse_dcc"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Merchant amount and currency, plus the amount and currency the terminal "
        "offered. A partial payload is accepted and does not raise."
    ),
    "properties": {
        "merchantAmount": {
            "type": ["number", "string"],
            "description": "Amount on the merchant bill. A number or a decimal string. Zero or more.",
        },
        "merchantCurrency": {
            "type": "string",
            "description": "Currency the merchant charged, such as JPY. This is the currency to pay.",
        },
        "offeredAmount": {
            "type": ["number", "string"],
            "description": (
                "Amount the terminal offered in another currency. Checked as a number, "
                "then ignored. It is not converted and it is not paid."
            ),
        },
        "offeredCurrency": {
            "type": "string",
            "description": "Currency the terminal offered. Compared to merchantCurrency without case.",
        },
    },
    "required": ["merchantAmount", "merchantCurrency", "offeredAmount", "offeredCurrency"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "payAmount": {
            "type": "number",
            "description": (
                "Merchant amount rounded half up. JPY uses 0 decimal places. "
                "Every other currency uses 2. 0 when the amount is bad or negative."
            ),
        },
        "payCurrency": {
            "type": "string",
            "description": "Merchant currency, trimmed. Empty when it was missing.",
        },
        "refused": {
            "type": "boolean",
            "description": (
                "False when the offered currency is the merchant currency. "
                "True when the terminal offered another currency or an amount is bad."
            ),
        },
        "reason": {"type": "string"},
    },
    "required": ["payAmount", "payCurrency", "refused", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Refuse dynamic currency conversion. Tourist rule: pay the merchant's "
        "currency. When offeredCurrency differs from merchantCurrency, refuse the "
        "terminal offer, pay merchantAmount in merchantCurrency, and set reason to "
        "dcc_refused. Ignore offeredAmount. Do not convert. When the currencies "
        "match, reason is local_currency and refused is false. A bad or negative "
        "amount pays 0 with reason invalid_amount. JPY rounds to 0 decimals; other "
        "currencies round to 2. Sandbox only: no live terminal, no card charge, "
        "and no network. A later integrator wires this tool into the master."
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
    """AgentCore runtime entry for ``refuse_dcc``. Calls ``refuse_dcc``."""
    try:
        tool_name = _tool_name(context)
        parsed = refuse_dcc(tool_input)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "payAmount": 0,
                "payCurrency": parsed.get("payCurrency") or "",
                "refused": True,
                "reason": "unsupported AgentCore tool; expected refuse_dcc",
            }
        return parsed
    except Exception:
        return {
            "payAmount": 0,
            "payCurrency": "",
            "refused": True,
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
