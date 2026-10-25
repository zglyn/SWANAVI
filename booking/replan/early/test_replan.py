"""Early-finish replan: pull later same-day segments forward.

These tests stay in-process. They do not call AWS or open a socket.
"""

from __future__ import annotations

import copy
import inspect
import socket
import unittest

from booking.replan.early import AGENTCORE_TOOL, TOOL_SPEC, handler, replan_early
from booking.replan.early import replan as replan_mod
from booking.replan.early import tool as tool_mod

NOW = "2026-11-03T11:00:00Z"

PLAN = {
    "tripId": "trip-early",
    "flights": [],
    "hotels": [],
    "attractions": [
        {
            "segmentId": "attraction-early",
            "kind": "attraction",
            "name": "Morning walk",
            "date": "2026-11-03",
            "time": "08:00",
        },
        {
            "segmentId": "attraction-done",
            "kind": "attraction",
            "name": "Temple",
            "date": "2026-11-03",
            "time": "10:00",
        },
        {
            "segmentId": "attraction-next",
            "kind": "attraction",
            "name": "Garden",
            "date": "2026-11-03",
            "time": "14:00",
        },
        {
            "segmentId": "attraction-later",
            "kind": "attraction",
            "name": "Tea",
            "date": "2026-11-03",
            "time": "17:00",
        },
        {
            "segmentId": "attraction-tomorrow",
            "kind": "attraction",
            "name": "Shrine",
            "date": "2026-11-04",
            "time": "10:00",
        },
    ],
}


def _disruption(segment_id: str = "attraction-done", **overrides) -> dict:
    disruption = {
        "segmentId": segment_id,
        "kind": "attraction",
        "event": "ended_early",
        "deltaMinutes": 60,
    }
    disruption.update(overrides)
    return disruption


def _by_id(plan: dict, segment_id: str) -> dict:
    for bucket in ("flights", "hotels", "attractions"):
        items = plan.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("segmentId") == segment_id:
                return item
    raise AssertionError(f"missing {segment_id}")


class _AgentCoreContext:
    def __init__(self, tool_name: str) -> None:
        self.client_context = self
        self.custom = {"bedrockAgentCoreToolName": tool_name}


class ReplanEarlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._network = _network_forbidden()
        self._network.__enter__()

    def tearDown(self) -> None:
        self._network.__exit__(None, None, None)

    def test_sixty_minutes_early_pulls_the_next_same_day_item_forward(self) -> None:
        original = copy.deepcopy(PLAN)
        result = replan_early(
            tripId="trip-early",
            now=NOW,
            plan=PLAN,
            disruption=_disruption(),
        )

        self.assertEqual(result["segmentId"], "attraction-done")
        self.assertEqual(result["event"], "ended_early")
        self.assertTrue(result["changed"])
        self.assertEqual(PLAN, original)

        done = _by_id(result["plan"], "attraction-done")
        nxt = _by_id(result["plan"], "attraction-next")
        later = _by_id(result["plan"], "attraction-later")
        early = _by_id(result["plan"], "attraction-early")
        tomorrow = _by_id(result["plan"], "attraction-tomorrow")

        self.assertEqual(done, _by_id(original, "attraction-done"))
        self.assertEqual(early, _by_id(original, "attraction-early"))
        self.assertEqual(tomorrow, _by_id(original, "attraction-tomorrow"))
        self.assertEqual(nxt["time"], "13:00")
        self.assertEqual(nxt["date"], "2026-11-03")
        self.assertEqual(nxt["start"], "2026-11-03T13:00:00Z")
        self.assertEqual(nxt["end"], "2026-11-03T15:00:00Z")
        self.assertEqual(later["time"], "16:00")
        self.assertEqual(later["start"], "2026-11-03T16:00:00Z")
        self.assertEqual(later["end"], "2026-11-03T18:00:00Z")
        self.assertEqual(
            [item["segmentId"] for item in result["plan"]["attractions"]],
            [item["segmentId"] for item in original["attractions"]],
        )
        self.assertIn("shifted attraction-next earlier by 60 minutes", result["notes"])

    def test_segment_already_started_does_not_move(self) -> None:
        plan = copy.deepcopy(PLAN)
        result = replan_early(
            {
                "tripId": "trip-early",
                "now": "2026-11-03T14:30:00Z",
                "plan": plan,
                "disruption": _disruption(),
            }
        )

        started = _by_id(result["plan"], "attraction-next")
        later = _by_id(result["plan"], "attraction-later")
        self.assertEqual(started, _by_id(PLAN, "attraction-next"))
        self.assertNotIn("start", started)
        self.assertEqual(later["time"], "16:00")
        self.assertEqual(later["start"], "2026-11-03T16:00:00Z")
        self.assertTrue(result["changed"])
        self.assertIn("left attraction-next in place; it already started before now", result["notes"])

    def test_delta_minutes_zero_does_not_change_the_plan(self) -> None:
        for delta in (0, -15, 0.0):
            result = replan_early(tripId="trip-early", now=NOW, plan=PLAN, disruption=_disruption(deltaMinutes=delta))
            self.assertFalse(result["changed"])
            self.assertEqual(result["event"], "ended_early")
            self.assertEqual(result["plan"], PLAN)
            self.assertEqual(result["notes"], ["deltaMinutes is not positive; plan unchanged"])

    def test_shift_does_not_start_before_now(self) -> None:
        result = replan_early(
            tripId="trip-early",
            now="2026-11-03T13:30:00Z",
            plan=PLAN,
            disruption=_disruption(),
        )

        nxt = _by_id(result["plan"], "attraction-next")
        self.assertEqual(nxt["start"], "2026-11-03T13:30:00Z")
        self.assertEqual(nxt["end"], "2026-11-03T15:30:00Z")
        self.assertEqual(nxt["time"], "13:30")
        self.assertIn(
            "shifted attraction-next earlier by 30 minutes so it does not start before now",
            result["notes"],
        )

    def test_derived_flight_hotel_and_attraction_windows(self) -> None:
        plan = {
            "tripId": "trip-derived",
            "flights": [
                {
                    "segmentId": "flight-next",
                    "kind": "flight",
                    "from": "SFO",
                    "to": "KIX",
                    "departDate": "2026-11-03",
                    "returnDate": "2026-11-06",
                },
                {
                    "segmentId": "flight-explicit",
                    "kind": "flight",
                    "from": "KIX",
                    "to": "ITM",
                    "departDate": "2026-11-03",
                    "start": "2026-11-03T15:00:00Z",
                    "end": "2026-11-03T16:00:00Z",
                },
            ],
            "hotels": [
                {
                    "segmentId": "hotel-next",
                    "kind": "hotel",
                    "city": "Kyoto",
                    "checkIn": "2026-11-03",
                    "checkOut": "2026-11-06",
                }
            ],
            "attractions": [
                {
                    "segmentId": "attraction-done",
                    "kind": "attraction",
                    "name": "Early",
                    "city": "Kyoto",
                    "date": "2026-11-03",
                    "time": "05:00",
                },
                {
                    "segmentId": "attraction-untimed",
                    "kind": "attraction",
                    "name": "Default",
                    "city": "Kyoto",
                    "date": "2026-11-03",
                },
            ],
        }
        result = replan_early(
            tripId="trip-derived",
            now="2026-11-03T07:00:00Z",
            plan=plan,
            disruption=_disruption(),
        )

        self.assertTrue(result["changed"])
        flight = _by_id(result["plan"], "flight-next")
        explicit = _by_id(result["plan"], "flight-explicit")
        hotel = _by_id(result["plan"], "hotel-next")
        untimed = _by_id(result["plan"], "attraction-untimed")
        done = _by_id(result["plan"], "attraction-done")

        self.assertEqual(done["time"], "05:00")
        self.assertNotIn("start", done)
        self.assertEqual(flight["departDate"], "2026-11-03")
        self.assertEqual(flight["returnDate"], "2026-11-06")
        self.assertEqual(flight["start"], "2026-11-03T08:00:00Z")
        self.assertEqual(flight["end"], "2026-11-03T11:00:00Z")
        self.assertEqual(explicit["start"], "2026-11-03T14:00:00Z")
        self.assertEqual(explicit["end"], "2026-11-03T15:00:00Z")
        self.assertEqual(explicit["departDate"], "2026-11-03")
        self.assertEqual(hotel["checkIn"], "2026-11-03")
        self.assertEqual(hotel["checkOut"], "2026-11-06")
        self.assertEqual(hotel["start"], "2026-11-03T14:00:00Z")
        self.assertEqual(hotel["end"], "2026-11-06T10:00:00Z")
        self.assertEqual(untimed["time"], "09:00")
        self.assertEqual(untimed["start"], "2026-11-03T09:00:00Z")
        self.assertEqual(untimed["end"], "2026-11-03T11:00:00Z")

    def test_partial_plan_does_not_raise(self) -> None:
        cases = [
            None,
            "not json",
            {},
            {"plan": None, "disruption": None, "now": None},
            {"flights": [1, "x", None], "hotels": None, "attractions": "nope"},
            {"plan": {"flights": [{}]}, "disruption": "bad", "now": "not-a-time"},
            {"plan": {"hotels": [{"kind": "hotel"}]}, "disruption": {}, "now": NOW},
            {
                "tripId": "partial",
                "now": NOW,
                "plan": {
                    "flights": ["nope", None],
                    "hotels": None,
                    "attractions": [
                        {"segmentId": "attraction-done", "date": "2026-11-03", "time": "10:00"},
                        {"segmentId": "attraction-next", "date": "2026-11-03", "time": "14:00"},
                    ],
                },
                "disruption": _disruption(),
            },
        ]
        for case in cases:
            result = replan_early(case)
            self.assertEqual(set(result), {"segmentId", "event", "changed", "plan", "notes"})
            self.assertEqual(result["event"], "ended_early")
            self.assertIsInstance(result["changed"], bool)
            self.assertIsInstance(result["plan"], dict)
            self.assertIsInstance(result["notes"], list)
            self.assertTrue(all(isinstance(note, str) for note in result["notes"]))

        shifted = replan_early(cases[-1])
        self.assertTrue(shifted["changed"])
        self.assertEqual(_by_id(shifted["plan"], "attraction-next")["time"], "13:00")

    def test_other_disruption_events_do_not_change_the_plan(self) -> None:
        result = replan_early(
            tripId="trip-early",
            now=NOW,
            plan=PLAN,
            disruption=_disruption(event="cancelled"),
        )
        self.assertFalse(result["changed"])
        self.assertEqual(result["plan"], PLAN)
        self.assertEqual(result["event"], "ended_early")

    def test_tool_spec_is_replan_early(self) -> None:
        self.assertEqual(TOOL_SPEC["name"], "replan_early")
        self.assertEqual(TOOL_SPEC["inputSchema"]["required"], ["tripId", "now", "plan", "disruption"])
        self.assertEqual(
            TOOL_SPEC["inputSchema"]["properties"]["disruption"]["required"],
            ["segmentId", "kind", "event", "deltaMinutes"],
        )
        self.assertEqual(TOOL_SPEC["outputSchema"]["required"], ["segmentId", "event", "changed", "plan", "notes"])
        self.assertEqual(TOOL_SPEC["outputSchema"]["properties"]["event"]["enum"], ["ended_early"])
        self.assertIn("AgentCore", TOOL_SPEC["description"])
        self.assertIn("when a segment ends early", TOOL_SPEC["description"])
        self.assertEqual(AGENTCORE_TOOL["type"], "inline_function")
        self.assertEqual(AGENTCORE_TOOL["name"], "replan_early")
        self.assertEqual(AGENTCORE_TOOL["config"]["inlineFunction"]["inputSchema"], TOOL_SPEC["inputSchema"])

    def test_handler_calls_replan_early(self) -> None:
        payload = {"tripId": "trip-early", "now": NOW, "plan": PLAN, "disruption": _disruption()}
        self.assertEqual(handler(payload), replan_early(payload))
        self.assertEqual(
            handler(payload, _AgentCoreContext("booking___replan_early")),
            replan_early(payload),
        )

    def test_wrong_tool_name_does_not_replan(self) -> None:
        payload = {"tripId": "trip-early", "now": NOW, "plan": PLAN, "disruption": _disruption()}
        result = handler(payload, _AgentCoreContext("booking___replan_late"))
        self.assertFalse(result["changed"])
        self.assertEqual(result["plan"], PLAN)
        self.assertEqual(result["notes"], ["unsupported AgentCore tool; expected replan_early"])

    def test_does_not_read_the_wall_clock_or_call_aws(self) -> None:
        for module in (replan_mod, tool_mod):
            source = inspect.getsource(module)
            for banned in (
                "datetime.now",
                ".utcnow",
                "time.time",
                "boto3",
                "botocore",
                "urllib",
                "requests",
                "socket",
                "subprocess",
            ):
                self.assertNotIn(banned, source)


class _network_forbidden:
    def __enter__(self):
        self._socket = socket.socket
        self._create_connection = socket.create_connection

        def blocked(*_args, **_kwargs):
            raise AssertionError("replan_early opened a socket")

        socket.socket = blocked
        socket.create_connection = blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket = self._socket
        socket.create_connection = self._create_connection
        return False


if __name__ == "__main__":
    unittest.main()
