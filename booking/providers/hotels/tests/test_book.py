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

from booking.providers.hotels import book  # noqa: E402

_HOTEL_ENV = (
    "HOTEL_BOOKING_PROVIDER",
    "HOTEL_BOOKING_API_BASE",
    "HOTEL_BOOKING_API_KEY",
    "HOTEL_SANDBOX_FAULT",
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

    def test_default_provider_does_not_call_the_network(self):
        def boom(*args, **kwargs):
            raise AssertionError("hotel network call")

        with patch("urllib.request.urlopen", boom), patch("booking.providers.hotels.live.post_json", boom):
            result = book(sample_segment(), TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "booked")
        self.assertTrue(result["confirmationCode"].startswith("SANDBOX-"))

    def test_live_adapter_refuses_production_without_a_request(self):
        os.environ["HOTEL_BOOKING_PROVIDER"] = "live"
        os.environ["HOTEL_BOOKING_API_BASE"] = "https://api.booking.com/v1"

        def boom(*args, **kwargs):
            raise AssertionError("production host was contacted")

        with patch("urllib.request.urlopen", boom), patch("booking.providers.hotels.live.post_json", boom):
            result = book(sample_segment(), TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertIn("production", result["error"])

    def test_card_details_do_not_book_or_charge(self):
        segment = sample_segment()
        segment["cardNumber"] = "4242424242424242"

        def boom(*args, **kwargs):
            raise AssertionError("card booking contacted a provider")

        with patch("urllib.request.urlopen", boom), patch("booking.providers.hotels.live.post_json", boom):
            result = book(segment, TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "needs_user")
        self.assertIsNone(result["confirmationCode"])
        self.assertIsNone(result["price"])
        self.assertIn("card", result["error"])

    def test_live_sandbox_payload_has_no_payment(self):
        os.environ["HOTEL_BOOKING_PROVIDER"] = "live"
        os.environ["HOTEL_BOOKING_API_BASE"] = "https://sandbox.hotels.test/v1"
        os.environ["HOTEL_BOOKING_API_KEY"] = "test-key"
        seen = {}

        def fake_post(url, payload, api_key, timeout=10.0):
            seen["url"] = url
            seen["payload"] = payload
            seen["api_key"] = api_key
            return {
                "status": "booked",
                "confirmationCode": "LIVE-1",
                "price": {"amount": "10.00", "currency": "USD"},
                "error": None,
            }

        with patch("booking.providers.hotels.live.post_json", fake_post):
            result = book(sample_segment(), TRAVELERS, TRIP_ID)

        self.assertEqual(result["status"], "booked")
        self.assertEqual(result["confirmationCode"], "LIVE-1")
        self.assertEqual(result["price"], {"amount": "10.00", "currency": "USD"})
        self.assertIn("sandbox.hotels.test", seen["url"])
        self.assertNotIn("card", str(seen["payload"]).lower())
        self.assertNotIn("charge", str(seen["payload"]).lower())
        self.assertEqual(seen["api_key"], "test-key")
        self.assertEqual(seen["payload"]["segment"]["kind"], "hotel")


if __name__ == "__main__":
    unittest.main()
