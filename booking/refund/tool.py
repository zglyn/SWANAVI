"""AgentCore tool spec for ``refund_booking``.

The master agent calls this tool after ``replan_cancel``. This module does
not run that loop. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on
harness invoke). When the runtime hands back a ``refund_booking`` call, run
``handler``. ``handler`` calls ``refund_booking``.
"""

from __future__ import annotations

from .refund import REASON_UNREADABLE, refund_booking

TOOL_NAME = "refund_booking"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Cancelled segment to refund in the sandbox. "
        "The master calls this after replan_cancel. "
        "This tool does not charge a card and does not call a supplier."
    ),
    "properties": {
        "segmentId": {"type": "string"},
        "confirmationCode": {
            "type": "string",
            "description": "Sandbox booking code. A refund requires a code that starts with SANDBOX-.",
        },
        "amount": {
            "description": "Refund amount. A decimal string or a number. Echoed on success.",
        },
        "currency": {"type": "string"},
        "event": {
            "type": "string",
            "enum": ["cancelled"],
            "description": "Must be cancelled. The master sets this after replan_cancel.",
        },
    },
    "required": ["segmentId", "confirmationCode", "amount", "currency", "event"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segmentId": {"type": "string"},
        "status": {"type": "string", "enum": ["refunded", "failed"]},
        "refundCode": {
            "type": ["string", "null"],
            "description": "Starts with SANDBOX-REF- when refunded. Null when failed.",
        },
        "amount": {"description": "Echoed from the input when it can be read."},
        "currency": {"type": ["string", "null"]},
        "reason": {
            "type": ["string", "null"],
            "description": "Why the refund failed. Null when status is refunded.",
        },
    },
    "required": ["segmentId", "status", "refundCode", "amount", "currency", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Record a sandbox refund for one cancelled booking. The master agent "
        "calls this tool after replan_cancel. This tool does not run that loop, "
        "does not replan the day, and does not book a replacement. A cancelled "
        "segment with a SANDBOX- confirmation code and an amount returns status "
        "refunded and a refund code that starts with SANDBOX-REF-. Anything else "
        "returns status failed, a null refund code, and a reason. Sandbox only: "
        "no network, no card, and no AWS."
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
    """AgentCore runtime entry for ``refund_booking``. Calls ``refund_booking``.

    Never raises.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "status": "failed",
                "refundCode": None,
                "amount": None,
                "currency": None,
                "reason": "ignored tool call for a different tool",
            }
        return refund_booking(tool_input)
    except Exception:
        return {
            "segmentId": "",
            "status": "failed",
            "refundCode": None,
            "amount": None,
            "currency": None,
            "reason": REASON_UNREADABLE,
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
