"""AgentCore tool spec for ``pick_card``.

Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When
the runtime hands back a ``pick_card`` call, run ``handler``. ``handler``
calls ``pick_card``. This module does not run the master loop, does not
charge a card, and does not read real card data. Cards in the input are
fake fixtures. A later integrator wires this tool into the master.
"""

from __future__ import annotations

from .pick import pick_card

TOOL_NAME = "pick_card"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Merchant country, charge amount, currency, and fake fixture cards. "
        "A partial payload is accepted and does not raise. No real card data."
    ),
    "properties": {
        "merchantCountry": {
            "type": "string",
            "description": (
                "Merchant country as an ISO-ish name or code. Japan and JP match, "
                "France and FR match, and US matches US."
            ),
        },
        "amount": {
            "description": "Charge before the foreign-exchange fee. A number or a decimal string. Zero or more.",
            "anyOf": [{"type": "number"}, {"type": "string"}],
        },
        "currency": {
            "type": "string",
            "description": "Currency code, passed through. JPY amounts round to 0 decimals; every other currency rounds to 2.",
        },
        "cards": {
            "type": "array",
            "description": (
                "Fake fixture cards. Only a Mastercard can be selected. "
                "Visa and Amex are ignored."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Fixture id. Not a real card number.",
                    },
                    "network": {
                        "type": "string",
                        "description": "Card network. mastercard is matched case-insensitively.",
                    },
                    "fxFeePercent": {
                        "description": "Foreign-exchange fee percent used when the country is not in noFxCountries.",
                        "anyOf": [{"type": "number"}, {"type": "string"}],
                    },
                    "noFxCountries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Countries where this fixture charges no foreign-exchange fee.",
                    },
                },
                "required": ["id", "network", "fxFeePercent", "noFxCountries"],
            },
        },
    },
    "required": ["merchantCountry", "amount", "currency", "cards"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "cardId": {
            "type": ["string", "integer", "null"],
            "description": "Id of the chosen fixture Mastercard. Null when none is chosen.",
        },
        "fxFeePercent": {
            "type": ["number", "null"],
            "description": (
                "0 when the merchant country is in the chosen card's noFxCountries. "
                "The chosen card's percent otherwise. Null when no Mastercard is chosen."
            ),
        },
        "feeAmount": {
            "type": "number",
            "description": "amount * fxFeePercent / 100, rounded half up. 0 when the fee does not apply or the amount is negative.",
        },
        "payAmount": {
            "type": "number",
            "description": "amount + feeAmount, rounded half up to 2 decimals, or 0 decimals for JPY.",
        },
        "currency": {
            "type": "string",
            "description": "Currency from the input. Empty when the caller did not send one.",
        },
        "reason": {
            "type": "string",
            "description": "no_fx_fee, lowest_fee, no_mastercard, or invalid_amount.",
        },
        "status": {
            "type": "string",
            "description": "needs_user when no Mastercard is available. Omitted when a card is chosen or the amount is invalid.",
        },
    },
    "required": ["cardId", "fxFeePercent", "feeAmount", "payAmount", "currency", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Pick a sandbox Mastercard for a merchant charge. Prefer a Mastercard "
        "whose noFxCountries includes the merchant country (Japan/JP, France/FR, "
        "US/US): fxFeePercent 0, feeAmount 0, reason no_fx_fee. Otherwise the "
        "Mastercard with the lowest fxFeePercent. feeAmount is amount * "
        "fxFeePercent / 100 and reason is lowest_fee. payAmount is amount + "
        "feeAmount, rounded half up to 2 decimals, or 0 decimals for JPY. If no "
        "Mastercard is present, status is needs_user, cardId is null, and reason "
        "is no_mastercard. Visa and Amex are never selected. A negative amount "
        "returns reason invalid_amount and feeAmount 0. Cards in the input are "
        "fake fixtures. Sandbox only: no network, no real card data, and no charge. "
        "A later integrator wires this tool into the master."
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
    """AgentCore runtime entry for ``pick_card``. Calls ``pick_card``."""
    try:
        tool_name = _tool_name(context)
        result = pick_card(tool_input)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "cardId": None,
                "fxFeePercent": None,
                "feeAmount": 0,
                "payAmount": 0,
                "currency": result.get("currency") or "",
                "reason": "unsupported AgentCore tool; expected pick_card",
            }
        return result
    except Exception:
        return {
            "cardId": None,
            "fxFeePercent": None,
            "feeAmount": 0,
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
