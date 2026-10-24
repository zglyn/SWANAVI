"""AgentCore tool spec for `verify_flight_email`.

The only supported invoke path is the Amazon Bedrock AgentCore runtime.
The master agent calls this tool after `book_flight`. Register `TOOL_SPEC`
(or pass `AGENTCORE_TOOL` on harness invoke). When the runtime hands back a
`verify_flight_email` call, run `handler`. `handler` calls `verify`.

Sandbox only: the handler does not read an inbox and does not call AWS.
"""

from __future__ import annotations

import json

from .verify import verify

TOOL_NAME = "verify_flight_email"

INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Flight confirmation email plus the booked segment, confirmation code, "
        "and travelers. Checked after book_flight."
    ),
    "properties": {
        "email": {
            "type": "object",
            "description": (
                "Confirmation email. subject and body are checked. "
                "Sandbox emails come from sample_email and are not delivered."
            ),
            "properties": {
                "from": {"type": "string", "description": "Sender address."},
                "to": {"type": "string", "description": "Recipient address."},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "receivedAt": {"type": "string", "description": "ISO-8601 receipt time."},
            },
        },
        "segment": {
            "type": "object",
            "description": "The flight segment that was booked.",
            "properties": {
                "segmentId": {"type": "string"},
                "kind": {"type": "string", "description": "flight"},
                "from": {"type": "string", "description": "Origin IATA code."},
                "to": {"type": "string", "description": "Destination IATA code."},
                "departDate": {"type": "string", "description": "Departure date, YYYY-MM-DD."},
                "travelerIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ids of travelers on this segment.",
                },
            },
            "required": ["segmentId", "from", "to", "departDate"],
        },
        "confirmation_code": {
            "type": "string",
            "description": "Code returned by book_flight. confirmationCode is accepted as an alias.",
        },
        "travelers": {
            "type": "array",
            "description": "Traveler profiles. Each name is givenName plus familyName, or name.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "givenName": {"type": "string"},
                    "familyName": {"type": "string"},
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["id"],
            },
        },
    },
    "required": ["email", "segment", "confirmation_code", "travelers"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Flight email check. verified is true only when the confirmation code, "
        "route, depart date, and traveler names appear in the subject or body."
    ),
    "properties": {
        "segmentId": {"type": "string"},
        "kind": {"type": "string", "description": "flight"},
        "verified": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["segmentId", "kind", "verified", "reason"],
}

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Check the flight confirmation email after book_flight. "
        "Verified only when the confirmation code, route, depart date, and "
        "traveler names appear in the subject or body. "
        "The only supported invoke path is the Amazon Bedrock AgentCore runtime. "
        "Sandbox only: no network, no inbox, and no AWS."
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


def handler(tool_input: dict | str, context: object = None) -> dict:
    """AgentCore runtime entry for `verify_flight_email`. Calls `verify`.

    A bad payload returns verified false and does not raise.
    """
    try:
        tool_name = _tool_name(context)
        if tool_name is not None and tool_name != TOOL_NAME:
            return {
                "segmentId": "",
                "kind": "flight",
                "verified": False,
                "reason": "unsupported AgentCore tool; expected verify_flight_email",
            }
        payload = _payload(tool_input)
        if payload is None:
            return {
                "segmentId": "",
                "kind": "flight",
                "verified": False,
                "reason": "verify_flight_email input must be an object",
            }
        code = payload.get("confirmation_code", payload.get("confirmationCode"))
        return verify(
            payload.get("email"),
            payload.get("segment"),
            code,
            payload.get("travelers"),
        )
    except Exception:
        return {
            "segmentId": "",
            "kind": "flight",
            "verified": False,
            "reason": "verify_flight_email input could not be read",
        }


def _payload(tool_input: object) -> dict | None:
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            return None
    if isinstance(tool_input, dict) and isinstance(tool_input.get("arguments"), dict):
        tool_input = tool_input["arguments"]
    if not isinstance(tool_input, dict):
        return None
    return tool_input


def _tool_name(context: object) -> str | None:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None)
    if not isinstance(custom, dict):
        return None
    raw = custom.get("bedrockAgentCoreToolName")
    if not isinstance(raw, str) or not raw.strip():
        return None
    # Gateway tool names are "{target}___{tool}".
    if "___" in raw:
        return raw.split("___", 1)[1]
    return raw.strip()
