"""Orchestrator behavior with and without sibling providers."""

from __future__ import annotations

import json
import os
import sys
import types
import unittest
from pathlib import Path
from typing import Any

from booking.contract import TripPlan
from booking.orchestrator.demo import FIXTURE, main
from booking.orchestrator.memory import (
    STATE_MARKER,
    AgentCoreBookingMemory,
    LocalBookingMemory,
    memory_from_env,
)
from booking.orchestrator.service import book_plan, handle_payload
from booking.orchestrator.tools import TOOLS

SAMPLE = json.loads(FIXTURE.read_text(encoding="utf-8"))
PROVIDER_NAMES = (
    "booking.providers",
    "booking.providers.flights",
    "booking.providers.hotels",
    "booking.providers.attractions",
)


def _sandbox(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
    del travelers, trip_id
    return {
        "segmentId": segment["segmentId"],
        "kind": segment["kind"],
        "status": "booked",
        "confirmationCode": f"SANDBOX-{segment['segmentId']}",
        "price": {"amount": "10.00", "currency": "USD"},
        "error": None,
    }


class ProviderSandbox(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: sys.modules.get(name) for name in PROVIDER_NAMES}
        for name in PROVIDER_NAMES:
            sys.modules.pop(name, None)

    def tearDown(self) -> None:
        for name in PROVIDER_NAMES:
            sys.modules.pop(name, None)
            if self._saved[name] is not None:
                sys.modules[name] = self._saved[name]

    def _install(self, module_name: str, book: Any) -> None:
        module = types.ModuleType(module_name)
        module.book = book
        sys.modules[module_name] = module

    def test_sample_plan_without_providers(self) -> None:
        plan = TripPlan.model_validate(SAMPLE)
        self.assertEqual({segment.kind for segment in plan.flights}, {"flight"})
        self.assertEqual(len(plan.hotels), 1)
        self.assertEqual(len(plan.attractions), 1)

        result = handle_payload(SAMPLE, LocalBookingMemory())

        self.assertEqual(result["tripId"], "sample-kyoto")
        self.assertIsNone(result["error"])
        self.assertEqual(
            [item["segmentId"] for item in result["results"]],
            ["flight-1", "hotel-1", "attraction-1"],
        )
        for item in result["results"]:
            self.assertEqual(item["status"], "failed")
            self.assertEqual(item["error"], "provider_not_installed")
            self.assertIsNone(item["confirmationCode"])
            self.assertIsNone(item["price"])

    def test_provider_failure_does_not_stop_other_segments(self) -> None:
        def explode(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
            del segment, travelers, trip_id
            raise RuntimeError("supplier_timeout")

        self._install("booking.providers.flights", explode)

        result = handle_payload(SAMPLE, LocalBookingMemory())
        by_id = {item["segmentId"]: item for item in result["results"]}

        self.assertEqual(by_id["flight-1"]["status"], "failed")
        self.assertEqual(by_id["flight-1"]["error"], "supplier_timeout")
        self.assertEqual(by_id["hotel-1"]["error"], "provider_not_installed")
        self.assertEqual(by_id["attraction-1"]["error"], "provider_not_installed")
        self.assertIsNone(by_id["flight-1"]["confirmationCode"])

    def test_installed_sandbox_providers_book_every_segment(self) -> None:
        self._install("booking.providers.flights", _sandbox)
        self._install("booking.providers.hotels", _sandbox)
        self._install("booking.providers.attractions", _sandbox)

        result = handle_payload(SAMPLE, LocalBookingMemory())

        self.assertIsNone(result["error"])
        self.assertEqual(len(result["results"]), 3)
        for item in result["results"]:
            self.assertEqual(item["status"], "booked")
            self.assertTrue(item["confirmationCode"].startswith("SANDBOX-"))
            self.assertEqual(item["price"], {"amount": "10.00", "currency": "USD"})
            self.assertIsNone(item["error"])

    def test_non_sandbox_confirmation_is_rejected(self) -> None:
        def live_code(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
            booked = _sandbox(segment, travelers, trip_id)
            booked["confirmationCode"] = "ABC123"
            return booked

        self._install("booking.providers.flights", live_code)
        self._install("booking.providers.hotels", _sandbox)
        self._install("booking.providers.attractions", _sandbox)

        result = handle_payload(SAMPLE, LocalBookingMemory())
        by_id = {item["segmentId"]: item for item in result["results"]}

        self.assertEqual(by_id["flight-1"]["status"], "failed")
        self.assertEqual(by_id["flight-1"]["error"], "non_sandbox_confirmation")
        self.assertIsNone(by_id["flight-1"]["confirmationCode"])
        self.assertEqual(by_id["hotel-1"]["status"], "booked")
        self.assertEqual(by_id["attraction-1"]["status"], "booked")

    def test_booked_segments_are_not_sent_twice(self) -> None:
        calls: list[str] = []

        def counting(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
            calls.append(segment["segmentId"])
            return _sandbox(segment, travelers, trip_id)

        for name in (
            "booking.providers.flights",
            "booking.providers.hotels",
            "booking.providers.attractions",
        ):
            self._install(name, counting)

        memory = LocalBookingMemory()
        first = handle_payload(SAMPLE, memory)
        second = handle_payload(SAMPLE, memory)

        self.assertEqual(calls, ["flight-1", "hotel-1", "attraction-1"])
        self.assertEqual(second["results"], first["results"])

    def test_unknown_traveler_is_needs_user_and_others_still_run(self) -> None:
        payload = json.loads(json.dumps(SAMPLE))
        payload["flights"][0]["travelerIds"] = ["missing"]
        self._install("booking.providers.hotels", _sandbox)

        result = handle_payload(payload, LocalBookingMemory())
        by_id = {item["segmentId"]: item for item in result["results"]}

        self.assertEqual(by_id["flight-1"]["status"], "needs_user")
        self.assertEqual(by_id["flight-1"]["error"], "unknown_traveler")
        self.assertIsNone(by_id["flight-1"]["confirmationCode"])
        self.assertEqual(by_id["hotel-1"]["status"], "booked")
        self.assertEqual(by_id["attraction-1"]["error"], "provider_not_installed")

    def test_invalid_plan_does_not_raise(self) -> None:
        result = handle_payload({"tripId": "bad", "flights": []}, LocalBookingMemory())
        self.assertEqual(result["tripId"], "bad")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["error"], "invalid_plan")
        self.assertEqual(handle_payload(["nope"], LocalBookingMemory())["error"], "invalid_plan")

    def test_nullable_return_date_and_attraction_time(self) -> None:
        payload = json.loads(json.dumps(SAMPLE))
        payload["flights"][0]["returnDate"] = None
        payload["attractions"][0]["time"] = None
        plan = TripPlan.model_validate(payload)
        dumped = plan.flights[0].model_dump(by_alias=True)
        self.assertIn("from", dumped)
        self.assertNotIn("origin", dumped)
        self.assertIsNone(plan.attractions[0].time)
        result = book_plan(plan, LocalBookingMemory())
        self.assertEqual(len(result["results"]), 3)

    def test_tools_are_the_three_booking_kinds(self) -> None:
        self.assertEqual([tool.kind for tool in TOOLS], ["flight", "hotel", "attraction"])
        self.assertEqual([tool.name for tool in TOOLS], ["book_flight", "book_hotel", "book_attraction"])

    def test_production_hostname_does_not_call_providers(self) -> None:
        called: list[str] = []

        def counting(segment: dict[str, Any], travelers: list[dict[str, Any]], trip_id: str) -> dict[str, Any]:
            called.append(segment["segmentId"])
            return _sandbox(segment, travelers, trip_id)

        for name in (
            "booking.providers.flights",
            "booking.providers.hotels",
            "booking.providers.attractions",
        ):
            self._install(name, counting)

        previous = os.environ.get("AMADEUS_HOSTNAME")
        os.environ["AMADEUS_HOSTNAME"] = "production"
        memory_env = {name: os.environ.pop(name, None) for name in ("AGENTCORE_MEMORY_ID", "MEMORY_BOOKINGMEMORY_ID")}
        try:
            from booking.orchestrator.main import invoke

            result = invoke(SAMPLE, context=None)
        finally:
            if previous is None:
                os.environ.pop("AMADEUS_HOSTNAME", None)
            else:
                os.environ["AMADEUS_HOSTNAME"] = previous
            for name, value in memory_env.items():
                if value is not None:
                    os.environ[name] = value

        self.assertEqual(called, [])
        self.assertTrue(result["results"])
        for item in result["results"]:
            self.assertEqual(item["status"], "failed")
            self.assertEqual(item["error"], "production_booking_refused")
            self.assertIsNone(item["confirmationCode"])


class MemoryTests(unittest.TestCase):
    def test_agentcore_session_round_trip(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.events: list[dict[str, Any]] = []

            def add_turns(self, messages: list[Any], metadata: dict[str, Any] | None = None, **_: Any) -> None:
                payload = []
                for message in messages:
                    self.assert_marker = message.text.startswith(STATE_MARKER)
                    payload.append(
                        {
                            "conversational": {
                                "content": {"text": message.text},
                                "role": message.role.value,
                            }
                        }
                    )
                self.events.append({"payload": payload, "metadata": metadata or {}})

            def list_events(self, **_: Any) -> list[dict[str, Any]]:
                return list(self.events)

        session = FakeSession()
        memory = AgentCoreBookingMemory(
            memory_id="memory-under-test",
            session_factory=lambda trip_id: session,
        )
        stored = [
            {
                "segmentId": "flight-1",
                "kind": "flight",
                "status": "booked",
                "confirmationCode": "SANDBOX-flight-1",
                "price": {"amount": "10.00", "currency": "USD"},
                "error": None,
            }
        ]
        memory.save("sample-kyoto", stored)
        self.assertEqual(memory.load("sample-kyoto"), stored)
        self.assertEqual(session.events[0]["metadata"]["recordType"], {"stringValue": "booking-state"})
        self.assertTrue(session.events[0]["payload"][0]["conversational"]["content"]["text"].startswith(STATE_MARKER))

    def test_remote_failure_falls_back_locally(self) -> None:
        def broken(trip_id: str) -> Any:
            del trip_id
            raise RuntimeError("no credentials")

        memory = AgentCoreBookingMemory(memory_id="memory-under-test", session_factory=broken)
        self.assertEqual(memory.load("sample-kyoto"), [])
        memory.save("sample-kyoto", [{"segmentId": "flight-1", "status": "booked"}])
        self.assertEqual(memory.load("sample-kyoto"), [{"segmentId": "flight-1", "status": "booked"}])

    def test_memory_from_env_without_id_skips_aws(self) -> None:
        previous = {name: os.environ.pop(name, None) for name in ("AGENTCORE_MEMORY_ID", "MEMORY_BOOKINGMEMORY_ID")}
        try:
            memory = memory_from_env()
        finally:
            for name, value in previous.items():
                if value is not None:
                    os.environ[name] = value
        self.assertIsInstance(memory, LocalBookingMemory)


class RuntimeTests(unittest.TestCase):
    def test_entrypoint_books_sample_without_credentials(self) -> None:
        previous = {name: os.environ.pop(name, None) for name in ("AGENTCORE_MEMORY_ID", "MEMORY_BOOKINGMEMORY_ID")}
        try:
            from booking.orchestrator.main import app, invoke

            self.assertIn("main", app.handlers)
            self.assertEqual(
                set(app.booking_tools),
                {"book_flight", "book_hotel", "book_attraction"},
            )
            result = invoke(SAMPLE, context=None)
        finally:
            for name, value in previous.items():
                if value is not None:
                    os.environ[name] = value
        self.assertEqual(result["tripId"], "sample-kyoto")
        self.assertTrue(all(item["error"] == "provider_not_installed" for item in result["results"]))

    def test_demo_prints_sample_results(self) -> None:
        from io import StringIO
        from unittest.mock import patch

        buffer = StringIO()
        with patch("sys.stdout", buffer):
            status = main()
        self.assertEqual(status, 0)
        printed = json.loads(buffer.getvalue())
        self.assertEqual(printed["tripId"], "sample-kyoto")
        self.assertEqual(len(printed["results"]), 3)


if __name__ == "__main__":
    unittest.main()
