"""AgentCore tool spec for ``incidental_hold``.

A later integrator wires this tool into the master. This module does not.
The hold is not a charge: ``handler`` explains a hotel incidental
authorization and does not capture or charge a card. Register ``TOOL_SPEC``
(or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime hands back
an ``incidental_hold`` call, run ``handler``. ``handler`` calls
``incidental_hold``.
"""

from __future__ import annotations

from .hold import incidental_hold

TOOL_NAME = "incidental_hold"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Hotel incidental authorization, the amount captured against it, "
        "the currency, and checkout. The hold is not a charge. A partial "
        "payload is accepted and does not raise."
    ),
    "properties": {
        "authorizedHold": {
            "description": (
                "Amount the hotel incidental hold covers. A number or a decimal "
                "string. This is not a charge."
            ),
            "anyOf": [{"type": "number"}, {"type": "string"}],
        },
        "capturedAmount": {
            "description": (
                "Amount captured against the hold. A number or a decimal string. "
                "This tool does not capture it."
            ),
            "anyOf": [{"type": "number"}, {"type": "string"}],
        },
        "currency": {
            "type": "string",
            "description": "Currency code. JPY amounts round to 0 decimals. Every other currency rounds to 2.",
        },
        "checkoutAt": {
            "type": "string",
            "description": "Checkout instant, ISO-8601 with Z. releaseBy is this instant plus 7 days.",
        },
    },
    "required": ["authorizedHold", "capturedAmount", "currency", "checkoutAt"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "authorizedHold": {
            "type": "number",
            "description": "authorizedHold rounded half up to 2 decimals, or 0 decimals for JPY.",
        },
        "capturedAmount": {
            "type": "number",
            "description": "capturedAmount rounded the same way. The extra above the hold is still shown.",
        },
        "releaseAmount": {
            "type": "number",
            "description": (
                "authorizedHold minus capturedAmount when the capture is within the hold. "
                "0 when the capture equals or exceeds the hold, and 0 when an amount is negative."
            ),
        },
        "currency": {"type": "string"},
        "releaseBy": {
            "type": ["string", "null"],
            "description": (
                "checkoutAt plus 7 days, sandbox date only. Null when an amount is not "
                "usable or checkoutAt is not an ISO timestamp. Nothing is sent to a card network."
            ),
        },
        "payAmount": {
            "type": "number",
            "description": (
                "Amount that counts as paid: min(capturedAmount, authorizedHold) when both "
                "numbers are usable. On over_capture this is authorizedHold. 0 when an amount is negative."
            ),
        },
        "reason": {
            "type": "string",
            "description": "held, captured_in_full, over_capture, or invalid_amount.",
        },
    },
    "required": [
        "authorizedHold",
        "capturedAmount",
        "releaseAmount",
        "currency",
        "releaseBy",
        "payAmount",
        "reason",
    ],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Explain a hotel incidental authorization. The hold is not a charge, and this "
        "tool does not capture or charge a card. releaseAmount is authorizedHold minus "
        "capturedAmount when the capture is within the hold. releaseBy is checkoutAt plus "
        "7 days. reason is held when part of the hold remains, captured_in_full when the "
        "capture equals the hold, and over_capture when the capture is above the hold. "
        "On over_capture the extra is not accepted: releaseAmount is 0 and payAmount is "
        "authorizedHold. payAmount is min(capturedAmount, authorizedHold) when the numbers "
        "are valid. A negative number returns reason invalid_amount and releaseAmount 0. "
        "Amounts round half up to 2 decimals. JPY rounds to 0 decimals. Sandbox only: "
        "no card network, no network, and no AWS. This tool does not run the master loop."
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
    """AgentCore runtime entry for ``incidental_hold``. Calls ``incidental_hold``."""
    try:
        tool_name = _tool_name(context)
        result = incidental_hold(tool_input)
        if tool_name is not None and tool_name != TOOL_NAME:
            result["releaseAmount"] = 0
            result["payAmount"] = 0
            result["releaseBy"] = None
            result["reason"] = "unsupported AgentCore tool; expected incidental_hold"
        return result
    except Exception:
        return {
            "authorizedHold": 0,
            "capturedAmount": 0,
            "releaseAmount": 0,
            "currency": "",
            "releaseBy": None,
            "payAmount": 0,
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
