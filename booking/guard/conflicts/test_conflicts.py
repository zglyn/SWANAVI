"""Schedule conflicts: overlapping windows, not back-to-back, not removed.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest

from booking.guard.conflicts import AGENTCORE_TOOL, TOOL_SPEC, check_conflicts, handler
from booking.guard.conflicts import conflicts as conflicts_mod
from booking.guard.conflicts import tool as tool_mod

DAY = "2026-11-02"
NOW = "2026-11-02T12:10:00Z"


def _flight(segment_id: str, **extra) -> dict:
    segment = {
        "segmentId": segment_id,
        "kind": "flight",
        "from": "SFO",
        "to": "KIX",
        "departDate": DAY,
    }
    segment.update(extra)
    return segment


def _hotel(segment_id: str, **extra) -> dict:
    segment = {
        "segmentId": segment_id,
        "kind": "hotel",
        "city": "Kyoto",
        "checkIn": DAY,
        "checkOut": "2026-11-04",
    }
    segment.update(extra)
    return segment


def _attraction(segment_id: str, **extra) -> dict:
    segment = {
        "segmentId": segment_id,
        "kind": "attraction",
        "name": segment_id,
        "city": "Kyoto",
        "date": DAY,
    }
    segment.update(extra)
    return segment


def _plan(flights=(), hotels=(), attractions=()) -> dict:
    return {
        "tripId": "trip-1",
        "flights": list(flights),
        "hotels": list(hotels),
        "attractions": list(attractions),
    }


class ConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_overlapping_attraction_and_flight(self) -> None:
        plan = _plan(
            flights=[
                _flight(
                    "flight-1",
                    start="2026-11-02T09:00:00Z",
                    end="2026-11-02T12:00:00Z",
                )
            ],
            attractions=[
                _attraction(
                    "attraction-1",
                    start="2026-11-02T11:00:00Z",
                    end="2026-11-02T13:00:00Z",
                )
            ],
        )
        original = copy.deepcopy(plan)
        result = check_conflicts(NOW, plan)

        self.assertEqual(
            result,
            {
                "conflicts": [
                    {"segmentA": "flight-1", "segmentB": "attraction-1", "overlapMinutes": 60}
                ]
            },
        )
        self.assertEqual(plan, original)

    def test_back_to_back_segments_are_not_a_conflict(self) -> None:
        plan = _plan(
            flights=[
                _flight(
                    "flight-1",
                    start="2026-11-02T09:00:00Z",
                    end="2026-11-02T12:00:00Z",
                )
            ],
            attractions=[
                _attraction(
                    "attraction-1",
                    start="2026-11-02T12:00:00Z",
                    end="2026-11-02T14:00:00Z",
                )
            ],
        )
        self.assertEqual(check_conflicts(NOW, plan), {"conflicts": []})

        derived = _plan(
            flights=[_flight("flight-1", departDate=DAY)],
            attractions=[_attraction("attraction-2", date=DAY, time="12:00")],
        )
        self.assertEqual(check_conflicts({"now": NOW, "plan": derived})["conflicts"], [])

    def test_removed_segment_is_ignored(self) -> None:
        plan = _plan(
            flights=[
                _flight(
                    "flight-1",
                    start="2026-11-02T09:00:00Z",
                    end="2026-11-02T12:00:00Z",
                )
            ],
            attractions=[
                _attraction(
                    "attraction-removed",
                    start="2026-11-02T11:00:00Z",
                    end="2026-11-02T13:00:00Z",
                    removed=True,
                ),
                _attraction(
                    "attraction-live",
                    start="2026-11-02T11:30:00Z",
                    end="2026-11-02T12:30:00Z",
                ),
            ],
        )
        result = check_conflicts(NOW, plan)
        self.assertEqual(
            result["conflicts"],
            [{"segmentA": "flight-1", "segmentB": "attraction-live", "overlapMinutes": 30}],
        )

        only_removed = _plan(
            flights=[_flight("flight-1", start="2026-11-02T09:00:00Z", end="2026-11-02T12:00:00Z")],
            attractions=[
                _attraction(
                    "attraction-removed",
                    start="2026-11-02T10:00:00Z",
                    end="2026-11-02T11:00:00Z",
                    removed=True,
                )
            ],
        )
        self.assertEqual(check_conflicts(NOW, only_removed), {"conflicts": []})

    def test_derived_clocks_match_replan_rules(self) -> None:
        plan = _plan(
            flights=[_flight("flight-1", departDate=DAY)],
            hotels=[_hotel("hotel-1", checkIn=DAY, checkOut="2026-11-04")],
            attractions=[
                _attraction("attraction-timed", date=DAY, time="10:00"),
                _attraction("attraction-default", date="2026-11-03"),
                _attraction("attraction-stamp", date="2026-11-03T14:30:00Z"),
            ],
        )
        by_pair = {
            (item["segmentA"], item["segmentB"]): item["overlapMinutes"]
            for item in check_conflicts(NOW, plan)["conflicts"]
        }
        # Flight 09:00-12:00 and attraction 10:00-12:00 share 120 minutes.
        self.assertEqual(by_pair[("flight-1", "attraction-timed")], 120)
        # Hotel 15:00 on the 2nd through 11:00 on the 4th covers the 3rd.
        # Default attraction is 10:00-12:00. Stamped attraction is 14:30-16:30.
        self.assertEqual(by_pair[("hotel-1", "attraction-default")], 120)
        self.assertEqual(by_pair[("hotel-1", "attraction-stamp")], 120)
        self.assertNotIn(("flight-1", "hotel-1"), by_pair)
        self.assertNotIn(("flight-1", "attraction-default"), by_pair)

        timed_depart = _plan(
            flights=[_flight("flight-late", departDate="2026-11-02T15:00:00Z")],
            attractions=[_attraction("show", date=DAY, time="16:00")],
        )
        self.assertEqual(
            check_conflicts(NOW, timed_depart)["conflicts"],
            [{"segmentA": "flight-late", "segmentB": "show", "overlapMinutes": 120}],
        )

    def test_explicit_window_beats_derived_clocks(self) -> None:
        plan = _plan(
            flights=[
                _flight(
                    "flight-1",
                    departDate=DAY,
                    start="2026-11-02T18:00:00Z",
                    end="2026-11-02T19:00:00Z",
                )
            ],
            attractions=[_attraction("attraction-1", date=DAY, time="10:00")],
        )
        self.assertEqual(check_conflicts(NOW, plan), {"conflicts": []})

    def test_partial_plan_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"now": None, "plan": None},
            {"plan": {"flights": [None, "x", {}]}, "now": "not-a-time"},
            {"flights": [{"segmentId": "flight-1"}]},
            {"now": NOW, "plan": {"hotels": "nope", "attractions": None}},
            [],
            {"now": NOW, "plan": {"flights": [{"segmentId": "flight-1", "departDate": "yesterday"}]}},
        ]
        for case in cases:
            result = check_conflicts(case)
            self.assertEqual(set(result), {"conflicts"})
            self.assertIsInstance(result["conflicts"], list)

        self.assertEqual(check_conflicts(), {"conflicts": []})
        self.assertEqual(check_conflicts(now=NOW, plan=None, tripId="trip-1"), {"conflicts": []})

    def test_now_does_not_change_the_conflicts(self) -> None:
        plan = _plan(
            flights=[_flight("flight-1", start="2026-11-02T09:00:00Z", end="2026-11-02T12:00:00Z")],
            attractions=[_attraction("attraction-1", start="2026-11-02T11:00:00Z", end="2026-11-02T13:00:00Z")],
        )
        first = check_conflicts("2026-11-01T00:00:00Z", plan)
        second = check_conflicts("2026-11-09T00:00:00Z", plan)
        third = check_conflicts("not-a-time", plan)
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_tool_spec_is_check_conflicts(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "check_conflicts")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["now", "plan"])
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["conflicts"])
        item = TOOL_SPEC["outputSchema"]["properties"]["conflicts"]["items"]
        self.assertEqual(item["required"], ["segmentA", "segmentB", "overlapMinutes"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("after a replan", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "check_conflicts")
        self.assertEqual(AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"], TOOL_SPEC["inputSchema"])

    def test_handler_calls_check_conflicts(self) -> None:
        plan = _plan(
            flights=[_flight("flight-1", start="2026-11-02T09:00:00Z", end="2026-11-02T12:00:00Z")],
            attractions=[_attraction("attraction-1", start="2026-11-02T11:00:00Z", end="2026-11-02T13:00:00Z")],
        )
        payload = {"now": NOW, "plan": plan}
        self.assertEqual(handler(payload), check_conflicts(payload))
        self.assertEqual(handler(json.dumps(payload)), check_conflicts(payload))
        wrapped = handler({"arguments": payload}, _AgentCoreContext("guard___check_conflicts"))
        self.assertEqual(wrapped["conflicts"][0]["overlapMinutes"], 60)
        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertEqual(rejected, {"conflicts": []})

    def test_does_not_read_the_wall_clock_or_aws(self) -> None:
        source = inspect.getsource(conflicts_mod) + inspect.getsource(tool_mod)
        for banned in (
            "datetime.now",
            ".utcnow",
            "time.time",
            "boto3",
            "botocore",
            "requests",
            "urllib",
            "bedrock_agentcore",
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
            raise AssertionError("check_conflicts opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
