"""Flight check-in: 24 hour window, sandbox boarding pass, no airline call.

These tests stay in-process. They do not call an airline, AWS, or open a socket.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.checkin import AGENTCORE_TOOL, TOOL_SPEC, check_in_flight, handler
from booking.assist.checkin import checkin as checkin_mod
from booking.assist.checkin.checkin import ERROR_INVALID
from booking.assist.checkin import tool as tool_mod

SEGMENT = "flight-1"
DEPART = "2026-11-02T09:00:00Z"
OPENS = "2026-11-01T09:00:00Z"
CODE = "SANDBOX-FLIGHT"
TRAVELERS = [{"id": "t1", "name": "Ada Lovelace"}]


def _segment(**overrides):
    segment = {
        "segmentId": SEGMENT,
        "kind": "flight",
        "departAt": DEPART,
        "confirmationCode": CODE,
    }
    segment.update(overrides)
    return segment


def _check(**overrides):
    payload = {
        "now": "2026-11-01T12:00:00Z",
        "segment": _segment(),
        "travelers": list(TRAVELERS),
    }
    if "segment" in overrides and isinstance(overrides["segment"], dict):
        payload["segment"] = _segment(**overrides.pop("segment"))
    payload.update(overrides)
    return check_in_flight(payload)


class CheckInFlightTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_waiting_before_the_window(self) -> None:
        result = _check(now="2026-11-01T08:59:59Z")

        self.assertEqual(
            set(result),
            {"segmentId", "status", "boardingPass", "opensAt", "error"},
        )
        self.assertEqual(result["segmentId"], SEGMENT)
        self.assertEqual(result["status"], "waiting")
        self.assertIsNone(result["boardingPass"])
        self.assertEqual(result["opensAt"], OPENS)
        self.assertIsNone(result["error"])

    def test_checked_in_inside_the_window(self) -> None:
        opened = _check(now=OPENS)
        later = _check(now="2026-11-02T08:59:59Z")

        for result in (opened, later):
            self.assertEqual(result["status"], "checked_in")
            self.assertEqual(result["opensAt"], OPENS)
            self.assertIsNone(result["error"])
            self.assertIsInstance(result["boardingPass"], str)
            self.assertTrue(result["boardingPass"].startswith("SANDBOX-BP-"))
            self.assertNotIn(" ", result["boardingPass"])
        self.assertEqual(opened["boardingPass"], later["boardingPass"])

        again = check_in_flight("2026-11-01T12:00:00Z", _segment(), list(TRAVELERS))
        self.assertEqual(again["boardingPass"], opened["boardingPass"])
        self.assertNotEqual(
            again["boardingPass"],
            _check(segment={"confirmationCode": "SANDBOX-OTHER"})["boardingPass"],
        )

    def test_missed_after_departure(self) -> None:
        at_departure = _check(now=DEPART)
        after = _check(now="2026-11-02T09:00:01Z")

        for result in (at_departure, after):
            self.assertEqual(result["status"], "missed")
            self.assertIsNone(result["boardingPass"])
            self.assertEqual(result["opensAt"], OPENS)
            self.assertIsNone(result["error"])

    def test_needs_user_without_a_confirmation_code(self) -> None:
        cases = [
            {"confirmationCode": None},
            {"confirmationCode": ""},
            {"confirmationCode": "   "},
        ]
        for segment in cases:
            result = _check(now="2026-11-01T12:00:00Z", segment=segment)
            self.assertEqual(result["status"], "needs_user")
            self.assertIsNone(result["boardingPass"])
            self.assertEqual(result["opensAt"], OPENS)
            self.assertIsNone(result["error"])

        omitted = _segment()
        del omitted["confirmationCode"]
        result = check_in_flight(
            {"now": "2026-11-01T12:00:00Z", "segment": omitted, "travelers": TRAVELERS}
        )
        self.assertEqual(result["status"], "needs_user")
        self.assertIsNone(result["boardingPass"])

    def test_date_only_depart_date_is_nine_utc(self) -> None:
        segment = {
            "segmentId": SEGMENT,
            "kind": "flight",
            "departDate": "2026-11-02",
            "confirmationCode": CODE,
        }
        waiting = check_in_flight(
            {"now": "2026-11-01T08:59:59Z", "segment": segment, "travelers": TRAVELERS}
        )
        checked = check_in_flight(
            {"now": "2026-11-01T09:00:00Z", "segment": segment, "travelers": TRAVELERS}
        )

        self.assertEqual(waiting["status"], "waiting")
        self.assertEqual(waiting["opensAt"], OPENS)
        self.assertIsNone(waiting["boardingPass"])
        self.assertEqual(checked["status"], "checked_in")
        self.assertTrue(checked["boardingPass"].startswith("SANDBOX-BP-"))
        self.assertEqual(checked["opensAt"], OPENS)

    def test_not_a_flight(self) -> None:
        result = _check(segment={"kind": "hotel", "departAt": DEPART, "confirmationCode": CODE})

        self.assertEqual(result["status"], "not_a_flight")
        self.assertEqual(result["segmentId"], SEGMENT)
        self.assertIsNone(result["boardingPass"])
        self.assertIsNone(result["opensAt"])
        self.assertIsNone(result["error"])

    def test_bad_input_returns_invalid_segment(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"now": DEPART},
            {"now": DEPART, "segment": _segment()},
            {"now": "tomorrow", "segment": _segment(), "travelers": TRAVELERS},
            {"now": DEPART, "segment": {"kind": "flight"}, "travelers": TRAVELERS},
            {
                "now": DEPART,
                "segment": {"segmentId": SEGMENT, "kind": "flight", "confirmationCode": CODE},
                "travelers": TRAVELERS,
            },
            {"now": DEPART, "segment": _segment(), "travelers": None},
            {"now": "2026-11-02", "segment": _segment(), "travelers": TRAVELERS},
        ]
        for case in cases:
            result = check_in_flight(case)
            self.assertEqual(result["error"], ERROR_INVALID)
            self.assertEqual(result["error"], "invalid_segment")
            self.assertIsNone(result["status"])
            self.assertIsNone(result["boardingPass"])
            self.assertIsNone(result["opensAt"])
            self.assertIsInstance(result["segmentId"], str)

        shifted = _check(segment={"departAt": "2026-11-02T18:00:00+09:00"})
        self.assertEqual(shifted["status"], "checked_in")
        self.assertEqual(shifted["opensAt"], OPENS)

    def test_tool_spec_is_check_in_flight(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_in_flight")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["now", "segment", "travelers"])
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["segmentId", "status", "boardingPass", "opensAt", "error"],
        )
        self.assertIn("24 hour", TOOL_SPEC["description"])
        self.assertIn("SANDBOX-BP-", TOOL_SPEC["description"])
        self.assertIn("not a real barcode", TOOL_SPEC["description"])
        self.assertIn("invalid_segment", TOOL_SPEC["description"])
        self.assertIn("no airline API", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_in_flight")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_check_in_flight(self) -> None:
        payload = {
            "now": "2026-11-01T12:00:00Z",
            "segment": _segment(),
            "travelers": TRAVELERS,
        }
        self.assertEqual(handler(payload), check_in_flight(payload))
        self.assertEqual(handler(json.dumps(payload)), check_in_flight(payload))
        self.assertEqual(handler(None)["error"], "invalid_segment")

        class _Custom:
            custom = {"bedrockAgentCoreToolName": "runtime___check_in_flight"}

        class _Context:
            client_context = _Custom()

        self.assertEqual(handler(payload, _Context()), check_in_flight(payload))

        class _Other:
            custom = {"bedrockAgentCoreToolName": "runtime___book_flight"}

        class _OtherContext:
            client_context = _Other()

        ignored = handler(payload, _OtherContext())
        self.assertEqual(ignored["error"], "invalid_segment")
        self.assertIsNone(ignored["boardingPass"])

    def test_sandbox_sources_do_not_touch_network_or_airline(self) -> None:
        for module in (checkin_mod, tool_mod):
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
            raise AssertionError("check_in_flight opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
