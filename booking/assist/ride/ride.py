"""Request a car from the attraction that is ending to the next stop.

Sandbox is the default. The Uber Rides API client runs only when
``ROAM_RIDE_PROVIDER=live`` and ``UBER_ACCESS_TOKEN`` is set. A missing
``pickupAt`` or ``dropoffName`` returns ``status: failed`` and does not raise.
This module does not run the master loop.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

PROVIDER_ENV = "ROAM_RIDE_PROVIDER"
TOKEN_ENV = "UBER_ACCESS_TOKEN"

REASON_NO_PICKUP_AT = "pickupAt is missing"
REASON_BAD_PICKUP_AT = "pickupAt must be an ISO-8601 time"
REASON_NO_DROPOFF = "dropoffName is missing"
REASON_UNREADABLE = "request_ride could not read the input"

_ENVELOPE_KEYS = (
    "fromSegmentId",
    "from_segment_id",
    "toSegmentId",
    "to_segment_id",
    "pickupAt",
    "pickup_at",
    "pickupName",
    "pickup_name",
    "dropoffName",
    "dropoff_name",
    "partySize",
    "party_size",
)


def request_ride(
    fromSegmentId=None,
    toSegmentId=None,
    pickupAt=None,
    pickupName=None,
    dropoffName=None,
    partySize=None,
) -> dict:
    """Request a ride, or return a failed result.

    The first argument may be the ``fromSegmentId``, or one object with
    ``fromSegmentId``, ``toSegmentId``, ``pickupAt``, ``pickupName``,
    ``dropoffName``, and ``partySize``. Never raises.
    """
    try:
        fields = _normalize(fromSegmentId, toSegmentId, pickupAt, pickupName, dropoffName, partySize)
        return _request(fields)
    except Exception:
        return _result("failed", None, None, None, None, REASON_UNREADABLE)


def _normalize(fromSegmentId, toSegmentId, pickupAt, pickupName, dropoffName, partySize) -> dict:
    if (
        isinstance(fromSegmentId, str)
        and toSegmentId is None
        and pickupAt is None
        and pickupName is None
        and dropoffName is None
        and partySize is None
    ):
        try:
            loaded = json.loads(fromSegmentId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            fromSegmentId = loaded
    if (
        isinstance(fromSegmentId, dict)
        and toSegmentId is None
        and pickupAt is None
        and pickupName is None
        and dropoffName is None
        and partySize is None
    ):
        source = fromSegmentId
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        return _fields(source)
    return {
        "fromSegmentId": fromSegmentId,
        "toSegmentId": toSegmentId,
        "pickupAt": pickupAt,
        "pickupName": pickupName,
        "dropoffName": dropoffName,
        "partySize": partySize,
    }


def _fields(source: dict) -> dict:
    return {
        "fromSegmentId": source.get("fromSegmentId", source.get("from_segment_id")),
        "toSegmentId": source.get("toSegmentId", source.get("to_segment_id")),
        "pickupAt": source.get("pickupAt", source.get("pickup_at")),
        "pickupName": source.get("pickupName", source.get("pickup_name")),
        "dropoffName": source.get("dropoffName", source.get("dropoff_name")),
        "partySize": source.get("partySize", source.get("party_size")),
    }


def _request(fields: dict) -> dict:
    pickup_at = _text(fields.get("pickupAt"))
    dropoff_name = _text(fields.get("dropoffName"))
    party_size = _party_size(fields.get("partySize"))
    if pickup_at is None:
        return _result("failed", None, None, dropoff_name, party_size, REASON_NO_PICKUP_AT)
    if not _iso_datetime(pickup_at):
        return _result("failed", None, pickup_at, dropoff_name, party_size, REASON_BAD_PICKUP_AT)
    if dropoff_name is None:
        return _result("failed", None, pickup_at, None, party_size, REASON_NO_DROPOFF)

    pickup_name = _text(fields.get("pickupName")) or ""
    client = _live_client()
    if client is None:
        return _sandbox(fields, pickup_at, pickup_name, dropoff_name, party_size)
    try:
        result = client.request(pickup_name, dropoff_name, pickup_at, party_size)
    except Exception as exc:
        return _result("failed", None, pickup_at, dropoff_name, party_size, _live_reason(exc))
    return _normalize_live(result, pickup_at, dropoff_name, party_size)


def _sandbox(fields: dict, pickup_at: str, pickup_name: str, dropoff_name: str, party_size: int | None) -> dict:
    return _result(
        "requested",
        _ride_code(fields, pickup_at, pickup_name, dropoff_name, party_size),
        pickup_at,
        dropoff_name,
        party_size,
        None,
    )


def _live_client():
    """Uber client only when the provider is live and an access token is set."""
    mode = os.environ.get(PROVIDER_ENV, "sandbox").strip().lower() or "sandbox"
    token = os.environ.get(TOKEN_ENV, "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if mode != "live" or not token:
        return None
    from .live import UberRidesClient

    return UberRidesClient(token)


def _normalize_live(result: object, pickup_at: str, dropoff_name: str, party_size: int | None) -> dict:
    if not isinstance(result, dict):
        return _result("failed", None, pickup_at, dropoff_name, party_size, "Uber Rides API returned an invalid result")
    status = result.get("status")
    ride_code = result.get("rideCode")
    if status != "requested" or not isinstance(ride_code, str) or not ride_code.strip():
        reason = result.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "Uber Rides API did not request a ride"
        return _result("failed", None, pickup_at, dropoff_name, party_size, reason.strip())
    return _result("requested", ride_code.strip(), pickup_at, dropoff_name, party_size, None)


def _live_reason(exc: BaseException) -> str:
    text = str(exc).strip() or "Uber Rides API request failed"
    if len(text) > 180:
        return "Uber Rides API request failed; production was not called"
    return text


def _ride_code(fields: dict, pickup_at: str, pickup_name: str, dropoff_name: str, party_size: int | None) -> str:
    raw = "|".join(
        [
            _text(fields.get("fromSegmentId")) or "",
            _text(fields.get("toSegmentId")) or "",
            pickup_at,
            pickup_name,
            dropoff_name,
            "" if party_size is None else str(party_size),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-RIDE-{digest}"


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _party_size(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1:
        return None
    return value


def _iso_datetime(value: str) -> bool:
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    if "T" not in text:
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def _result(status, ride_code, pickup_at, dropoff_name, party_size, reason) -> dict:
    return {
        "status": status,
        "rideCode": ride_code,
        "pickupAt": pickup_at,
        "dropoffName": dropoff_name,
        "partySize": party_size,
        "reason": reason,
    }
