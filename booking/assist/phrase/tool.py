"""AgentCore tool spec for ``phrase_card``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
when it requests a ride. This module does not run that loop. Place, address,
and arrival are copied as given. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on
harness invoke). When the runtime hands back a ``phrase_card`` call, run
``handler``. ``handler`` calls ``phrase_card``.
"""

from __future__ import annotations

from .phrase import phrase_card

TOOL_NAME = "phrase_card"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Language code and the place, address, and arrival the traveler shows a driver. "
        "placeName, address, and arriveAt are copied as given."
    ),
    "properties": {
        "language": {
            "type": "string",
            "description": "ja prefixes the card. fr prefixes the card. Any other code does not.",
        },
        "placeName": {
            "type": "string",
            "description": "Place the driver is going. Missing or blank makes card an empty string.",
        },
        "address": {"type": "string", "description": "Street address, copied as given."},
        "arriveAt": {"type": "string", "description": "Arrival text, copied as given."},
    },
    "required": ["language", "placeName", "address", "arriveAt"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": "The language code and the card the traveler shows a driver.",
    "properties": {
        "language": {"type": "string"},
        "card": {
            "type": "string",
            "description": (
                "placeName, address, and arriveAt on three lines. "
                "ja starts with こちらまでお願いします. "
                "fr starts with À cette adresse, s'il vous plaît. "
                "Empty when placeName is missing."
            ),
        },
    },
    "required": ["language", "card"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Build the card a traveler shows a driver. The master agent calls this tool "
        "on the Amazon Bedrock AgentCore runtime when it requests a ride. This tool "
        "does not run that loop and does not request the ride. card is placeName, "
        "address, and arriveAt on three lines. language ja prefixes the card with "
        "こちらまでお願いします. language fr prefixes the card with "
        "À cette adresse, s'il vous plaît. Any other language has no prefix. "
        "A missing placeName makes card an empty string. Place text is copied as given. "
        "Never raises. Sandbox only: no translation API, no network, and no AWS."
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
    """AgentCore runtime entry for ``phrase_card``. Calls ``phrase_card``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {"language": "", "card": ""}
        return phrase_card(tool_input)
    except Exception:
        return {"language": "", "card": ""}


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
