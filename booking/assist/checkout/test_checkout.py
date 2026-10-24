"""Late checkout: a flight 5 hours after checkout requests 2 extra hours.

A flight 1 hour after checkout is not needed. These tests stay in-process.
They do not call AWS or open a socket.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from booking.assist.checkout import AGENTCORE_TOOL, TOOL_SPEC, handler, late_checkout
from booking.assist.checkout import checkout as checkout_mod
from booking.assist.checkout.checkout import REASON_BAD_TIMES, REASON_MISSING_TIMES, REASON_UNREADABLE
from booking.assist.checkout import tool as tool_mod

SEGMENT = "hotel-kyoto"
TRAVELER = "Mina Cho"
CHECKOUT = "2026-11-06T10:00:00Z"
DEPART_5H = "2026-11-06T15:00:00Z"
DEPART_1H = "2026-11-06T11:00:00Z"
UNTIL_2H = "2026-11-06T12:00:00Z"


def _call(**overrides):
    payload = {
        "hotelSegmentId": SEGMENT,
        "checkoutAt": CHECKOUT,
        "departAt": DEPART_5H,
        "travelerName": TRAVELER,
    }
    payload.update(overrides)
    return late_checkout(payload)


def _instant(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(text)


class LateCheckoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_flight_5h_after_checkout_requests_2_extra_hours(self) -> None:
        result = _call()

        self.assertEqual(result["hotelSegmentId"], SEGMENT)
        self.assertEqual(result["status"], "requested")
        self.assertEqual(result["until"], UNTIL_2H)
        self.assertEqual(_instant(result["until"]) - _instant(CHECKOUT), timedelta(hours=2))
        self.assertNotEqual(_instant(result["until"]), _instant(DEPART_5H))
        self.assertIn(TRAVELER, result["reason"])
        self.assertIn("2 extra hours", result["reason"])
        self.assertEqual(set(result), {"hotelSegmentId", "status", "until", "reason"})

        again = late_checkout(SEGMENT, CHECKOUT, DEPART_5H, TRAVELER)
        self.assertEqual(again, result)

    def test_flight_1h_after_checkout_is_not_needed(self) -> None:
        result = _call(departAt=DEPART_1H)

        self.assertEqual(result["hotelSegmentId"], SEGMENT)
        self.assertEqual(result["status"], "not_needed")
        self.assertIsNone(result["until"])
        self.assertIn(TRAVELER, result["reason"])
        self.assertIn("not needed", result["reason"])

    def test_exactly_2h_after_checkout_is_not_needed(self) -> None:
        result = _call(departAt=UNTIL_2H)

        self.assertEqual(result["status"], "not_needed")
        self.assertIsNone(result["until"])

    def test_flight_before_checkout_is_not_needed(self) -> None:
        result = _call(departAt="2026-11-06T08:00:00Z")

        self.assertEqual(result["status"], "not_needed")
        self.assertIsNone(result["until"])

    def test_offset_clocks_compare_as_instants(self) -> None:
        result = _call(
            checkoutAt="2026-11-06T19:00:00+09:00",
            departAt="2026-11-06T16:00:00Z",
        )

        self.assertEqual(result["status"], "requested")
        self.assertEqual(result["until"], "2026-11-06T21:00:00+09:00")
        self.assertEqual(
            _instant(result["until"]) - _instant("2026-11-06T19:00:00+09:00"),
            timedelta(hours=2),
        )

    def test_missing_times_fail_without_raising(self) -> None:
        cases = [
            {"checkoutAt": None},
            {"departAt": None},
            {"checkoutAt": ""},
            {"departAt": "   "},
            {"checkoutAt": "2026-11-06"},
            {"departAt": "2026-11-06"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = _call(**overrides)
                self.assertEqual(result["status"], "failed")
                self.assertIsNone(result["until"])
                self.assertEqual(result["reason"], REASON_MISSING_TIMES)
                self.assertEqual(result["hotelSegmentId"], SEGMENT)

        self.assertEqual(late_checkout(SEGMENT, None, DEPART_5H, TRAVELER)["reason"], REASON_MISSING_TIMES)
        self.assertEqual(late_checkout(SEGMENT, CHECKOUT, None, TRAVELER)["reason"], REASON_MISSING_TIMES)

    def test_bad_times_fail_without_raising(self) -> None:
        result = _call(departAt="tomorrow afternoon")

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["until"])
        self.assertEqual(result["reason"], REASON_BAD_TIMES)

    def test_unreadable_input_fails_without_raising(self) -> None:
        for case in ("not json", "[]", "null", "12"):
            with self.subTest(case=case):
                result = late_checkout(case)
                self.assertEqual(result["status"], "failed")
                self.assertIsNone(result["until"])
                self.assertEqual(result["hotelSegmentId"], "")
                self.assertEqual(result["reason"], REASON_UNREADABLE)

    def test_garbage_does_not_raise(self) -> None:
        cases = [
            None,
            [],
            {},
            {"hotelSegmentId": SEGMENT},
            {"arguments": {"travelerName": TRAVELER}},
            {"input": {"hotelSegmentId": SEGMENT, "travelerName": TRAVELER}},
        ]
        for case in cases:
            with self.subTest(case=case):
                result = late_checkout(case)
                self.assertEqual(set(result), {"hotelSegmentId", "status", "until", "reason"})
                self.assertEqual(result["status"], "failed")
                self.assertIsNone(result["until"])
                self.assertIsInstance(result["reason"], str)
                self.assertTrue(result["reason"])

    def test_snake_case_and_json_string(self) -> None:
        payload = {
            "hotel_segment_id": SEGMENT,
            "checkout_at": CHECKOUT,
            "depart_at": DEPART_1H,
            "traveler_name": TRAVELER,
        }
        result = late_checkout(payload)
        self.assertEqual(result["status"], "not_needed")
        self.assertEqual(result["hotelSegmentId"], SEGMENT)

        encoded = late_checkout(
            json.dumps(
                {
                    "hotelSegmentId": SEGMENT,
                    "checkoutAt": CHECKOUT,
                    "departAt": DEPART_5H,
                    "travelerName": TRAVELER,
                }
            )
        )
        self.assertEqual(encoded["status"], "requested")
        self.assertEqual(encoded["until"], UNTIL_2H)
        self.assertIn(TRAVELER, encoded["reason"])

    def test_tool_spec_is_late_checkout(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "late_checkout")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["hotelSegmentId", "checkoutAt", "departAt", "travelerName"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["status"]["enum"],
            ["requested", "not_needed", "failed"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["hotelSegmentId", "status", "until", "reason"],
        )
        description = TOOL_SPEC["description"]
        self.assertIn("Bedrock AgentCore", description)
        self.assertIn("departure morning", description)
        self.assertIn("room is held", description)
        self.assertIn("late in the day", description)
        self.assertIn("names the traveler", description)
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "late_checkout")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_late_checkout(self) -> None:
        payload = {
            "hotelSegmentId": SEGMENT,
            "checkoutAt": CHECKOUT,
            "departAt": DEPART_5H,
            "travelerName": TRAVELER,
        }
        self.assertEqual(handler(payload), late_checkout(payload))
        self.assertEqual(handler(json.dumps(payload)), late_checkout(payload))
        early = dict(payload, departAt=DEPART_1H)
        self.assertEqual(handler(early)["status"], "not_needed")

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___late_checkout"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), late_checkout(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___book_hotel"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored["status"], "failed")
        self.assertIsNone(ignored["until"])

    def test_readme_tells_the_master_when_to_call(self) -> None:
        readme = Path(__file__).with_name("README.md").read_text(encoding="utf-8")
        self.assertIn("Bedrock AgentCore", readme)
        self.assertIn("departure morning", readme)
        self.assertIn("room is held", readme)
        self.assertIn("late in the day", readme)
        self.assertIn("5 hours after checkout", readme)
        self.assertIn("1 hour after checkout", readme)

    def test_sandbox_sources_do_not_touch_network_or_aws(self) -> None:
        for module in (checkout_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("datetime.now", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("late_checkout opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
