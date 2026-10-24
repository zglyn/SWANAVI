"""Late-finish replan: shift the rest of the day, keep what already started.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import copy
import inspect
import json
import socket
import unittest

from booking.replan.late import AGENTCORE_TOOL, TOOL_SPEC, handler, replan_late
from booking.replan.late import replan as replan_mod
from booking.replan.late import tool as tool_mod


def _attraction(segment_id: str, date: str, time: str | None = None, **extra) -> dict:
    segment = {
        "segmentId": segment_id,
        "kind": "attraction",
        "name": segment_id,
        "city": "Kyoto",
        "date": date,
        "partySize": 1,
    }
    if time is not None:
        segment["time"] = time
    segment.update(extra)
    return segment


DAY = "2026-11-02"
NEXT_DAY = "2026-11-03"
NOW = "2026-11-02T12:10:00Z"


def _day_plan() -> dict:
    return {
        "tripId": "trip-1",
        "flights": [],
        "hotels": [],
        "attractions": [
            _attraction("attraction-1", DAY, "10:00"),
            _attraction("attraction-2", DAY, "12:30"),
            _attraction("attraction-3", DAY, "15:00"),
            _attraction("attraction-next", NEXT_DAY, "09:00"),
        ],
    }


def _late(segment_id: str, kind: str, delta) -> dict:
    return {
        "segmentId": segment_id,
        "kind": kind,
        "event": "ended_late",
        "deltaMinutes": delta,
    }


class LateReplanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_sixty_minutes_late_pushes_the_next_same_day_item(self) -> None:
        plan = _day_plan()
        original = copy.deepcopy(plan)
        result = replan_late("trip-1", NOW, plan, _late("attraction-1", "attraction", 60))

        self.assertTrue(result["changed"])
        self.assertEqual(result["segmentId"], "attraction-1")
        self.assertEqual(result["event"], "ended_late")
        self.assertEqual(result["plan"]["attractions"][0], original["attractions"][0])
        self.assertEqual(result["plan"]["attractions"][1]["time"], "13:30")
        self.assertEqual(result["plan"]["attractions"][1]["date"], DAY)
        self.assertEqual(result["plan"]["attractions"][1]["start"], "2026-11-02T13:30:00Z")
        self.assertEqual(result["plan"]["attractions"][1]["end"], "2026-11-02T15:30:00Z")
        self.assertEqual(result["plan"]["attractions"][2]["time"], "16:00")
        self.assertEqual(result["plan"]["attractions"][2]["start"], "2026-11-02T16:00:00Z")
        self.assertEqual(result["plan"]["attractions"][3], original["attractions"][3])
        self.assertEqual(plan, original)
        self.assertIn("shifted attraction-2 later by 60 minutes", result["notes"])
        self.assertIn("kept finished segment attraction-1", result["notes"])

    def test_segment_already_started_does_not_move(self) -> None:
        plan = {
            "tripId": "trip-1",
            "attractions": [
                _attraction("attraction-1", DAY, "09:00"),
                _attraction("attraction-started", DAY, "11:15"),
                _attraction("attraction-2", DAY, "13:00"),
            ],
        }
        original = copy.deepcopy(plan)
        result = replan_late(
            "trip-1",
            "2026-11-02T12:00:00Z",
            plan,
            _late("attraction-1", "attraction", 60),
        )

        self.assertTrue(result["changed"])
        self.assertEqual(result["plan"]["attractions"][0], original["attractions"][0])
        self.assertEqual(result["plan"]["attractions"][1], original["attractions"][1])
        self.assertNotIn("start", result["plan"]["attractions"][1])
        self.assertEqual(result["plan"]["attractions"][2]["time"], "14:00")
        self.assertIn("left attraction-started in place; it already started before now", result["notes"])

    def test_zero_delta_does_not_change_the_plan(self) -> None:
        plan = _day_plan()
        original = copy.deepcopy(plan)
        for delta in (0, -15, 0.0):
            result = replan_late("trip-1", NOW, plan, _late("attraction-1", "attraction", delta))
            self.assertFalse(result["changed"])
            self.assertEqual(result["event"], "ended_late")
            self.assertEqual(result["segmentId"], "attraction-1")
            self.assertEqual(result["plan"], original)
            self.assertEqual(plan, original)
            self.assertEqual(result["notes"], ["deltaMinutes is not positive; plan unchanged"])

    def test_missing_clocks_follow_kind_defaults(self) -> None:
        plan = {
            "tripId": "trip-1",
            "flights": [
                {
                    "segmentId": "flight-1",
                    "kind": "flight",
                    "from": "SFO",
                    "to": "KIX",
                    "departDate": DAY,
                }
            ],
            "hotels": [
                {
                    "segmentId": "hotel-1",
                    "kind": "hotel",
                    "city": "Kyoto",
                    "checkIn": DAY,
                    "checkOut": "2026-11-06",
                }
            ],
            "attractions": [
                _attraction("before-end", DAY, "11:59"),
                _attraction("at-end", DAY, "12:00"),
                _attraction("next-day", NEXT_DAY, "09:00"),
            ],
        }
        result = replan_late(
            "trip-1",
            "2026-11-02T08:00:00Z",
            plan,
            _late("flight-1", "flight", 60),
        )

        self.assertEqual(result["plan"]["flights"][0], plan["flights"][0])
        self.assertEqual(result["plan"]["attractions"][0]["time"], "11:59")
        self.assertNotIn("start", result["plan"]["attractions"][0])
        self.assertEqual(result["plan"]["attractions"][1]["time"], "13:00")
        self.assertEqual(result["plan"]["attractions"][1]["start"], "2026-11-02T13:00:00Z")
        self.assertEqual(result["plan"]["hotels"][0]["checkIn"], DAY)
        self.assertEqual(result["plan"]["hotels"][0]["checkOut"], "2026-11-06")
        self.assertEqual(result["plan"]["hotels"][0]["start"], "2026-11-02T16:00:00Z")
        self.assertEqual(result["plan"]["hotels"][0]["end"], "2026-11-06T12:00:00Z")
        self.assertEqual(result["plan"]["attractions"][2], plan["attractions"][2])

        bare = {
            "attractions": [
                _attraction("early", DAY, start="2026-11-02T08:00:00Z", end="2026-11-02T09:00:00Z"),
                _attraction("all-day", DAY, time=None),
            ]
        }
        shifted = replan_late("trip-1", "2026-11-02T09:30:00Z", bare, _late("early", "attraction", 60))
        self.assertEqual(shifted["plan"]["attractions"][0], bare["attractions"][0])
        self.assertEqual(shifted["plan"]["attractions"][1]["start"], "2026-11-02T11:00:00Z")
        self.assertEqual(shifted["plan"]["attractions"][1]["end"], "2026-11-02T13:00:00Z")
        self.assertNotIn("time", shifted["plan"]["attractions"][1])

    def test_explicit_window_and_midnight_rollover(self) -> None:
        plan = {
            "attractions": [
                _attraction(
                    "timed",
                    DAY,
                    start="2026-11-02T18:00:00Z",
                    end="2026-11-02T19:00:00Z",
                ),
                _attraction("late-show", DAY, "23:30"),
            ]
        }
        result = replan_late("trip-1", "2026-11-02T19:30:00Z", plan, _late("timed", "attraction", 60))
        show = result["plan"]["attractions"][1]
        self.assertEqual(show["date"], NEXT_DAY)
        self.assertEqual(show["time"], "00:30")
        self.assertEqual(show["start"], "2026-11-03T00:30:00Z")
        self.assertEqual(show["end"], "2026-11-03T02:30:00Z")
        self.assertEqual(result["plan"]["attractions"][0], plan["attractions"][0])

    def test_partial_plan_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"plan": None, "disruption": None, "now": None},
            {"plan": {"flights": [None, "x", {}]}, "disruption": "nope", "now": "not-a-time"},
            {"flights": [{"segmentId": "flight-1"}]},
            [],
        ]
        for case in cases:
            result = replan_late(case)
            self.assertEqual(set(result), {"segmentId", "event", "changed", "plan", "notes"})
            self.assertEqual(result["event"], "ended_late")
            self.assertIsInstance(result["changed"], bool)
            self.assertIsInstance(result["plan"], dict)
            self.assertIsInstance(result["notes"], list)
            for note in result["notes"]:
                self.assertIsInstance(note, str)

        plan = {"attractions": [_attraction("a1", DAY, "10:00"), _attraction("a2", DAY, "12:00")]}
        bad_now = replan_late("trip-1", "not-a-time", plan, _late("a1", "attraction", 60))
        self.assertFalse(bad_now["changed"])
        self.assertEqual(bad_now["plan"]["attractions"][1]["time"], "12:00")
        self.assertNotIn("start", bad_now["plan"]["attractions"][1])

        missing = replan_late("trip-1", NOW, plan, _late("missing", "attraction", 60))
        self.assertFalse(missing["changed"])
        self.assertEqual(missing["plan"]["attractions"][1]["time"], "12:00")
        self.assertEqual(missing["notes"], ["segment missing is not on the plan"])

    def test_tool_spec_is_replan_late(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "replan_late")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["tripId", "now", "plan", "disruption"])
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["properties"]["disruption"]["properties"]["event"]["enum"],
            ["ended_late"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["segmentId", "event", "changed", "plan", "notes"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("when a segment ends late", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "replan_late")
        self.assertEqual(AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"], TOOL_SPEC["inputSchema"])

    def test_handler_calls_replan_late(self) -> None:
        plan = _day_plan()
        payload = {
            "tripId": "trip-1",
            "now": NOW,
            "plan": plan,
            "disruption": _late("attraction-1", "attraction", 60),
        }
        self.assertEqual(handler(payload), replan_late(payload))
        self.assertEqual(handler(json.dumps(payload)), replan_late(payload))
        wrapped = handler(
            {"arguments": payload},
            _AgentCoreContext("replan___replan_late"),
        )
        self.assertEqual(wrapped["plan"]["attractions"][1]["time"], "13:30")
        rejected = handler(payload, _AgentCoreContext("book_flight"))
        self.assertFalse(rejected["changed"])
        self.assertEqual(rejected["notes"], ["unsupported AgentCore tool; expected replan_late"])

    def test_does_not_read_the_wall_clock_or_aws(self) -> None:
        source = inspect.getsource(replan_mod) + inspect.getsource(tool_mod)
        for banned in ("datetime.now", ".utcnow", "time.time", "boto3", "botocore", "requests", "urllib", "bedrock_agentcore"):
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
            raise AssertionError("replan_late opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
