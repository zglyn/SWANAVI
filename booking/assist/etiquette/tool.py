"""AgentCore tool spec for ``etiquette_card``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
before a stop. This module does not run that loop. A later integrator wires
the master. Register ``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness
invoke). When the runtime hands back an ``etiquette_card`` call, run
``handler``. ``handler`` calls ``etiquette_card``.

Fixed sandbox phrases. Not medical, legal, or safety advice, and not a map.
"""

from __future__ import annotations

from .card import UNKNOWN_COUNTRY, etiquette_card

TOOL_NAME = "etiquette_card"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Country, stop name, and stop kind. A partial payload is accepted and "
        "does not raise. placeName is not used to choose the card."
    ),
    "properties": {
        "country": {
            "type": "string",
            "description": (
                "Country name. The sandbox directory has Japan, France, and "
                "the United States. Any other country uses reason unknown_country."
            ),
        },
        "placeName": {
            "type": "string",
            "description": (
                "Stop name, accepted as given. Not a map lookup and not used "
                "to choose the card."
            ),
        },
        "kind": {
            "type": "string",
            "enum": ["shrine", "temple", "museum", "restaurant", "general"],
            "description": (
                "shrine or temple, museum (including a church-like stop), "
                "restaurant, or general."
            ),
        },
    },
    "required": ["country", "placeName", "kind"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Fixed etiquette card. Not medical, legal, or safety advice, and not a map."
    ),
    "properties": {
        "country": {
            "type": "string",
            "description": (
                "Japan, France, or United States when the directory matches. "
                "Otherwise the country text the caller sent."
            ),
        },
        "kind": {
            "type": "string",
            "description": "shrine, temple, museum, restaurant, general, or empty when kind is missing.",
        },
        "rules": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Fixed sandbox etiquette lines. Empty when this stop has no card.",
        },
        "phrase": {
            "type": ["string", "null"],
            "description": "Fixed sandbox phrase. Null when this stop has no card.",
        },
        "phraseLanguage": {
            "type": ["string", "null"],
            "description": "ja or fr when phrase is set. Null when phrase is null.",
        },
        "phraseMeaning": {
            "type": ["string", "null"],
            "description": "English meaning of phrase. Null when phrase is null.",
        },
        "reason": {
            "type": "string",
            "enum": ["none", "unknown_country"],
            "description": (
                "none when the country is in the sandbox directory. "
                "unknown_country otherwise."
            ),
        },
    },
    "required": [
        "country",
        "kind",
        "rules",
        "phrase",
        "phraseLanguage",
        "phraseMeaning",
        "reason",
    ],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Return a fixed etiquette card for one stop. The master agent calls this "
        "tool on the Amazon Bedrock AgentCore runtime. This tool does not run that "
        "loop. A later integrator wires the master. Sandbox phrases only: no "
        "translation API, no network, and no AWS. Not medical, legal, or safety "
        "advice, and not a map. placeName is not used to choose the card. "
        "Japan shrine or temple: shoes off before the hall, bow once at the gate, "
        "photography of the inner hall is restricted, phrase 写真は大丈夫ですか, "
        "language ja, meaning May I take a photo?. Japan restaurant: no tipping, "
        "shoes off only at a tatami room, phrase 予約しています, meaning I have a "
        "reservation. France museum, including a church-like stop passed as kind "
        "museum: quiet inside, shoulders covered, phrase "
        "Pardon, une photo est-elle permise ?, meaning Excuse me, are photos allowed?. "
        "The United States returns empty rules, a null phrase, and reason none. "
        "Any other country returns empty rules, a null phrase, and reason "
        "unknown_country."
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
    """AgentCore runtime entry for ``etiquette_card``. Calls ``etiquette_card``."""
    try:
        result = etiquette_card(tool_input)
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "country": result.get("country") if isinstance(result.get("country"), str) else "",
                "kind": result.get("kind") if isinstance(result.get("kind"), str) else "",
                "rules": [],
                "phrase": None,
                "phraseLanguage": None,
                "phraseMeaning": None,
                "reason": UNKNOWN_COUNTRY,
            }
        return result
    except Exception:
        return {
            "country": "",
            "kind": "",
            "rules": [],
            "phrase": None,
            "phraseLanguage": None,
            "phraseMeaning": None,
            "reason": UNKNOWN_COUNTRY,
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
