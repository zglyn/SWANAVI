"""Ride requests: a complete request is sandbox-coded, a missing dropoff fails.

These tests stay on the sandbox. They do not call the Uber Rides API client
and do not hit production.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import unittest

from booking.assist.ride import AGENTCORE_TOOL, TOOL_SPEC, handler, request_ride
from booking.assist.ride.ride import REASON_NO_DROPOFF, REASON_NO_PICKUP_AT

PICKUP_AT = "2026-11-03T11:00:00+09:00"
DROPOFF = "Nishiki Market"
PICKUP = "Fushimi Inari Taisha"
_ENV_KEYS = ("ROAM_RIDE_PROVIDER", "UBER_ACCESS_TOKEN")


def _ride(**overrides):
    payload = {
        "fromSegmentId": "attraction-1",
        "toSegmentId": "dinner-1",
        "pickupAt": PICKUP_AT,
        "pickupName": PICKUP,
        "dropoffName": DROPOFF,
        "partySize": 2,
    }
    payload.update(overrides)
    return request_ride(payload)


class RequestRideTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_complete_request_returns_sandbox_ride_code(self) -> None:
        result = _ride()

        self.assertEqual(
            set(result),
            {"status", "rideCode", "pickupAt", "dropoffName", "partySize", "reason"},
        )
        self.assertEqual(result["status"], "requested")
        self.assertIsInstance(result["rideCode"], str)
        self.assertTrue(result["rideCode"].startswith("SANDBOX-RIDE-"))
        self.assertEqual(result["pickupAt"], PICKUP_AT)
        self.assertEqual(result["dropoffName"], DROPOFF)
        self.assertEqual(result["partySize"], 2)
        self.assertIsNone(result["reason"])

        again = request_ride("attraction-1", "dinner-1", PICKUP_AT, PICKUP, DROPOFF, 2)
        self.assertEqual(again, result)
        self.assertNotIn("booking.assist.ride.live", sys.modules)

    def test_missing_dropoff_fails_without_raising(self) -> None:
        cases = [
            {"dropoffName": None},
            {"dropoffName": ""},
            {"dropoffName": "   "},
            {"dropoffName": 12},
        ]
        for overrides in cases:
            payload = {
                "fromSegmentId": "attraction-1",
                "toSegmentId": "dinner-1",
                "pickupAt": PICKUP_AT,
                "pickupName": PICKUP,
                "dropoffName": DROPOFF,
                "partySize": 2,
            }
            payload.update(overrides)
            if overrides["dropoffName"] is None:
                del payload["dropoffName"]
            result = request_ride(payload)
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["rideCode"])
            self.assertEqual(result["reason"], REASON_NO_DROPOFF)
            self.assertEqual(result["pickupAt"], PICKUP_AT)
            self.assertIsNone(result["dropoffName"])
            self.assertEqual(result["partySize"], 2)

    def test_missing_pickup_at_fails_without_raising(self) -> None:
        result = _ride(pickupAt=None)

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["rideCode"])
        self.assertIsNone(result["pickupAt"])
        self.assertEqual(result["dropoffName"], DROPOFF)
        self.assertEqual(result["reason"], REASON_NO_PICKUP_AT)

    def test_live_adapter_stays_off_without_both_env_vars(self) -> None:
        os.environ["UBER_ACCESS_TOKEN"] = "should-not-be-sent"
        token_only = _ride()
        self.assertEqual(token_only["status"], "requested")
        self.assertTrue(token_only["rideCode"].startswith("SANDBOX-RIDE-"))

        os.environ.pop("UBER_ACCESS_TOKEN", None)
        os.environ["ROAM_RIDE_PROVIDER"] = "live"
        provider_only = _ride()
        self.assertEqual(provider_only["status"], "requested")
        self.assertTrue(provider_only["rideCode"].startswith("SANDBOX-RIDE-"))
        self.assertNotIn("booking.assist.ride.live", sys.modules)

    def test_tool_spec_is_request_ride(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "request_ride")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["fromSegmentId", "toSegmentId", "pickupAt", "pickupName", "dropoffName", "partySize"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["properties"]["status"]["enum"], ["requested", "failed"])
        self.assertIn("Bedrock AgentCore", TOOL_SPEC["description"])
        self.assertIn("Uber Rides API", TOOL_SPEC["description"])
        self.assertIn("ROAM_RIDE_PROVIDER=live", TOOL_SPEC["description"])
        self.assertIn("UBER_ACCESS_TOKEN", TOOL_SPEC["description"])
        self.assertIn("SANDBOX-RIDE-", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "request_ride")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_request_ride(self) -> None:
        payload = {
            "fromSegmentId": "attraction-1",
            "toSegmentId": "dinner-1",
            "pickupAt": PICKUP_AT,
            "pickupName": PICKUP,
            "dropoffName": DROPOFF,
            "partySize": 2,
        }
        self.assertEqual(handler(payload), request_ride(payload))
        self.assertEqual(handler(json.dumps(payload)), request_ride(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___request_ride"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), request_ride(payload))
        self.assertTrue(handler(payload)["rideCode"].startswith("SANDBOX-RIDE-"))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___book_hotel"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored["status"], "failed")
        self.assertIsNone(ignored["rideCode"])


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("request_ride opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
