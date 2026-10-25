"""Luggage drop: an early arrival requests a hold, a later arrival does not.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest
from pathlib import Path

from booking.assist.luggage import AGENTCORE_TOOL, TOOL_SPEC, handler, luggage_drop
from booking.assist.luggage import drop as drop_mod
from booking.assist.luggage.drop import REASON_NO_ARRIVE, REASON_NO_CHECKIN, REASON_NO_NAME
from booking.assist.luggage import tool as tool_mod

HOTEL = "hotel-1"
TRAVELER = "Ada Lovelace"
ARRIVE_EARLY = "2026-11-02T10:00:00Z"
CHECK_IN = "2026-11-02T15:00:00Z"
ARRIVE_LATE = "2026-11-02T16:30:00Z"


def _payload(**overrides) -> dict:
    payload = {
        "hotelSegmentId": HOTEL,
        "travelerName": TRAVELER,
        "arriveAt": ARRIVE_EARLY,
        "checkInAt": CHECK_IN,
    }
    payload.update(overrides)
    return payload


class LuggageDropTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_early_arrival_requests_a_drop(self) -> None:
        result = luggage_drop(_payload())

        self.assertEqual(set(result), {"hotelSegmentId", "status", "deskNote", "reason"})
        self.assertEqual(result["hotelSegmentId"], HOTEL)
        self.assertEqual(result["status"], "drop_requested")
        self.assertIn(TRAVELER, result["deskNote"])
        self.assertIn("hold bags", result["deskNote"])
        self.assertIn(CHECK_IN, result["deskNote"])
        self.assertIn("Desk", result["deskNote"])
        self.assertIsNone(result["reason"])

        again = luggage_drop(HOTEL, TRAVELER, ARRIVE_EARLY, CHECK_IN)
        self.assertEqual(again, result)

    def test_arrival_after_check_in_is_not_needed(self) -> None:
        result = luggage_drop(_payload(arriveAt=ARRIVE_LATE))

        self.assertEqual(result["hotelSegmentId"], HOTEL)
        self.assertEqual(result["status"], "not_needed")
        self.assertEqual(result["deskNote"], "")
        self.assertNotIn("hold bags", result["deskNote"])
        self.assertIsNone(result["reason"])

    def test_arrival_at_check_in_is_not_needed(self) -> None:
        result = luggage_drop(_payload(arriveAt=CHECK_IN))

        self.assertEqual(result["status"], "not_needed")
        self.assertEqual(result["deskNote"], "")
        self.assertIsNone(result["reason"])

        offset = luggage_drop(
            _payload(arriveAt="2026-11-02T16:00:00+01:00", checkInAt="2026-11-02T15:00:00Z")
        )
        self.assertEqual(offset["status"], "not_needed")

    def test_missing_time_fails_without_raising(self) -> None:
        cases = [
            ({"arriveAt": None}, REASON_NO_ARRIVE),
            ({"arriveAt": ""}, REASON_NO_ARRIVE),
            ({"arriveAt": "   "}, REASON_NO_ARRIVE),
            ({"checkInAt": None}, REASON_NO_CHECKIN),
            ({"checkInAt": ""}, REASON_NO_CHECKIN),
        ]
        for overrides, reason in cases:
            payload = _payload()
            payload.update(overrides)
            if overrides.get("arriveAt", "kept") is None and "arriveAt" in overrides:
                del payload["arriveAt"]
            if overrides.get("checkInAt", "kept") is None and "checkInAt" in overrides:
                del payload["checkInAt"]
            result = luggage_drop(payload)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["deskNote"], "")
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["hotelSegmentId"], HOTEL)
            self.assertEqual(set(result), {"hotelSegmentId", "status", "deskNote", "reason"})

        both = luggage_drop({"hotelSegmentId": HOTEL, "travelerName": TRAVELER})
        self.assertEqual(both["status"], "failed")
        self.assertIn("missing", both["reason"])

    def test_early_arrival_without_a_name_fails_without_raising(self) -> None:
        result = luggage_drop(_payload(travelerName="  "))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], REASON_NO_NAME)
        self.assertEqual(result["deskNote"], "")
        self.assertNotIn("hold bags", result["deskNote"])

    def test_other_failures_do_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            [],
            {},
            {"arriveAt": "tomorrow", "checkInAt": CHECK_IN},
            {"arriveAt": ARRIVE_EARLY, "checkInAt": "noon"},
            {"hotelSegmentId": HOTEL, "arriveAt": 1730541600, "checkInAt": CHECK_IN},
            {"arguments": {"travelerName": TRAVELER}},
        ]
        for case in cases:
            result = luggage_drop(case)
            self.assertEqual(set(result), {"hotelSegmentId", "status", "deskNote", "reason"})
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["deskNote"], "")
            self.assertIsInstance(result["reason"], str)
            self.assertTrue(result["reason"])

    def test_json_and_arguments_envelope(self) -> None:
        payload = _payload()
        self.assertEqual(luggage_drop(json.dumps(payload)), luggage_drop(payload))
        wrapped = luggage_drop({"arguments": payload})
        self.assertEqual(wrapped["status"], "drop_requested")
        self.assertIn(TRAVELER, wrapped["deskNote"])

    def test_tool_spec_is_luggage_drop(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "luggage_drop")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["hotelSegmentId", "travelerName", "arriveAt", "checkInAt"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["properties"]["status"]["enum"],
            ["drop_requested", "not_needed", "failed"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["hotelSegmentId", "status", "deskNote", "reason"],
        )
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("flight lands before hotel check-in", TOOL_SPEC["description"])
        self.assertIn("hold bags", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "luggage_drop")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_luggage_drop(self) -> None:
        payload = _payload()
        self.assertEqual(handler(payload), luggage_drop(payload))
        self.assertEqual(handler(json.dumps(payload)), luggage_drop(payload))

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___luggage_drop"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), luggage_drop(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___book_hotel"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored["status"], "failed")
        self.assertEqual(ignored["deskNote"], "")
        self.assertIsInstance(ignored["reason"], str)

    def test_readme_says_the_master_calls_this_before_check_in(self) -> None:
        text = (Path(__file__).with_name("README.md")).read_text(encoding="utf-8")
        self.assertIn("luggage_drop", text)
        self.assertIn("Bedrock AgentCore", text)
        self.assertIn("flight lands before hotel check-in", text)

    def test_sandbox_sources_do_not_touch_network_or_aws(self) -> None:
        for module in (drop_mod, tool_mod):
            source = inspect.getsource(module)
            self.assertNotIn("boto", source)
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("http.client", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("subprocess", source)
            self.assertNotIn("datetime.now", source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("luggage_drop opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
