"""AgentCore tool spec for ``check_entry``.

The master agent calls this tool on the Amazon Bedrock AgentCore runtime
before the trip starts. This module does not run that loop. Register
``TOOL_SPEC`` (or pass ``AGENTCORE_TOOL`` on harness invoke). When the runtime
hands back a ``check_entry`` call, run ``handler``. ``handler`` calls
``check_entry``.
"""

from __future__ import annotations

from .entry import ISSUE_FAILED, check_entry

TOOL_NAME = "check_entry"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Passport and visa facts the master already has. This tool does not look up "
        "entry rules for the destination. passportExpiry and tripEnd are YYYY-MM-DD."
    ),
    "properties": {
        "destinationCountry": {
            "type": "string",
            "description": "Destination country supplied by the caller. Not looked up.",
        },
        "passportExpiry": {
            "type": "string",
            "description": "Passport expiry date, YYYY-MM-DD.",
        },
        "tripEnd": {
            "type": "string",
            "description": "Trip end date, YYYY-MM-DD.",
        },
        "visaOnFile": {
            "type": "boolean",
            "description": "True only when the traveler already has the visa on file.",
        },
    },
    "required": ["destinationCountry", "passportExpiry", "tripEnd", "visaOnFile"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {
            "type": "boolean",
            "description": (
                "False when passportExpiry is missing, when passportExpiry is less than "
                "180 days after tripEnd, or when visaOnFile is false. True otherwise."
            ),
        },
        "issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Why entry is not ok. Empty when ok is true.",
        },
    },
    "required": ["ok", "issues"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Check passport expiry and visa on file before the trip starts. The master agent "
        "calls this tool on the Amazon Bedrock AgentCore runtime before the trip starts. "
        "This tool does not run that loop. ok is false when passportExpiry is missing, "
        "when passportExpiry is less than 180 days after tripEnd, or when visaOnFile is "
        "false. Otherwise ok is true and issues is empty. Sandbox only: no network and no AWS."
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
    """AgentCore runtime entry for ``check_entry``. Calls ``check_entry``."""
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "ok": False,
                "issues": ["unsupported AgentCore tool; expected check_entry"],
            }
        return check_entry(tool_input)
    except Exception:
        return {"ok": False, "issues": [ISSUE_FAILED]}


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
