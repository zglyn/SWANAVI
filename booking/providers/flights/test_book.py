"""Flight booking: a sample segment books, and a provider error fails closed.

These tests stay on the sandbox provider. They do not call the Amadeus client.
"""

from __future__ import annotations

import os
import socket
import sys
import unittest
from decimal import Decimal

from booking.providers.flights import AGENTCORE_TOOL, TOOL_SPEC, book, handler
from booking.providers.flights.sandbox import FORCE_ERROR_ENV

SAMPLE_SEGMENT = {
    "segmentId": "seg-flight-1",
    "kind": "flight",
    "from": "JFK",
    "to": "KIX",
    "departDate": "2026-11-02",
    "returnDate": "2026-11-09",
    "cabin": "economy",
    "travelerIds": ["t1"],
}
TRAVELERS = [{"id": "t1", "givenName": "Ada", "familyName": "Lovelace"}]
TRIP_ID = "trip-kyoto-001"
_ENV_KEYS = (
    "ROAM_FLIGHT_PROVIDER",
    FORCE_ERROR_ENV,
    "AMADEUS_CLIENT_ID",
    "AMADEUS_CLIENT_SECRET",
    "AMADEUS_HOSTNAME",
)


class BookFlightTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        sys.modules.pop("booking.providers.flights.live", None)

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_sample_flight_segment_books(self) -> None:
        with _network_forbidden():
            result = book(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)
            again = book(dict(SAMPLE_SEGMENT), list(TRAVELERS), TRIP_ID)

        self.assertEqual(
            set(result),
            {"segmentId", "kind", "status", "confirmationCode", "price", "error"},
        )
        self.assertEqual(result, again)
        self.assertEqual(result["segmentId"], "seg-flight-1")
        self.assertEqual(result["kind"], "flight")
        self.assertEqual(result["status"], "booked")
        self.assertTrue(result["confirmationCode"].startswith("SANDBOX-"))
        self.assertIsNone(result["error"])
        self.assertEqual(result["price"]["currency"], "USD")
        self.assertGreater(Decimal(result["price"]["amount"]), 0)
        self.assertNotIn("booking.providers.flights.live", sys.modules)

    def test_one_way_books_and_costs_less_than_round_trip(self) -> None:
        with _network_forbidden():
            one_way = book(dict(SAMPLE_SEGMENT, returnDate=None), TRAVELERS, TRIP_ID)
            round_trip = book(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)
        self.assertEqual(one_way["status"], "booked")
        self.assertTrue(one_way["confirmationCode"].startswith("SANDBOX-"))
        self.assertLess(Decimal(one_way["price"]["amount"]), Decimal(round_trip["price"]["amount"]))

    def test_forced_provider_error_returns_failed_without_raising(self) -> None:
        os.environ[FORCE_ERROR_ENV] = "1"
        with _network_forbidden():
            result = book(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["segmentId"], "seg-flight-1")
        self.assertEqual(result["kind"], "flight")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertEqual(result["error"], "sandbox flight provider forced error")

    def test_missing_traveler_needs_user(self) -> None:
        result = book(SAMPLE_SEGMENT, [], TRIP_ID)
        self.assertEqual(result["status"], "needs_user")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertIn("t1", result["error"])

    def test_tool_spec_is_book_flight(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "book_flight")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["segment", "travelers", "trip_id"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "book_flight")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_book(self) -> None:
        payload = {"segment": SAMPLE_SEGMENT, "travelers": TRAVELERS, "trip_id": TRIP_ID}
        with _network_forbidden():
            self.assertEqual(handler(payload), book(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID))
        self.assertNotIn("booking.providers.flights.live", sys.modules)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("flight booking opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
