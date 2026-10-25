"""Build one traveler notice for a trip event.

Sandbox only: no network, no AWS, and no message delivery. The master agent
calls this after a replan or a refused overcharge so the traveler gets one
message. This module does not run that loop.
"""

from __future__ import annotations

import json

EVENTS = (
    "cancelled",
    "ended_early",
    "ended_late",
    "booked",
    "over_capture_rejected",
)

_EVENT_SENTENCE = {
    "cancelled": "A segment on this trip was cancelled.",
    "ended_early": "A segment on this trip ended early.",
    "ended_late": "A segment on this trip ended late.",
    "booked": "A segment on this trip was booked.",
    "over_capture_rejected": "A charge above the authorized amount was refused.",
}

_ENVELOPE_KEYS = ("tripId", "trip_id", "event", "notes", "segmentId", "segment_id")
_FALLBACK_EVENT = "update"


def trip_notice(tripId=None, event=None, notes=None, segmentId=None) -> dict:
    """Return ``tripId``, ``subject``, and ``body``. Never raises.

    ``tripId`` may be the id, or one object with ``tripId``, ``event``,
    ``notes``, and ``segmentId``. ``subject`` and ``body`` name the event
    and include every note. Empty notes still return both strings.
    """
    try:
        trip_id, event_name, note_list, segment_id = _normalize(tripId, event, notes, segmentId)
        return _compose(trip_id, event_name, note_list, segment_id)
    except Exception:
        return _result("", _FALLBACK_EVENT, [], "")


def _normalize(tripId, event, notes, segmentId):
    if isinstance(tripId, str) and event is None and notes is None and segmentId is None:
        try:
            loaded = json.loads(tripId)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            tripId = loaded
        else:
            return "", _FALLBACK_EVENT, [], ""
    if isinstance(tripId, dict) and event is None and notes is None and segmentId is None:
        source = tripId
        arguments = source.get("arguments")
        if isinstance(arguments, dict):
            source = arguments
        elif isinstance(source.get("input"), dict) and not any(key in source for key in _ENVELOPE_KEYS):
            source = source["input"]
        return (
            _text(source.get("tripId", source.get("trip_id"))),
            _event(source.get("event")),
            _notes(source.get("notes")),
            _text(source.get("segmentId", source.get("segment_id"))),
        )
    return _text(tripId), _event(event), _notes(notes), _text(segmentId)


def _compose(trip_id: str, event_name: str, note_list: list[str], segment_id: str) -> dict:
    return _result(trip_id, event_name, note_list, segment_id)


def _result(trip_id: str, event_name: str, note_list: list[str], segment_id: str) -> dict:
    headline = f"Trip {trip_id}: {event_name}" if trip_id else f"Trip: {event_name}"
    if segment_id:
        headline = f"{headline} ({segment_id})"
    subject = f"{headline} — {' | '.join(note_list)}" if note_list else headline

    lines = [f"Traveler notice for trip {trip_id}." if trip_id else "Traveler notice."]
    lines.append(f"Event: {event_name}.")
    sentence = _EVENT_SENTENCE.get(event_name)
    if sentence:
        lines.append(sentence)
    if segment_id:
        lines.append(f"Segment: {segment_id}.")
    if note_list:
        lines.append("Notes:")
        lines.extend(note_list)
    else:
        lines.append("No further notes.")
    return {"tripId": trip_id, "subject": subject, "body": "\n".join(lines)}


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _event(value) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return _FALLBACK_EVENT


def _notes(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        notes = []
        for item in value:
            if isinstance(item, str):
                if item:
                    notes.append(item)
            elif item is not None:
                rendered = str(item)
                if rendered:
                    notes.append(rendered)
        return notes
    return []
