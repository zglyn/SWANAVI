"""Hotel booker tests. Run from the repo root:

python3 -m unittest discover -s booking/providers/hotels/tests -v
"""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from booking.providers.hotels import TOOL_SPEC, book, handler  # noqa: E402

_HOTEL_ENV = (
    "ROAM_HOTEL_PROVIDER",
    "AMADEUS_CLIENT_ID",
    "AMADEUS_CLIENT_SECRET",
    "AMADEUS_HOSTNAME",
    "HOTEL_SANDBOX_FAULT",
    "HOTEL_BOOKING_PROVIDER",
    "HOTEL_BOOKING_API_BASE",
    "HOTEL_BOOKING_API_KEY",
)

TRIP_ID = "trip-kyoto-001"
TRAVELERS = [
    {"name": "Ada Lovelace"},
    {"name": "Alan Turing"},
]


def sample_segment() -> dict:
    return {
        "segmentId": "seg-hotel-1",
        "kind": "hotel",
        "city": "Kyoto",
        "checkIn": "2026-11-02",
        "checkOut": "2026-11-05",
        "rooms": 1,
        "guests": 2,
    }


def expected_confirmation() -> str:
    payload = "trip-kyoto-001|seg-hotel-1|kyoto|2026-11-02|2026-11-05|1|2|ada lovelace,alan turing"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12].upper()
    return f"SANDBOX-{digest}"


class HotelBookTests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _HOTEL_ENV}
        for key in _HOTEL_ENV:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_sample_hotel_segment_books(self):
        first = book(sample_segment(), TRAVELERS, TRIP_ID)
        second = book(sample_segment(), TRAVELERS, TRIP_ID)

        self.assertEqual(first, second)
        self.assertEqual(first["segmentId"], "seg-hotel-1")
        self.assertEqual(first["kind"], "hotel")
        self.assertEqual(first["status"], "booked")
        self.assertTrue(first["confirmationCode"].startswith("SANDBOX-"))
        self.assertEqual(first["confirmationCode"], expected_confirmation())
        self.assertEqual(first["price"], {"amount": "660.00", "currency": "USD"})
        self.assertIsNone(first["error"])

    def test_forced_provider_error_returns_failed(self):
        segment = sample_segment()
        segment["sandboxFault"] = "error"

        result = book(segment, TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["kind"], "hotel")
        self.assertEqual(result["segmentId"], "seg-hotel-1")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertEqual(result["error"], "sandbox hotel provider failed")

    def test_incomplete_segment_needs_user(self):
        segment = sample_segment()
        del segment["checkIn"]

        result = book(segment, TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "needs_user")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertIn("checkIn", result["error"])

    def test_checkout_before_checkin_needs_user(self):
        segment = sample_segment()
        segment["checkIn"] = "2026-11-05"
        segment["checkOut"] = "2026-11-02"

        result = book(segment, TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "needs_user")
        self.assertIsNone(result["confirmationCode"])
        self.assertIn("checkOut must be after checkIn", result["error"])

    def test_agentcore_tool_handler_calls_book(self):
        self.assertEqual(TOOL_SPEC["name"], "book_hotel")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["segment", "travelers", "trip_id"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])

        event = {"segment": sample_segment(), "travelers": TRAVELERS, "trip_id": TRIP_ID}
        context = _agentcore_context("hotels___book_hotel")

        self.assertEqual(handler(event, context), book(sample_segment(), TRAVELERS, TRIP_ID))
        self.assertTrue(handler(event)["confirmationCode"].startswith("SANDBOX-"))

        rejected = handler(event, _agentcore_context("hotels___book_flight"))
        self.assertEqual(rejected["status"], "failed")
        self.assertIsNone(rejected["confirmationCode"])

    def test_default_provider_does_not_call_the_network(self):
        def boom(*args, **kwargs):
            raise AssertionError("hotel network call")

        with patch("urllib.request.urlopen", boom):
            result = handler(
                {"segment": sample_segment(), "travelers": TRAVELERS, "trip_id": TRIP_ID}
            )

        self.assertEqual(result["status"], "booked")
        self.assertTrue(result["confirmationCode"].startswith("SANDBOX-"))

    def test_live_mode_without_amadeus_config_does_not_call_the_network(self):
        os.environ["ROAM_HOTEL_PROVIDER"] = "live"

        def boom(*args, **kwargs):
            raise AssertionError("Amadeus was called")

        with patch("urllib.request.urlopen", boom):
            result = book(sample_segment(), TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertIn("AMADEUS_HOSTNAME=test", result["error"])

    def test_production_hostname_does_not_call_amadeus(self):
        os.environ["ROAM_HOTEL_PROVIDER"] = "live"
        os.environ["AMADEUS_HOSTNAME"] = "production"
        os.environ["AMADEUS_CLIENT_ID"] = "id"
        os.environ["AMADEUS_CLIENT_SECRET"] = "secret"

        def boom(*args, **kwargs):
            raise AssertionError("production Amadeus was called")

        with patch("urllib.request.urlopen", boom):
            result = book(sample_segment(), TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "failed")
        self.assertIn("production", result["error"])
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])

    def test_card_details_do_not_book_or_charge(self):
        segment = sample_segment()
        segment["cardNumber"] = "4242424242424242"

        def boom(*args, **kwargs):
            raise AssertionError("card booking contacted a provider")

        with patch("urllib.request.urlopen", boom):
            result = book(segment, TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "needs_user")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertIn("card", result["error"])


class _AgentCoreContext:
    def __init__(self, tool_name: str):
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


def _agentcore_context(tool_name: str) -> _AgentCoreContext:
    return _AgentCoreContext(tool_name)


if __name__ == "__main__":
    unittest.main()
