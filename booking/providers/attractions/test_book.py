"""Attraction booking: a sample segment books, and a provider error fails closed.

These tests stay on the sandbox. They do not call the Amadeus client and do not need keys.
"""

from __future__ import annotations

import json
import os
import socket
import unittest
from decimal import Decimal

from booking.providers.attractions import BOOK_ATTRACTION_TOOL, book, book_attraction
from booking.providers.attractions.sandbox import FORCE_ERROR_ENV

SAMPLE_SEGMENT = {
    "segmentId": "seg-fushimi-1",
    "kind": "attraction",
    "name": "Fushimi Inari Taisha",
    "city": "Kyoto",
    "date": "2026-11-02",
    "partySize": 2,
    "time": "09:00",
}
TRAVELERS = [{"name": "Mina Park"}, {"name": "Luis Ortega"}]
TRIP_ID = "trip-kyoto-2026"
_ENV_KEYS = (
    "ROAM_ATTRACTION_PROVIDER",
    "ROAM_ATTRACTION_SANDBOX_URL",
    "AMADEUS_CLIENT_ID",
    "AMADEUS_CLIENT_SECRET",
    "AMADEUS_HOSTNAME",
    FORCE_ERROR_ENV,
)


class BookAttractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_sample_attraction_segment_books(self) -> None:
        result = book(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)

        self.assertEqual(
            set(result),
            {"segmentId", "kind", "status", "confirmationCode", "price", "error"},
        )
        self.assertEqual(result["segmentId"], "seg-fushimi-1")
        self.assertEqual(result["kind"], "attraction")
        self.assertEqual(result["status"], "booked")
        self.assertTrue(result["confirmationCode"].startswith("SANDBOX-"))
        self.assertIsNone(result["error"])
        self.assertEqual(result["price"]["currency"], "USD")
        self.assertEqual(Decimal(result["price"]["amount"]) % 1, 0)
        self.assertGreater(Decimal(result["price"]["amount"]), 0)

        again = book(dict(SAMPLE_SEGMENT), list(TRAVELERS), TRIP_ID)
        self.assertEqual(again, result)

        solo = dict(SAMPLE_SEGMENT, partySize=1)
        solo_result = book(solo, TRAVELERS[:1], TRIP_ID)
        self.assertEqual(
            Decimal(result["price"]["amount"]),
            Decimal(solo_result["price"]["amount"]) * 2,
        )
        self.assertNotEqual(solo_result["confirmationCode"], result["confirmationCode"])

    def test_null_time_books(self) -> None:
        segment = dict(SAMPLE_SEGMENT, time=None)
        result = book(segment, TRAVELERS, TRIP_ID)
        self.assertEqual(result["status"], "booked")
        self.assertTrue(result["confirmationCode"].startswith("SANDBOX-"))

    def test_forced_provider_error_returns_failed_without_raising(self) -> None:
        os.environ[FORCE_ERROR_ENV] = "1"

        result = book(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["segmentId"], "seg-fushimi-1")
        self.assertEqual(result["kind"], "attraction")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertEqual(result["error"], "sandbox attraction provider forced error")

    def test_missing_fields_need_user(self) -> None:
        result = book({"kind": "attraction"}, TRAVELERS, TRIP_ID)
        self.assertEqual(result["status"], "needs_user")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertIn("segmentId", result["error"])

    def test_agentcore_tool_handler_calls_book(self) -> None:
        json.dumps(BOOK_ATTRACTION_TOOL)
        self.assertEqual(BOOK_ATTRACTION_TOOL["name"], "book_attraction")
        self.assertEqual(
            BOOK_ATTRACTION_TOOL["inputSchema"]["required"],
            ["segment", "travelers", "trip_id"],
        )
        self.assertIn("AgentCore runtime", BOOK_ATTRACTION_TOOL["description"])

        direct = book(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)
        via_tool = book_attraction(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)
        self.assertEqual(via_tool, direct)
        self.assertEqual(via_tool["status"], "booked")
        self.assertTrue(via_tool["confirmationCode"].startswith("SANDBOX-"))

    def test_live_client_is_not_used_by_default(self) -> None:
        os.environ["AMADEUS_CLIENT_ID"] = "test-client"
        os.environ["AMADEUS_CLIENT_SECRET"] = "test-secret"
        os.environ["AMADEUS_HOSTNAME"] = "production"
        with _network_forbidden():
            result = book_attraction(SAMPLE_SEGMENT, TRAVELERS, TRIP_ID)
        self.assertEqual(result["status"], "booked")
        self.assertTrue(result["confirmationCode"].startswith("SANDBOX-"))


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*args, **kwargs):
            raise AssertionError("attraction booking opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
