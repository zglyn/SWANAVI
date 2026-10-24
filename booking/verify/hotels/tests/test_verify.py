"""Hotel confirmation-email tests. Run from the repo root:

python3 -m unittest discover -s booking/verify/hotels/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from booking.verify.hotels import TOOL_SPEC, handler, sample_email, verify  # noqa: E402
from booking.verify.hotels.email import SANDBOX_FROM, SANDBOX_RECEIVED_AT  # noqa: E402

TRIP_ID = "trip-kyoto-001"
CODE = "SANDBOX-KYOTO123456"
TRAVELERS = [
    {"name": "Ada Lovelace", "email": "ada@example.com"},
    "Alan Turing",
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


class _AgentCoreContext:
    def __init__(self, tool_name: str):
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class HotelEmailTests(unittest.TestCase):
    def test_matching_email_verifies(self):
        segment = sample_segment()
        email = sample_email(segment, CODE, TRAVELERS, TRIP_ID)

        self.assertEqual(email["from"], SANDBOX_FROM)
        self.assertEqual(email["to"], "ada@example.com")
        self.assertEqual(email["receivedAt"], SANDBOX_RECEIVED_AT)
        for field in (CODE, "Kyoto", "2026-11-02", "2026-11-05", "Ada Lovelace", "Alan Turing"):
            self.assertIn(field, email["body"])

        result = verify(email, segment, CODE, TRAVELERS)

        self.assertEqual(result["segmentId"], "seg-hotel-1")
        self.assertEqual(result["kind"], "hotel")
        self.assertTrue(result["verified"])
        self.assertIn("confirmation code", result["reason"])

    def test_mismatched_code_is_not_verified(self):
        segment = sample_segment()
        email = sample_email(segment, CODE, TRAVELERS, TRIP_ID)

        result = verify(email, segment, "SANDBOX-OTHER999999", TRAVELERS)

        self.assertEqual(result["segmentId"], "seg-hotel-1")
        self.assertEqual(result["kind"], "hotel")
        self.assertFalse(result["verified"])
        self.assertIn("confirmation code", result["reason"])

    def test_wrong_dates_are_not_verified(self):
        segment = sample_segment()
        email = sample_email(segment, CODE, TRAVELERS, TRIP_ID)
        moved = dict(segment)
        moved["checkIn"] = "2027-01-10"
        moved["checkOut"] = "2027-01-12"

        result = verify(email, moved, CODE, TRAVELERS)

        self.assertFalse(result["verified"])
        self.assertIn("check-in", result["reason"])
        self.assertIn("check-out", result["reason"])

    def test_missing_guest_name_is_not_verified(self):
        segment = sample_segment()
        email = sample_email(segment, CODE, TRAVELERS, TRIP_ID)
        body = email["body"].replace("Alan Turing", "someone else")

        result = verify({**email, "body": body}, segment, CODE, TRAVELERS)

        self.assertFalse(result["verified"])
        self.assertIn("Alan Turing", result["reason"])

    def test_code_in_the_subject_counts(self):
        segment = sample_segment()
        email = sample_email(segment, CODE, TRAVELERS, TRIP_ID)
        email = {
            **email,
            "subject": f"Confirmation {CODE}",
            "body": email["body"].replace(CODE, ""),
        }

        self.assertNotIn(CODE, email["body"])
        self.assertTrue(verify(email, segment, CODE, TRAVELERS)["verified"])

    def test_bad_email_does_not_raise(self):
        segment = sample_segment()
        cases = (
            None,
            "not-an-email",
            [],
            {},
            {"subject": 12, "body": None},
            {"subject": "Hotel", "body": "no stay details"},
        )
        for email in cases:
            result = verify(email, segment, CODE, TRAVELERS)
            self.assertFalse(result["verified"])
            self.assertEqual(result["kind"], "hotel")
            self.assertIsInstance(result["reason"], str)
            self.assertTrue(result["reason"])

    def test_agentcore_tool_verifies_matching_email(self):
        self.assertEqual(TOOL_SPEC["name"], "verify_hotel_email")
        self.assertIn("book_hotel", TOOL_SPEC["description"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])

        segment = sample_segment()
        email = sample_email(segment, CODE, TRAVELERS, TRIP_ID)
        event = {
            "email": email,
            "segment": segment,
            "confirmationCode": CODE,
            "travelers": TRAVELERS,
        }

        self.assertEqual(
            handler(event, _AgentCoreContext("hotels___verify_hotel_email")),
            verify(email, segment, CODE, TRAVELERS),
        )
        sampled = handler(
            {
                "operation": "sample_email",
                "segment": segment,
                "travelers": TRAVELERS,
                "confirmation_code": CODE,
                "trip_id": TRIP_ID,
            }
        )
        self.assertEqual(sampled, email)

        rejected = handler(event, _AgentCoreContext("hotels___book_flight"))
        self.assertFalse(rejected["verified"])
        self.assertEqual(rejected["kind"], "hotel")

        bad = handler("{", _AgentCoreContext("verify_hotel_email"))
        self.assertFalse(bad["verified"])

    def test_sandbox_does_not_call_the_network(self):
        def boom(*args, **kwargs):
            raise AssertionError("hotel email verification contacted the network")

        segment = sample_segment()
        with patch("urllib.request.urlopen", boom), patch("socket.socket", boom):
            email = sample_email(segment, CODE, TRAVELERS, TRIP_ID)
            result = handler(
                {
                    "email": email,
                    "segment": segment,
                    "confirmation_code": CODE,
                    "travelers": TRAVELERS,
                }
            )

        self.assertTrue(result["verified"])


if __name__ == "__main__":
    unittest.main()
