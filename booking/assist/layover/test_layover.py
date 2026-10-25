"""Flight connections: a short international link, a domestic link that fits, a change of airport.

These tests stay in-process. They do not call an airline, AWS, or open a socket.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest

from booking.assist.layover import AGENTCORE_TOOL, TOOL_SPEC, check_layover, handler
from booking.assist.layover import layover as layover_mod
from booking.assist.layover import tool as tool_mod

ARRIVE = "2026-11-06T10:00:00Z"
PLUS_50 = "2026-11-06T10:50:00Z"
PLUS_60 = "2026-11-06T11:00:00Z"
PLUS_45 = "2026-11-06T10:45:00Z"
PLUS_90 = "2026-11-06T11:30:00Z"
PLUS_120 = "2026-11-06T12:00:00Z"
BEFORE = "2026-11-06T09:00:00Z"

_KEYS = {"ok", "gapMinutes", "minimumMinutes", "shortfallMinutes", "action", "reason"}


def _connection(
    arrive: str,
    depart: str,
    international: bool,
    inbound_airport: str = "NRT",
    outbound_airport: str = "NRT",
) -> dict:
    return check_layover(
        inbound={"segmentId": "flight-in", "arriveAt": arrive, "airport": inbound_airport},
        outbound={"segmentId": "flight-out", "departAt": depart, "airport": outbound_airport},
        international=international,
    )


class LayoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_sixty_minute_international_connection_is_short(self) -> None:
        result = _connection(ARRIVE, PLUS_60, True)
        self.assertEqual(
            result,
            {
                "ok": False,
                "gapMinutes": 60,
                "minimumMinutes": 90,
                "shortfallMinutes": 30,
                "action": "replan",
                "reason": "short",
            },
        )

    def test_fifty_minute_domestic_connection_is_ok(self) -> None:
        result = _connection(ARRIVE, PLUS_50, False)
        self.assertEqual(
            result,
            {
                "ok": True,
                "gapMinutes": 50,
                "minimumMinutes": 45,
                "shortfallMinutes": 0,
                "action": "none",
                "reason": "enough",
            },
        )

    def test_different_airports_need_the_user_and_still_report_the_gap(self) -> None:
        comfortable = _connection(ARRIVE, PLUS_120, False, inbound_airport="NRT", outbound_airport="HND")
        self.assertEqual(
            comfortable,
            {
                "ok": False,
                "gapMinutes": 120,
                "minimumMinutes": 45,
                "shortfallMinutes": 0,
                "action": "needs_user",
                "reason": "airport_change",
            },
        )

        short = _connection(ARRIVE, PLUS_60, True, inbound_airport="NRT", outbound_airport="HND")
        self.assertEqual(short["ok"], False)
        self.assertEqual(short["gapMinutes"], 60)
        self.assertEqual(short["minimumMinutes"], 90)
        self.assertEqual(short["shortfallMinutes"], 30)
        self.assertEqual(short["action"], "needs_user")
        self.assertEqual(short["reason"], "airport_change")

    def test_exact_minimum_is_enough(self) -> None:
        international = _connection(ARRIVE, PLUS_90, True)
        domestic = _connection(ARRIVE, PLUS_45, False)
        self.assertTrue(international["ok"])
        self.assertEqual(international["gapMinutes"], 90)
        self.assertEqual(international["shortfallMinutes"], 0)
        self.assertEqual(international["action"], "none")
        self.assertTrue(domestic["ok"])
        self.assertEqual(domestic["gapMinutes"], 45)
        self.assertEqual(domestic["minimumMinutes"], 45)
        self.assertEqual(domestic["shortfallMinutes"], 0)

    def test_one_minute_under_the_minimum_replans(self) -> None:
        international = _connection(ARRIVE, "2026-11-06T11:29:00Z", True)
        domestic = _connection(ARRIVE, "2026-11-06T10:44:00Z", False)
        self.assertEqual(international["gapMinutes"], 89)
        self.assertEqual(international["shortfallMinutes"], 1)
        self.assertEqual(international["action"], "replan")
        self.assertEqual(international["reason"], "short")
        self.assertEqual(domestic["gapMinutes"], 44)
        self.assertEqual(domestic["shortfallMinutes"], 1)
        self.assertEqual(domestic["reason"], "short")

    def test_negative_gap_is_inverted(self) -> None:
        result = _connection(ARRIVE, BEFORE, False)
        self.assertEqual(
            result,
            {
                "ok": False,
                "gapMinutes": -60,
                "minimumMinutes": 45,
                "shortfallMinutes": 105,
                "action": "replan",
                "reason": "inverted",
            },
        )

    def test_airport_change_wins_when_the_gap_is_also_inverted(self) -> None:
        result = _connection(ARRIVE, BEFORE, True, inbound_airport="NRT", outbound_airport="HND")
        self.assertEqual(result["gapMinutes"], -60)
        self.assertEqual(result["minimumMinutes"], 90)
        self.assertEqual(result["shortfallMinutes"], 150)
        self.assertEqual(result["action"], "needs_user")
        self.assertEqual(result["reason"], "airport_change")
        self.assertFalse(result["ok"])

    def test_partial_minute_does_not_count(self) -> None:
        domestic = _connection(ARRIVE, "2026-11-06T10:50:59Z", False)
        self.assertEqual(domestic["gapMinutes"], 50)
        self.assertTrue(domestic["ok"])
        early = _connection(ARRIVE, "2026-11-06T09:59:30Z", False)
        self.assertEqual(early["gapMinutes"], -1)
        self.assertEqual(early["reason"], "inverted")

    def test_offset_clocks_use_the_same_instant(self) -> None:
        result = check_layover(
            {
                "inbound": {
                    "segmentId": "flight-in",
                    "arriveAt": "2026-11-06T19:00:00+09:00",
                    "airport": "nrt",
                },
                "outbound": {
                    "segmentId": "flight-out",
                    "departAt": PLUS_50,
                    "airport": " NRT ",
                },
                "international": False,
            }
        )
        self.assertEqual(result["gapMinutes"], 50)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "enough")

    def test_does_not_mutate_a_plan(self) -> None:
        plan = {
            "flights": [
                {"segmentId": "flight-in", "arriveAt": ARRIVE, "airport": "NRT"},
                {"segmentId": "flight-out", "departAt": PLUS_60, "airport": "NRT"},
            ]
        }
        payload = {
            "inbound": {"segmentId": "flight-in", "arriveAt": ARRIVE, "airport": "NRT"},
            "outbound": {"segmentId": "flight-out", "departAt": PLUS_60, "airport": "NRT"},
            "international": True,
            "plan": plan,
        }
        snapshot = copy.deepcopy(payload)
        result = check_layover(payload)
        self.assertEqual(payload, snapshot)
        self.assertIs(payload["plan"], plan)
        self.assertEqual(result["reason"], "short")
        self.assertNotIn("plan", result)

    def test_partial_input_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            [],
            {"inbound": {"segmentId": "flight-in", "arriveAt": ARRIVE, "airport": "NRT"}},
            {
                "inbound": {"segmentId": "flight-in", "arriveAt": "2026-11-06", "airport": "NRT"},
                "outbound": {"segmentId": "flight-out", "departAt": PLUS_60, "airport": "NRT"},
                "international": True,
            },
            {
                "inbound": {"segmentId": "flight-in", "arriveAt": ARRIVE, "airport": "NRT"},
                "outbound": {"segmentId": "flight-out", "departAt": PLUS_60, "airport": "NRT"},
                "international": "true",
            },
            {
                "inbound": {"arriveAt": ARRIVE, "airport": "NRT"},
                "outbound": {"segmentId": "flight-out", "departAt": PLUS_60, "airport": "NRT"},
                "international": False,
            },
            {
                "inbound": {"segmentId": "flight-in", "arriveAt": ARRIVE, "airport": ""},
                "outbound": {"segmentId": "flight-out", "departAt": PLUS_60, "airport": "NRT"},
                "international": False,
            },
        ]
        for case in cases:
            result = check_layover(case)
            self.assertEqual(set(result), _KEYS)
            self.assertFalse(result["ok"])
            self.assertEqual(result["gapMinutes"], 0)
            self.assertEqual(result["minimumMinutes"], 0)
            self.assertEqual(result["shortfallMinutes"], 0)
            self.assertEqual(result["action"], "none")
            self.assertEqual(result["reason"], "invalid_input")

        self.assertEqual(check_layover()["reason"], "invalid_input")

    def test_json_string_and_argument_wrapper(self) -> None:
        payload = {
            "inbound": {"segmentId": "flight-in", "arriveAt": ARRIVE, "airport": "NRT"},
            "outbound": {"segmentId": "flight-out", "departAt": PLUS_60, "airport": "NRT"},
            "international": True,
        }
        self.assertEqual(check_layover(json.dumps(payload))["shortfallMinutes"], 30)
        wrapped = check_layover({"arguments": payload})
        self.assertEqual(wrapped["reason"], "short")
        nested = check_layover({"input": payload})
        self.assertEqual(nested["ok"], False)
        self.assertEqual(nested["action"], "replan")

    def test_tool_spec_is_check_layover(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_layover")
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["required"],
            ["inbound", "outbound", "international"],
        )
        self.assertEqual(
            TOOL_SPEC["outputSchema"]["required"],
            ["ok", "gapMinutes", "minimumMinutes", "shortfallMinutes", "action", "reason"],
        )
        self.assertIn("90", TOOL_SPEC["description"])
        self.assertIn("45", TOOL_SPEC["description"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("airline api", TOOL_SPEC["description"].lower())
        self.assertIn("does not change a plan", TOOL_SPEC["description"].lower())
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_layover")
        self.assertEqual(
            AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"],
            TOOL_SPEC["inputSchema"],
        )

    def test_handler_calls_check_layover(self) -> None:
        payload = {
            "inbound": {"segmentId": "flight-in", "arriveAt": ARRIVE, "airport": "NRT"},
            "outbound": {"segmentId": "flight-out", "departAt": PLUS_50, "airport": "NRT"},
            "international": False,
        }
        self.assertEqual(handler(payload), check_layover(payload))
        self.assertEqual(handler(json.dumps(payload)), check_layover(payload))
        named = handler(payload, _AgentCoreContext("assist___check_layover"))
        self.assertTrue(named["ok"])
        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(
            rejected,
            {
                "ok": False,
                "gapMinutes": 0,
                "minimumMinutes": 0,
                "shortfallMinutes": 0,
                "action": "none",
                "reason": "ignored_tool",
            },
        )

    def test_does_not_read_the_wall_clock_or_call_an_airline(self) -> None:
        source = inspect.getsource(layover_mod) + inspect.getsource(tool_mod)
        for banned in (
            "datetime.now",
            ".utcnow",
            "time.time",
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "httpx",
            "amadeus",
            "duffel",
            "booking.master",
            "socket",
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
            raise AssertionError("check_layover opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
