"""Ground transfers: the ride fits, the ride is short, or the stops overlap.

These tests stay in-process. They do not call AWS, a maps API, or open a socket.
"""

from __future__ import annotations

import inspect
import json
import socket
import unittest

from booking.assist.transfers import AGENTCORE_TOOL, TOOL_SPEC, check_transfer, handler
from booking.assist.transfers import tool as tool_mod
from booking.assist.transfers import transfer as transfer_mod

FROM_END = "2026-11-03T10:00:00Z"
FORTY_LATER = "2026-11-03T10:40:00Z"
TEN_LATER = "2026-11-03T10:10:00Z"
OVERLAP = "2026-11-03T09:45:00Z"


def _call(from_end: str, to_start: str, travel: int) -> dict:
    return check_transfer(
        fromSegmentId="temple",
        toSegmentId="garden",
        fromEnd=from_end,
        toStart=to_start,
        travelMinutes=travel,
    )


class TransferTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_forty_minute_gap_covers_a_thirty_minute_ride(self) -> None:
        result = _call(FROM_END, FORTY_LATER, 30)
        self.assertEqual(
            result,
            {
                "ok": True,
                "leaveBy": FROM_END,
                "shortfallMinutes": 0,
                "reason": "enough_time",
            },
        )

    def test_exact_gap_is_enough(self) -> None:
        result = _call(FROM_END, "2026-11-03T10:30:00Z", 30)
        self.assertTrue(result["ok"])
        self.assertEqual(result["leaveBy"], FROM_END)
        self.assertEqual(result["shortfallMinutes"], 0)

    def test_ten_minute_gap_is_short_by_twenty(self) -> None:
        result = _call(FROM_END, TEN_LATER, 30)
        self.assertEqual(
            result,
            {
                "ok": False,
                "leaveBy": None,
                "shortfallMinutes": 20,
                "reason": "shortfall",
            },
        )

    def test_overlap_is_not_ok(self) -> None:
        result = _call(FROM_END, OVERLAP, 30)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["leaveBy"])
        self.assertEqual(result["reason"], "overlap")
        self.assertEqual(result["shortfallMinutes"], 45)

    def test_zero_gap_is_a_shortfall_not_an_overlap(self) -> None:
        result = _call(FROM_END, FROM_END, 30)
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["reason"], "shortfall")
        self.assertEqual(result["shortfallMinutes"], 30)
        self.assertIsNone(result["leaveBy"])

    def test_offset_clocks_use_the_same_instant(self) -> None:
        result = check_transfer(
            {
                "fromSegmentId": "temple",
                "toSegmentId": "garden",
                "fromEnd": "2026-11-03T19:00:00+09:00",
                "toStart": FORTY_LATER,
                "travelMinutes": 30,
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["leaveBy"], "2026-11-03T19:00:00+09:00")

    def test_partial_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            [],
            {"fromEnd": FROM_END},
            {"fromEnd": "2026-11-03", "toStart": FORTY_LATER, "travelMinutes": 30},
            {"fromEnd": FROM_END, "toStart": "later", "travelMinutes": 30},
            {"fromEnd": FROM_END, "toStart": FORTY_LATER, "travelMinutes": True},
            {"fromEnd": FROM_END, "toStart": FORTY_LATER, "travelMinutes": "soon"},
            {"fromEnd": FROM_END, "toStart": FORTY_LATER},
        ]
        for case in cases:
            result = check_transfer(case)
            self.assertEqual(set(result), {"ok", "leaveBy", "shortfallMinutes", "reason"})
            self.assertFalse(result["ok"])
            self.assertIsNone(result["leaveBy"])
            self.assertEqual(result["shortfallMinutes"], 0)
            self.assertEqual(result["reason"], "invalid_input")

        self.assertEqual(check_transfer()["reason"], "invalid_input")

    def test_json_string_and_argument_wrapper(self) -> None:
        payload = {
            "fromSegmentId": "temple",
            "toSegmentId": "garden",
            "fromEnd": FROM_END,
            "toStart": TEN_LATER,
            "travelMinutes": "30",
        }
        self.assertEqual(check_transfer(json.dumps(payload))["shortfallMinutes"], 20)
        wrapped = check_transfer({"arguments": payload})
        self.assertEqual(wrapped["reason"], "shortfall")
        nested = check_transfer({"input": payload})
        self.assertEqual(nested["ok"], False)

    def test_tool_spec_is_check_transfer(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_transfer")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["fromSegmentId", "toSegmentId", "fromEnd", "toStart", "travelMinutes"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["ok", "leaveBy", "shortfallMinutes", "reason"],
        )
        self.assertIn("between consecutive stops", TOOL_SPEC["description"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_transfer")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_check_transfer(self) -> None:
        payload = {
            "fromSegmentId": "temple",
            "toSegmentId": "garden",
            "fromEnd": FROM_END,
            "toStart": FORTY_LATER,
            "travelMinutes": 30,
        }
        self.assertEqual(handler(payload), check_transfer(payload))
        self.assertEqual(handler(json.dumps(payload)), check_transfer(payload))
        named = handler(payload, _AgentCoreContext("assist___check_transfer"))
        self.assertTrue(named["ok"])
        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(
            rejected,
            {"ok": False, "leaveBy": None, "shortfallMinutes": 0, "reason": "ignored_tool"},
        )

    def test_does_not_read_the_wall_clock_maps_or_aws(self) -> None:
        source = inspect.getsource(transfer_mod) + inspect.getsource(tool_mod)
        for banned in (
            "datetime.now",
            ".utcnow",
            "time.time",
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "httpx",
            "maps.googleapis",
            "mapbox",
            "openrouteservice",
            "nominatim",
        ):
            self.assertNotIn(banned, source)


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = type("ClientContext", (), {})()
        self.client_context.custom = {"bedrockAgentCoreToolName": tool_name}


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("check_transfer opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
