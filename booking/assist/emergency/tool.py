"""AgentCore tool spec for ``emergency_card``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when the traveler asks for help. This module does not run that loop. It
returns phone numbers only, not medical guidance. Register ``TOOL_SPEC``
(or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime hands back
an ``emergency_card`` call, run ``handler``. ``handler`` calls ``emergency_card``.
"""

from __future__ import annotations

from .card import FALLBACK_EMERGENCY_NUMBER, UNKNOWN_COUNTRY, emergency_card

TOOL_NAME = "emergency_card"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Country the traveler is in, and the traveler's name. A partial payload "
        "is accepted and does not raise."
    ),
    "properties": {
        "country": {
            "type": "string",
            "description": (
                "Country name. The sandbox directory has Japan, France, and "
                "the United States. Any other country uses the unknown-country result."
            ),
        },
        "travelerName": {
            "type": "string",
            "description": "Traveler name. Included in the note. Not used to look anything up.",
        },
    },
    "required": ["country", "travelerName"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Phone numbers only. Not medical guidance.",
    "properties": {
        "country": {
            "type": "string",
            "description": "Sandbox directory name, or the country text the caller sent when it is unknown.",
        },
        "emergencyNumber": {
            "type": "string",
            "description": "Sandbox emergency phone number. 112 when the country is unknown.",
        },
        "embassyPhone": {
            "type": ["string", "null"],
            "description": "Sandbox embassy phone. Null when the country is unknown.",
        },
        "note": {
            "type": "string",
            "description": (
                "Includes travelerName. Includes unknown_country when the country "
                "is not in the sandbox directory. Phone numbers only."
            ),
        },
    },
    "required": ["country", "emergencyNumber", "embassyPhone", "note"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return sandbox emergency and embassy phone numbers when the traveler asks "
        "for help. The master agent calls this tool on the Amazon Bedrock AgentCore "
        "runtime. This tool does not run that loop. It returns phone numbers only, "
        "not medical guidance, doses, or treatment steps. Japan, France, and the "
        "United States are the sandbox directory. Any other country returns "
        "emergency number 112, a null embassy phone, and a note that includes "
        "unknown_country. The note includes travelerName. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``emergency_card``. Calls ``emergency_card``."""
    try:
        result = emergency_card(tool_input)
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            note = result.get("note") or UNKNOWN_COUNTRY
            if UNKNOWN_COUNTRY not in note:
                note = f"{UNKNOWN_COUNTRY} {note}"
            return {
                "country": result.get("country") or "",
                "emergencyNumber": FALLBACK_EMERGENCY_NUMBER,
                "embassyPhone": None,
                "note": note,
            }
        return result
    except Exception:
        return {
            "country": "",
            "emergencyNumber": FALLBACK_EMERGENCY_NUMBER,
            "embassyPhone": None,
            "note": UNKNOWN_COUNTRY,
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
