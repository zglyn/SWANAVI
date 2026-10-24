"""Booking state.

Local runs keep state in the process so a demo works with no AWS credentials.
When AgentCore injects a memory id, the same state is stored as short-term
memory events through MemorySessionManager.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

logger = logging.getLogger(__name__)

ACTOR_ID = "booking-orchestrator"
STATE_MARKER = "booking-state:"

# Set by `agentcore add memory --name BookingMemory`, or directly for a memory you already created.
MEMORY_ID_ENV = ("AGENTCORE_MEMORY_ID", "MEMORY_BOOKINGMEMORY_ID")


class BookingMemory(Protocol):
    def load(self, trip_id: str) -> list[dict[str, Any]]: ...

    def save(self, trip_id: str, results: list[dict[str, Any]]) -> None: ...


class LocalBookingMemory:
    """Process-local stand-in for AgentCore Memory. Not shared across processes."""

    def __init__(self) -> None:
        self._by_trip: dict[str, list[dict[str, Any]]] = {}

    def load(self, trip_id: str) -> list[dict[str, Any]]:
        stored = self._by_trip.get(trip_id)
        if stored is None:
            return []
        return json.loads(json.dumps(stored))

    def save(self, trip_id: str, results: list[dict[str, Any]]) -> None:
        self._by_trip[trip_id] = json.loads(json.dumps(results))


_PROCESS_LOCAL = LocalBookingMemory()


def encode_state(results: list[dict[str, Any]]) -> str:
    return STATE_MARKER + json.dumps(results, separators=(",", ":"), default=str)


def decode_state(text: str) -> list[dict[str, Any]] | None:
    if not isinstance(text, str) or not text.startswith(STATE_MARKER):
        return None
    try:
        parsed = json.loads(text[len(STATE_MARKER) :])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed


def _event_texts(event: Any) -> list[str]:
    payload = event.get("payload") if hasattr(event, "get") else None
    if not isinstance(payload, list):
        return []
    texts: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        conversational = item.get("conversational")
        if not isinstance(conversational, dict):
            continue
        content = conversational.get("content")
        if isinstance(content, dict) and isinstance(content.get("text"), str):
            texts.append(content["text"])
    return texts


class AgentCoreBookingMemory:
    """Short-term AgentCore Memory keyed by trip id.

    ``session_factory`` is for tests. Production builds a MemorySession from
    bedrock_agentcore.memory.MemorySessionManager on first use.
    """

    def __init__(
        self,
        memory_id: str,
        region_name: str | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self._memory_id = memory_id
        self._region_name = region_name
        self._session_factory = session_factory
        self._local = LocalBookingMemory()
        self._remote_unavailable = False

    def load(self, trip_id: str) -> list[dict[str, Any]]:
        if self._remote_unavailable:
            return self._local.load(trip_id)
        try:
            return self._load_remote(trip_id)
        except Exception as exc:
            logger.warning("AgentCore Memory read failed (%s); using process-local booking state", exc)
            self._remote_unavailable = True
            return self._local.load(trip_id)

    def save(self, trip_id: str, results: list[dict[str, Any]]) -> None:
        if self._remote_unavailable:
            self._local.save(trip_id, results)
            return
        try:
            self._save_remote(trip_id, results)
        except Exception as exc:
            logger.warning("AgentCore Memory write failed (%s); using process-local booking state", exc)
            self._remote_unavailable = True
            self._local.save(trip_id, results)

    def _session(self, trip_id: str) -> Any:
        if self._session_factory is not None:
            return self._session_factory(trip_id)
        from bedrock_agentcore.memory import MemorySessionManager

        manager = MemorySessionManager(memory_id=self._memory_id, region_name=self._region_name)
        return manager.create_memory_session(actor_id=ACTOR_ID, session_id=trip_id)

    def _load_remote(self, trip_id: str) -> list[dict[str, Any]]:
        session = self._session(trip_id)
        events = session.list_events(max_results=100, include_payload=True)
        found: list[dict[str, Any]] | None = None
        for event in events:
            for text in _event_texts(event):
                decoded = decode_state(text)
                if decoded is not None:
                    found = decoded
        return found or []

    def _save_remote(self, trip_id: str, results: list[dict[str, Any]]) -> None:
        from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

        session = self._session(trip_id)
        session.add_turns(
            messages=[ConversationalMessage(encode_state(results), MessageRole.ASSISTANT)],
            metadata={
                "recordType": {"stringValue": "booking-state"},
                "tripId": {"stringValue": trip_id},
            },
        )


def memory_from_env() -> BookingMemory:
    """AgentCore Memory when a memory id is configured, otherwise process-local state."""

    memory_id = next((os.environ[name] for name in MEMORY_ID_ENV if os.environ.get(name)), None)
    if not memory_id:
        return _PROCESS_LOCAL
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    return AgentCoreBookingMemory(memory_id=memory_id, region_name=region)
