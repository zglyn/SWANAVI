"""Amazon Bedrock AgentCore tool for hotel confirmation emails.

The master agent calls this tool on the AgentCore runtime after ``book_hotel``.
The runtime calls ``handler``. Sandbox only: no network, no inbox, and no AWS.
"""

from __future__ import annotations

import json

from .email import sample_email, verify

TOOL_NAME = "verify_hotel_email"

TOOL_SPEC = {
    "name": TOOL_NAME,
    "description": (
        "Check the hotel confirmation email for one booked segment. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore "
        "runtime after book_hotel. Sandbox only: no network, no real inbox, "
        "and no AWS. operation \"verify\" checks subject and body for the "
        "confirmation code, city, check-in, check-out, and guest names. "
        "operation \"sample_email\" returns the sandbox email a traveler "
        "would receive after the hotel books."
    ),
    "inputSchema": {
        "type": "object",
        "description": (
            "Verify a confirmation email, or build the sandbox email. "
            "confirmationCode is accepted as an alias of confirmation_code."
        ),
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["verify", "sample_email"],
                "description": 'Defaults to "verify".',
            },
            "email": {
                "type": "object",
                "description": "Confirmation email. Required for verify.",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "receivedAt": {"type": "string"},
                },
            },
            "segment": {
                "type": "object",
                "description": "Hotel segment from the trip plan.",
                "properties": {
                    "segmentId": {"type": "string"},
                    "kind": {"type": "string", "description": 'Must be "hotel".'},
                    "city": {"type": "string"},
                    "checkIn": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                    "checkOut": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                },
                "required": ["segmentId", "city", "checkIn", "checkOut"],
            },
            "confirmation_code": {"type": "string"},
            "confirmationCode": {
                "type": "string",
                "description": "Alias of confirmation_code from book_hotel.",
            },
            "travelers": {
                "type": "array",
                "description": "Guests. Each item is a name or an object with a name.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                    },
                },
            },
            "trip_id": {
                "type": "string",
                "description": "Trip id. Used by sample_email.",
            },
        },
        "required": ["segment", "travelers"],
    },
    "outputSchema": {
        "type": "object",
        "description": (
            "verify returns segmentId, kind \"hotel\", verified, and reason. "
            "sample_email returns from, to, subject, body, and receivedAt."
        ),
        "properties": {
            "segmentId": {"type": "string"},
            "kind": {"type": "string"},
            "verified": {"type": "boolean"},
            "reason": {"type": "string"},
            "from": {"type": "string"},
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "receivedAt": {"type": "string"},
        },
    },
}


def handler(event, context=None):
    """AgentCore runtime entry for ``verify_hotel_email``.

    The default operation is ``verify``. ``operation`` ``sample_email`` returns
    the sandbox confirmation email. A bad email does not raise.
    """
    try:
        return _handler(event, context)
    except Exception:
        return _rejected("", "confirmation email could not be checked")


def _handler(event, context):
    tool_name = _tool_name(context)
    payload = _payload(event)
    if tool_name is not None and tool_name != TOOL_NAME:
        segment = payload.get("segment") if isinstance(payload, dict) else None
        return _rejected(
            _segment_id(segment),
            "unsupported AgentCore tool; expected verify_hotel_email",
        )
    if payload is None:
        return _rejected("", "verify_hotel_email input must be an object")

    operation = payload.get("operation", payload.get("action", "verify"))
    if not isinstance(operation, str) or not operation.strip():
        operation = "verify"
    operation = operation.strip().lower()

    segment = payload.get("segment")
    travelers = payload.get("travelers")
    code = payload.get("confirmation_code", payload.get("confirmationCode"))
    trip_id = payload.get("trip_id", payload.get("tripId"))
    if operation == "sample_email":
        return sample_email(segment, code, travelers, trip_id)
    if operation != "verify":
        return _rejected(_segment_id(segment), "unknown operation")
    return verify(payload.get("email"), segment, code, travelers)


def _payload(event: object) -> dict | None:
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            return None
    if isinstance(event, dict) and isinstance(event.get("arguments"), dict):
        event = event["arguments"]
    if not isinstance(event, dict):
        return None
    return event


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


def _segment_id(segment: object) -> str:
    if not isinstance(segment, dict):
        return ""
    segment_id = segment.get("segmentId")
    if isinstance(segment_id, str) and segment_id.strip():
        return segment_id.strip()
    return ""


def _rejected(segment_id: str, reason: str) -> dict:
    return {
        "segmentId": segment_id,
        "kind": "hotel",
        "verified": False,
        "reason": reason,
    }
