"""Flight confirmation email: a matching email verifies, a wrong code does not.

These tests stay in the sandbox. They do not open a socket or read an inbox.
"""

from __future__ import annotations

import socket
import unittest

from booking.verify.flights import AGENTCORE_TOOL, TOOL_SPEC, handler, sample_email, verify

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
CODE = "SANDBOX-FLIGHT-001"


class VerifyFlightEmailTests(unittest.TestCase):
    def test_matching_email_is_verified(self) -> None:
        with _network_forbidden():
            email = sample_email(SAMPLE_SEGMENT, CODE, TRAVELERS, TRIP_ID)
            result = verify(email, SAMPLE_SEGMENT, CODE, TRAVELERS)

        self.assertEqual(set(email), {"from", "to", "subject", "body", "receivedAt"})
        self.assertTrue(email["from"].endswith("@sandbox.swanavi.invalid>"))
        self.assertNotEqual(email["from"], "JFK")
        self.assertIn(CODE, email["body"])
        self.assertIn("JFK", email["body"])
        self.assertIn("KIX", email["body"])
        self.assertIn("2026-11-02", email["body"])
        self.assertIn("Ada Lovelace", email["body"])
        self.assertRegex(email["receivedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(
            result,
            {
                "segmentId": "seg-flight-1",
                "kind": "flight",
                "verified": True,
                "reason": "confirmation code, route, depart date, and traveler names are in the email",
            },
        )
        self.assertEqual(
            handler(
                {
                    "email": email,
                    "segment": SAMPLE_SEGMENT,
                    "confirmation_code": CODE,
                    "travelers": TRAVELERS,
                }
            ),
            result,
        )

    def test_mismatched_code_is_not_verified(self) -> None:
        with _network_forbidden():
            email = sample_email(SAMPLE_SEGMENT, CODE, TRAVELERS, TRIP_ID)
            wrong = verify(email, SAMPLE_SEGMENT, "SANDBOX-WRONG", TRAVELERS)
            prefix = verify(email, SAMPLE_SEGMENT, "SANDBOX-FLIGHT", TRAVELERS)

        self.assertEqual(wrong["segmentId"], "seg-flight-1")
        self.assertEqual(wrong["kind"], "flight")
        self.assertFalse(wrong["verified"])
        self.assertEqual(wrong["reason"], "confirmation code was not in the email")
        self.assertFalse(prefix["verified"])
        self.assertEqual(prefix["reason"], "confirmation code was not in the email")

    def test_missing_depart_date_is_not_verified(self) -> None:
        email = sample_email(SAMPLE_SEGMENT, CODE, TRAVELERS, TRIP_ID)
        stripped = {
            **email,
            "subject": email["subject"].replace("2026-11-02", ""),
            "body": email["body"].replace("2026-11-02", ""),
        }
        result = verify(stripped, SAMPLE_SEGMENT, CODE, TRAVELERS)
        self.assertFalse(result["verified"])
        self.assertEqual(result["kind"], "flight")
        self.assertEqual(result["reason"], "depart date was not in the email")

    def test_bad_email_does_not_raise(self) -> None:
        for bad in (None, "not-an-email", [], {}, {"subject": None, "body": 12}):
            result = verify(bad, SAMPLE_SEGMENT, CODE, TRAVELERS)
            self.assertEqual(result["segmentId"], "seg-flight-1")
            self.assertEqual(result["kind"], "flight")
            self.assertFalse(result["verified"])
            self.assertEqual(result["reason"], "email could not be read")
        self.assertFalse(handler("{")["verified"])
        self.assertFalse(handler(None)["verified"])

    def test_tool_spec_is_verify_flight_email(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "verify_flight_email")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["email", "segment", "confirmation_code", "travelers"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("book_flight", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "verify_flight_email")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("flight email verification opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
