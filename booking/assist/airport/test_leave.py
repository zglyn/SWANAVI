"""Airport departure: 3 hours international, 2 hours domestic, late checkout is not ok.

These tests stay in-process. They do not call an airline, AWS, or open a socket.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.airport import AGENTCORE_TOOL, TOOL_SPEC, airport_leave, handler
from booking.assist.airport import leave as leave_mod
from booking.assist.airport.leave import REASON_MISSING_DEPART, REASON_STILL_AT_HOTEL
from booking.assist.airport import tool as tool_mod

SEGMENT = "flight-1"
DEPART = "2026-11-06T14:00:00Z"
INTERNATIONAL_LEAVE = "2026-11-06T11:00:00Z"
DOMESTIC_LEAVE = "2026-11-06T12:00:00Z"


def _leave(**overrides):
    payload = {
        "flightSegmentId": SEGMENT,
        "departAt": DEPART,
        "international": False,
        "hotelCheckoutAt": None,
    }
    payload.update(overrides)
    return airport_leave(payload)


class AirportLeaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_international_buffer_is_three_hours(self) -> None:
        result = _leave(international=True)

        self.assertEqual(result["flightSegmentId"], SEGMENT)
        self.assertEqual(result["leaveBy"], INTERNATIONAL_LEAVE)
        self.assertTrue(result["ok"])
        self.assertIn("3 hours", result["reason"])

        again = airport_leave(SEGMENT, DEPART, True, None)
        self.assertEqual(again, result)

    def test_domestic_buffer_is_two_hours(self) -> None:
        result = _leave(international=False)

        self.assertEqual(result["leaveBy"], DOMESTIC_LEAVE)
        self.assertTrue(result["ok"])
        self.assertIn("2 hours", result["reason"])

    def test_checkout_after_leave_by_is_not_ok(self) -> None:
        domestic = _leave(hotelCheckoutAt="2026-11-06T12:30:00Z")
        self.assertEqual(domestic["leaveBy"], DOMESTIC_LEAVE)
        self.assertFalse(domestic["ok"])
        self.assertEqual(domestic["reason"], REASON_STILL_AT_HOTEL)

        international = _leave(international=True, hotelCheckoutAt="2026-11-06T11:01:00Z")
        self.assertEqual(international["leaveBy"], INTERNATIONAL_LEAVE)
        self.assertFalse(international["ok"])
        self.assertEqual(international["reason"], REASON_STILL_AT_HOTEL)

    def test_checkout_at_or_before_leave_by_is_ok(self) -> None:
        exact = _leave(hotelCheckoutAt=DOMESTIC_LEAVE)
        earlier = _leave(international=True, hotelCheckoutAt="2026-11-06T10:00:00Z")

        self.assertTrue(exact["ok"])
        self.assertEqual(exact["leaveBy"], DOMESTIC_LEAVE)
        self.assertTrue(earlier["ok"])
        self.assertEqual(earlier["leaveBy"], INTERNATIONAL_LEAVE)

    def test_missing_depart_at_is_not_ok(self) -> None:
        for depart_at in (None, "", "   "):
            result = _leave(departAt=depart_at)
            self.assertFalse(result["ok"])
            self.assertEqual(result["leaveBy"], "")
            self.assertEqual(result["reason"], REASON_MISSING_DEPART)
            self.assertEqual(result["flightSegmentId"], SEGMENT)

    def test_partial_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"flightSegmentId": SEGMENT},
            {"departAt": "not-a-time", "international": False},
            {"departAt": DEPART, "international": "maybe"},
            {"departAt": DEPART, "international": True, "hotelCheckoutAt": "tomorrow"},
            {"departAt": "2026-11-06T16:00:00+02:00", "international": True, "hotelCheckoutAt": None},
        ]
        for case in cases:
            result = airport_leave(case)
            self.assertEqual(set(result), {"flightSegmentId", "leaveBy", "ok", "reason"})
            self.assertIsInstance(result["flightSegmentId"], str)
            self.assertIsInstance(result["leaveBy"], str)
            self.assertIsInstance(result["ok"], bool)
            self.assertIsInstance(result["reason"], str)

        shifted = airport_leave(
            {
                "departAt": "2026-11-06T16:00:00+02:00",
                "international": True,
                "hotelCheckoutAt": "2026-11-06T13:00:00+02:00",
            }
        )
        self.assertEqual(shifted["leaveBy"], INTERNATIONAL_LEAVE)
        self.assertTrue(shifted["ok"])

    def test_tool_spec_is_airport_leave(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "airport_leave")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["flightSegmentId", "departAt", "international"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["flightSegmentId", "leaveBy", "ok", "reason"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("morning of a flight", TOOL_SPEC["description"])
        self.assertIn("no airline API", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "airport_leave")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_airport_leave(self) -> None:
        payload = {
            "flightSegmentId": SEGMENT,
            "departAt": DEPART,
            "international": True,
            "hotelCheckoutAt": None,
        }
        self.assertEqual(handler(payload), airport_leave(payload))
        self.assertEqual(handler(json.dumps(payload)), airport_leave(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___airport_leave"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), airport_leave(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___book_flight"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertFalse(ignored["ok"])
        self.assertEqual(ignored["leaveBy"], "")
        self.assertIn("airport_leave", ignored["reason"])

    def test_sandbox_sources_do_not_touch_network_or_aws(self) -> None:
        for module in (leave_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("amadeus", source)
            self.assertNotIn("datetime.now", source)
            self.assertNotIn(".utcnow", source)
            self.assertNotIn("time.time", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("airport_leave opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
