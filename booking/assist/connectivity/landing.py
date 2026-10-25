"""Label a sandbox eSIM so the phone has data before a ride is requested.

Sandbox only. The plan code is a label. This module does not buy a plan,
call a carrier, install an eSIM, open the network, or call AWS. It does not
read the wall clock and does not run the master loop. A later integrator
wires the master. A partial input returns a result and does not raise.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

PLAN_PREFIX = "SANDBOX-ESIM-"
WINDOW = timedelta(hours=2)

STATUS_READY = "ready"
STATUS_REMIND = "remind"
STATUS_INSTALL = "install"
STATUS_NEEDS_USER = "needs_user"

ACTION_NONE = "none"
ACTION_REMIND = "remind"
ACTION_INSTALL = "install_esim"

_UNKNOWN_COUNTRY = frozenset(
    {
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
        "tbd",
        "tba",
        "?",
        "-",
    }
)

_ENVELOPE_KEYS = (
    "country",
    "arriveAt",
    "arrive_at",
    "now",
    "hasData",
    "has_data",
)


def landing_data(country=None, arriveAt=None, now=None, hasData=None) -> dict:
    """Decide whether the phone needs a sandbox data label. Never raises.

    ``country`` may be the country, or one object with ``country``,
    ``arriveAt``, ``now``, and ``hasData``. ``arriveAt`` and ``now`` are
    ISO-8601 timestamps. The caller supplies ``now``.

    An empty or unknown country is ``needs_user``. When ``hasData`` is true
    the status is ``ready`` and ``planCode`` is null. When ``hasData`` is
    false and ``now`` is earlier than ``arriveAt`` minus 2 hours, the status
    is ``remind`` and ``remindAt`` is that instant. Inside that 2-hour window,
    or after arrival, the status is ``install``, the action is
    ``install_esim``, and ``planCode`` starts with ``SANDBOX-ESIM-``.
    """
    try:
        fields = _normalize(country, arriveAt, now, hasData)
        return _decide(fields)
    except Exception:
        return _needs_user("")


def _normalize(country, arriveAt, now, hasData) -> dict:
    if isinstance(country, str) and arriveAt is None and now is None and hasData is None:
        loaded = _json_object(country)
        if isinstance(loaded, dict):
            country = loaded
    if isinstance(country, dict) and arriveAt is None and now is None and hasData is None:
        source = country
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        return {
            "country": source.get("country"),
            "arriveAt": source.get("arriveAt", source.get("arrive_at")),
            "now": source.get("now"),
            "hasData": source.get("hasData", source.get("has_data")),
        }
    return {
        "country": country,
        "arriveAt": arriveAt,
        "now": now,
        "hasData": hasData,
    }


def _decide(fields: dict) -> dict:
    country = _country_text(fields.get("country"))
    if not _known_country(country):
        return _needs_user(country or "")

    has_data = _has_data(fields.get("hasData"))
    if has_data is None:
        return _needs_user(country)
    if has_data:
        return _result(country, STATUS_READY, ACTION_NONE, None, None)

    arrive = _instant(fields.get("arriveAt"))
    current = _instant(fields.get("now"))
    if arrive is None or current is None:
        return _needs_user(country)

    remind_at = arrive - WINDOW
    if current < remind_at:
        return _result(country, STATUS_REMIND, ACTION_REMIND, None, _format(remind_at))
    return _result(country, STATUS_INSTALL, ACTION_INSTALL, _plan_code(country, arrive), None)


def _needs_user(country: str) -> dict:
    return _result(country, STATUS_NEEDS_USER, ACTION_NONE, None, None)


def _result(country: str, status: str, action: str, plan_code: str | None, remind_at: str | None) -> dict:
    return {
        "country": country,
        "status": status,
        "action": action,
        "planCode": plan_code,
        "remindAt": remind_at,
    }


def _plan_code(country: str, arrive_at: datetime) -> str:
    """Stable sandbox label. Not an order and not a carrier plan id."""
    raw = f"{country.casefold()}|{_format(arrive_at)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"{PLAN_PREFIX}{digest}"


def _country_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _known_country(country: str | None) -> bool:
    if not country:
        return False
    key = " ".join(country.casefold().split())
    if key in _UNKNOWN_COUNTRY:
        return False
    return sum(1 for char in country if char.isalpha()) >= 2


def _has_data(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


def _instant(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "T" not in text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_object(text: str):
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return loaded
    return None
