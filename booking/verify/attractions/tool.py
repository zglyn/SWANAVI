"""Amazon Bedrock AgentCore tool ``verify_attraction_email``.

The master agent calls this tool on the AgentCore runtime after
``book_attraction``. The handler runs ``sample_email`` or ``verify``. This
module does not call AWS.
"""

from __future__ import annotations

import json

from .email import sample_email, verify

TOOL_NAME = "verify_attraction_email"

_SEGMENT_SCHEMA = {
    "type": "object",
    "description": "Attraction segment from the trip plan.",
    "properties": {
        "segmentId": {"type": "string"},
        "kind": {"type": "string", "description": 'Must be "attraction".'},
        "name": {"type": "string"},
        "city": {"type": "string"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "partySize": {"type": "integer"},
        "time": {"type": "string", "description": "HH:MM, or omit when unknown."},
    },
    "required": ["segmentId", "kind", "name", "city", "date", "partySize"],
}

_EMAIL_SCHEMA = {
    "type": "object",
    "description": "Sandbox confirmation email. Checked fields are subject and body.",
    "properties": {
        "from": {"type": "string"},
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "receivedAt": {"type": "string", "description": "ISO-8601 timestamp."},
    },
    "required": ["from", "to", "subject", "body", "receivedAt"],
}

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["sample_email", "verify"],
            "description": (
                "sample_email builds the sandbox confirmation. "
                "verify checks an email against the segment."
            ),
        },
        "segment": _SEGMENT_SCHEMA,
        "confirmation_code": {"type": "string"},
        "travelers": {
            "type": "array",
            "description": "Travelers on the trip. Used as the sandbox To line.",
            "items": {"type": "object"},
        },
        "trip_id": {
            "type": "string",
            "description": "Trip id. Used by sample_email.",
        },
        "email": _EMAIL_SCHEMA,
    },
    "required": ["action", "segment", "confirmation_code", "travelers"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "description": (
        "sample_email returns from, to, subject, body, and receivedAt. "
        "verify returns segmentId, kind, verified, and reason."
    ),
    "properties": {
        "from": {"type": "string"},
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "receivedAt": {"type": "string"},
        "segmentId": {"type": "string"},
        "kind": {"type": "string", "description": "attraction"},
        "verified": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}

VERIFY_ATTRACTION_EMAIL_TOOL = {
    "name": TOOL_NAME,
    "description": (
        "Check the sandbox confirmation email for one attraction ticket. "
        "The master agent calls this tool on the Amazon Bedrock AgentCore runtime "
        "after book_attraction. "
        "action sample_email builds the email the traveler would receive, including "
        "the confirmation code, attraction name, city, date, and party size. "
        "action verify returns verified true only when the confirmation code, "
        "attraction name, date, and party size all appear in the subject or body. "
        "Sandbox only: no network, no inbox, and no AWS."
    ),
    "inputSchema": INPUT_SCHEMA,
    "outputSchema": OUTPUT_SCHEMA,
}


def verify_attraction_email(event: dict | str | None = None, context: object = None, **kwargs) -> dict:
    """AgentCore runtime entry for ``verify_attraction_email``.

    ``action`` ``sample_email`` calls ``sample_email``. ``action`` ``verify``
    calls ``verify``. A bad payload returns ``verified: false`` and does not raise.
    """

    del context
    try:
        payload = _payload(event, kwargs)
        action = payload.get("action")
        segment = payload.get("segment")
        code = payload.get("confirmation_code")
        if code is None:
            code = payload.get("confirmationCode")
        travelers = payload.get("travelers")
        if action == "verify" or (action is None and "email" in payload):
            return verify(payload.get("email"), segment, code, travelers)
        if action in (None, "sample_email"):
            trip_id = payload.get("trip_id")
            if trip_id is None:
                trip_id = payload.get("tripId")
            return sample_email(segment, code, travelers, trip_id)
        segment_id = segment.get("segmentId") if isinstance(segment, dict) else ""
        if not isinstance(segment_id, str):
            segment_id = ""
        return {
            "segmentId": segment_id,
            "kind": "attraction",
            "verified": False,
            "reason": "unknown action",
        }
    except Exception:
        return {
            "segmentId": "",
            "kind": "attraction",
            "verified": False,
            "reason": "confirmation email could not be read",
        }


def _payload(event: dict | str | None, kwargs: dict) -> dict:
    data: dict = {}
    if isinstance(event, str):
        loaded = json.loads(event)
        if not isinstance(loaded, dict):
            raise TypeError("tool input must be an object")
        data = loaded
    elif isinstance(event, dict):
        data = dict(event)
    elif event is not None:
        raise TypeError("tool input must be an object")
    data.update(kwargs)
    return data
