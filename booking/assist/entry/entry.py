"""Check passport expiry and visa on file before the trip starts.

Sandbox only: the caller supplies every field. This module does not look up
visa rules, open the network, or call AWS. The master agent calls
``check_entry`` before the trip starts.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

PASSPORT_VALIDITY_DAYS = 180

ISSUE_PASSPORT_MISSING = "passportExpiry is missing"
ISSUE_PASSPORT_INVALID = "passportExpiry must be YYYY-MM-DD"
ISSUE_TRIP_END_MISSING = "tripEnd is missing"
ISSUE_TRIP_END_INVALID = "tripEnd must be YYYY-MM-DD"
ISSUE_PASSPORT_SHORT = "passportExpiry is less than 180 days after tripEnd"
ISSUE_VISA_MISSING = "visaOnFile is missing"
ISSUE_VISA_FALSE = "visaOnFile is false"
ISSUE_FAILED = "check_entry failed"

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ENVELOPE_KEYS = ("destinationCountry", "passportExpiry", "tripEnd", "visaOnFile")


def check_entry(source=None) -> dict:
    """Return ``ok`` and ``issues``. Never raises.

    ``source`` is ``{destinationCountry, passportExpiry, tripEnd, visaOnFile}``
    or a JSON object with those fields. ``passportExpiry`` and ``tripEnd`` are
    ``YYYY-MM-DD``. ``ok`` is false when ``passportExpiry`` is missing, when
    ``passportExpiry`` is less than 180 days after ``tripEnd``, or when
    ``visaOnFile`` is false. Otherwise ``ok`` is true and ``issues`` is empty.
    """
    try:
        return _decide(_mapping(source))
    except Exception:
        return _result([ISSUE_FAILED])


def _mapping(source) -> dict:
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError:
            return {}
    if not isinstance(source, dict):
        return {}
    arguments = source.get("arguments")
    if isinstance(arguments, dict):
        source = arguments
    elif isinstance(source.get("input"), dict) and not _looks_like_entry(source):
        source = source["input"]
    if not isinstance(source, dict):
        return {}
    return source


def _looks_like_entry(value: dict) -> bool:
    return any(key in value for key in _ENVELOPE_KEYS)


def _decide(data: dict) -> dict:
    issues: list[str] = []
    expiry, expiry_issue = _require_date(
        data,
        "passportExpiry",
        ISSUE_PASSPORT_MISSING,
        ISSUE_PASSPORT_INVALID,
    )
    trip_end, trip_end_issue = _require_date(
        data,
        "tripEnd",
        ISSUE_TRIP_END_MISSING,
        ISSUE_TRIP_END_INVALID,
    )
    if expiry_issue:
        issues.append(expiry_issue)
    if trip_end_issue:
        issues.append(trip_end_issue)
    if (
        expiry is not None
        and trip_end is not None
        and expiry < trip_end + timedelta(days=PASSPORT_VALIDITY_DAYS)
    ):
        issues.append(ISSUE_PASSPORT_SHORT)
    visa_issue = _visa_issue(data)
    if visa_issue:
        issues.append(visa_issue)
    return _result(issues)


def _require_date(data: dict, key: str, missing: str, invalid: str):
    if key not in data or _blank(data.get(key)):
        return None, missing
    parsed = _parse_date(data.get(key))
    if parsed is None:
        return None, invalid
    return parsed, None


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _parse_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _DATE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _visa_issue(data: dict) -> str | None:
    if "visaOnFile" not in data or data.get("visaOnFile") is None:
        return ISSUE_VISA_MISSING
    if data["visaOnFile"] is True:
        return None
    return ISSUE_VISA_FALSE


def _result(issues: list[str]) -> dict:
    return {"ok": not issues, "issues": issues}
