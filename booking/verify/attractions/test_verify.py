"""Attraction confirmation emails: a matching message verifies, a wrong code does not.

These tests stay in the sandbox. They do not open a socket, an inbox, or AWS.
"""

from __future__ import annotations

import json
import socket
import unittest

from booking.verify.attractions import (
    VERIFY_ATTRACTION_EMAIL_TOOL,
    sample_email,
    verify,
    verify_attraction_email,
)

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
CODE = "SANDBOX-RIGHT"


class VerifyAttractionEmailTests(unittest.TestCase):
    def test_matching_email_verifies(self) -> None:
        email = sample_email(SAMPLE_SEGMENT, CODE, TRAVELERS, TRIP_ID)

        self.assertEqual(
            set(email),
            {"from", "to", "subject", "body", "receivedAt"},
        )
        self.assertEqual(email["from"], "tickets@sandbox.roam402.invalid")
        self.assertIn("Mina Park", email["to"])
        self.assertIn("Luis Ortega", email["to"])
        self.assertEqual(email["receivedAt"], "2026-11-02T18:00:00Z")
        for fact in (CODE, "Fushimi Inari Taisha", "Kyoto", "2026-11-02", "Party size: 2"):
            self.assertIn(fact, email["body"])

        result = verify(email, SAMPLE_SEGMENT, CODE, TRAVELERS)

        self.assertEqual(
            result,
            {
                "segmentId": "seg-fushimi-1",
                "kind": "attraction",
                "verified": True,
                "reason": "confirmation code, attraction name, date, and party size match",
            },
        )

    def test_mismatched_code_is_not_verified(self) -> None:
        email = sample_email(SAMPLE_SEGMENT, CODE, TRAVELERS, TRIP_ID)

        result = verify(email, SAMPLE_SEGMENT, "SANDBOX-WRONG", TRAVELERS)

        self.assertEqual(result["segmentId"], "seg-fushimi-1")
        self.assertEqual(result["kind"], "attraction")
        self.assertFalse(result["verified"])
        self.assertIn("confirmation code", result["reason"])

    def test_wrong_date_is_not_verified(self) -> None:
        email = sample_email(SAMPLE_SEGMENT, CODE, TRAVELERS, TRIP_ID)
        shifted = dict(email)
        shifted["subject"] = email["subject"].replace("2026-11-02", "2026-12-01")
        shifted["body"] = email["body"].replace("2026-11-02", "2026-12-01")

        result = verify(shifted, SAMPLE_SEGMENT, CODE, TRAVELERS)

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "missing date")
        self.assertEqual(result["kind"], "attraction")

    def test_party_size_inside_the_date_does_not_count(self) -> None:
        email = sample_email(SAMPLE_SEGMENT, CODE, TRAVELERS, TRIP_ID)
        stripped = dict(email)
        stripped["body"] = email["body"].replace("Party size: 2", "Party size:")
        stripped["subject"] = "Attraction tickets confirmed"

        result = verify(stripped, SAMPLE_SEGMENT, CODE, TRAVELERS)

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "missing party size")

    def test_bad_email_does_not_raise(self) -> None:
        for email in (None, "not-an-email", [], {}, {"subject": 3, "body": None}):
            result = verify(email, SAMPLE_SEGMENT, CODE, TRAVELERS)
            self.assertFalse(result["verified"])
            self.assertEqual(result["kind"], "attraction")
            self.assertEqual(result["segmentId"], "seg-fushimi-1")
            self.assertTrue(result["reason"])

        result = verify(None, None, None, None)
        self.assertEqual(
            result,
            {
                "segmentId": "",
                "kind": "attraction",
                "verified": False,
                "reason": "confirmation email is missing",
            },
        )

    def test_agentcore_tool_runs_both_actions(self) -> None:
        json.dumps(VERIFY_ATTRACTION_EMAIL_TOOL)
        self.assertEqual(VERIFY_ATTRACTION_EMAIL_TOOL["name"], "verify_attraction_email")
        self.assertEqual(
            VERIFY_ATTRACTION_EMAIL_TOOL["inputSchema"]["properties"]["action"]["enum"],
            ["sample_email", "verify"],
        )
        self.assertIn("after book_attraction", VERIFY_ATTRACTION_EMAIL_TOOL["description"])
        self.assertIn("AgentCore runtime", VERIFY_ATTRACTION_EMAIL_TOOL["description"])

        with _network_forbidden():
            email = verify_attraction_email(
                {
                    "action": "sample_email",
                    "segment": SAMPLE_SEGMENT,
                    "confirmation_code": CODE,
                    "travelers": TRAVELERS,
                    "trip_id": TRIP_ID,
                }
            )
            matched = verify_attraction_email(
                json.dumps(
                    {
                        "action": "verify",
                        "email": email,
                        "segment": SAMPLE_SEGMENT,
                        "confirmation_code": CODE,
                        "travelers": TRAVELERS,
                    }
                )
            )
            mismatched = verify_attraction_email(
                action="verify",
                email=email,
                segment=SAMPLE_SEGMENT,
                confirmation_code="SANDBOX-WRONG",
                travelers=TRAVELERS,
            )
            broken = verify_attraction_email("[")

        self.assertIn(CODE, email["body"])
        self.assertTrue(matched["verified"])
        self.assertFalse(mismatched["verified"])
        self.assertEqual(broken["verified"], False)
        self.assertEqual(broken["kind"], "attraction")


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*args, **kwargs):
            raise AssertionError("attraction email verification opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
