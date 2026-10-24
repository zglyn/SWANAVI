"""Hold an outdoor segment when the caller supplies a bad forecast.

Sandbox only. The master agent calls this when a forecast signal arrives.
A shift is handed to the late and early replan agents. This function does
not move segments, call a weather API, open the network, or call AWS.
"""

from __future__ import annotations

import json

_CALL_KEYS = ("segmentId", "outdoor", "condition")
_BAD = frozenset({"rain", "storm", "snow"})
_GOOD = frozenset({"clear", "cloudy"})


def check_weather(segmentId=None, outdoor=None, condition=None) -> dict:
    """Decide whether an outdoor segment should be held.

    Indoor segments are ok. Outdoor rain, storm, or snow asks for a shift.
    Outdoor clear or cloudy is ok. Any other outdoor condition is not ok
    and does not choose an action. Never raises.
    """
    try:
        bare_payload = (
            _is_payload(segmentId)
            and outdoor is None
            and condition is None
        )
        if bare_payload:
            data = _load(segmentId)
        else:
            data = {
                "segmentId": segmentId,
                "outdoor": outdoor,
                "condition": condition,
            }
        if not isinstance(data, dict):
            return _invalid("")
        return _decide(data)
    except Exception:
        return _invalid("")


def _decide(data: dict) -> dict:
    segment_id = _text(data.get("segmentId"))
    outdoor = data.get("outdoor")
    if outdoor is False:
        return _result(segment_id, True, "none", "indoor")
    if outdoor is not True:
        return _invalid(segment_id)
    condition = _condition(data.get("condition"))
    if condition in _BAD:
        return _result(segment_id, False, "shift", condition)
    if condition in _GOOD:
        return _result(segment_id, True, "none", condition)
    return _result(segment_id, False, "none", "unknown_condition")


def _invalid(segment_id: str) -> dict:
    return _result(segment_id, False, "none", "invalid_input")


def _result(segment_id: str, ok: bool, action: str, reason: str) -> dict:
    return {
        "segmentId": segment_id,
        "ok": ok,
        "action": action,
        "reason": reason,
    }


def _condition(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _is_payload(value) -> bool:
    return isinstance(value, (dict, str))


def _load(payload):
    if isinstance(payload, str):
        loaded = json.loads(payload)
        if not isinstance(loaded, dict):
            return None
        payload = loaded
    if not isinstance(payload, dict):
        return None
    return _unwrap(payload)


def _unwrap(payload: dict) -> dict:
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    nested = payload.get("input")
    if isinstance(nested, dict) and not any(key in payload for key in _CALL_KEYS):
        return nested
    return payload


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
